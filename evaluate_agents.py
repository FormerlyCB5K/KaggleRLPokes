"""Run two folder-based Pokemon TCG agents head to head.

Each agent folder must contain a Python entry point exposing ``agent(obs_dict)``.
``main.py`` is preferred; when it is absent, the folder must contain exactly one
non-test Python file.  The deck is read from ``deck.csv`` (case-insensitive) or,
for single-file agents such as the Lucario baseline, from ``MY_DECK``, ``DECK``,
or ``my_deck`` in the module.

Example:

    python evaluate_agents.py Rising-Tide-Fixed-Metal-v15 sample-archaludon 100

The evaluator alternates which bot occupies engine side 0.  The engine chooses
the actual first player, so the report buckets every result by the observation's
``firstPlayer`` field rather than assuming side 0 went first.
"""

from __future__ import annotations

import argparse
import copy
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Callable, Iterator, Sequence


REPO_ROOT = Path(__file__).resolve().parent
DECK_ATTRIBUTES = ("MY_DECK", "DECK", "my_deck")


def _wire_engine_imports() -> None:
    """Expose the local engine under both repository and Kaggle import names."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    import cg_download
    import cg_download.api
    import cg_download.game
    import cg_download.sim
    import cg_download.utils

    aliases = {
        "cg": cg_download,
        "cg.api": cg_download.api,
        "cg.game": cg_download.game,
        "cg.sim": cg_download.sim,
        "cg.utils": cg_download.utils,
    }
    for name, module in aliases.items():
        sys.modules.setdefault(name, module)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "agent"


@contextlib.contextmanager
def _agent_import_path(folder: Path) -> Iterator[None]:
    old_path = list(sys.path)
    old_cwd = Path.cwd()
    sys.path.insert(0, str(folder))
    os.chdir(folder)
    try:
        yield
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_path


def _is_within(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
    except (OSError, ValueError):
        return False
    return True


def _clear_agent_modules(folders: Sequence[Path]) -> None:
    """Remove modules loaded from agent folders so each game starts clean."""
    for module_name, module in list(sys.modules.items()):
        source = getattr(module, "__file__", None)
        if not source:
            continue
        source_path = Path(source)
        if any(_is_within(source_path, folder) for folder in folders):
            del sys.modules[module_name]


def _entrypoint(folder: Path) -> Path:
    main = folder / "main.py"
    if main.is_file():
        return main
    candidates = sorted(
        path
        for path in folder.glob("*.py")
        if not path.name.startswith("test_") and path.name != "__init__.py"
    )
    if len(candidates) != 1:
        names = ", ".join(path.name for path in candidates) or "none"
        raise RuntimeError(
            f"{folder}: expected main.py or exactly one non-test Python file; "
            f"found {names}"
        )
    return candidates[0]


def _deck_file(folder: Path) -> Path | None:
    candidates = sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.name.casefold() == "deck.csv"
    )
    if len(candidates) > 1:
        raise RuntimeError(
            f"{folder}: multiple case-insensitive deck.csv matches: "
            + ", ".join(path.name for path in candidates)
        )
    return candidates[0] if candidates else None


def _read_deck(path: Path) -> list[int]:
    try:
        deck = [int(line.strip()) for line in path.read_text().splitlines() if line.strip()]
    except ValueError as exc:
        raise RuntimeError(f"{path}: deck contains a non-integer line") from exc
    return _validate_deck(deck, str(path))


def _validate_deck(values: object, source: str) -> list[int]:
    if not isinstance(values, (list, tuple)):
        raise RuntimeError(f"{source}: deck must be a list or tuple")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise RuntimeError(f"{source}: deck must contain only integer card IDs")
    deck = list(values)
    if len(deck) != 60:
        raise RuntimeError(f"{source}: expected 60 cards, found {len(deck)}")
    return deck


def _load_module(source: Path, instance_key: str) -> ModuleType:
    digest = hashlib.sha256(f"{source.resolve()}:{instance_key}".encode()).hexdigest()[:12]
    module_name = f"_head_to_head_{_slug(source.parent.name)}_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not create an import spec for {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        with _agent_import_path(source.parent):
            spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


@dataclass(frozen=True)
class BotSource:
    folder: Path
    name: str
    source: Path
    file_deck: tuple[int, ...] | None

    @classmethod
    def resolve(cls, folder_arg: str, name: str | None) -> "BotSource":
        folder = Path(folder_arg).expanduser().resolve()
        if not folder.is_dir():
            raise RuntimeError(f"agent folder does not exist: {folder}")
        source = _entrypoint(folder)
        deck_path = _deck_file(folder)
        file_deck = tuple(_read_deck(deck_path)) if deck_path else None
        return cls(
            folder=folder,
            name=name or folder.name,
            source=source,
            file_deck=file_deck,
        )

    def instantiate(self, instance_key: str) -> "Bot":
        module = _load_module(self.source, instance_key)
        agent_fn = getattr(module, "agent", None)
        if not callable(agent_fn):
            raise RuntimeError(f"{self.source}: no callable agent(obs_dict) entry point")

        if self.file_deck is not None:
            deck = list(self.file_deck)
        else:
            deck = None
            for attribute in DECK_ATTRIBUTES:
                candidate = getattr(module, attribute, None)
                if candidate is not None:
                    deck = _validate_deck(candidate, f"{self.source}:{attribute}")
                    break
            if deck is None:
                raise RuntimeError(
                    f"{self.folder}: no deck.csv and none of "
                    f"{', '.join(DECK_ATTRIBUTES)} exists in {self.source.name}"
                )
        return Bot(self.name, self.folder, module, agent_fn, deck)


@dataclass
class Bot:
    name: str
    folder: Path
    module: ModuleType
    agent_fn: Callable[[dict], list[int]]
    configured_deck: list[int]

    def act(self, observation: dict) -> list[int]:
        with _agent_import_path(self.folder):
            action = self.agent_fn(observation)
        if not isinstance(action, list):
            raise RuntimeError(
                f"{self.name}: agent returned {type(action).__name__}, expected list[int]"
            )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in action):
            raise RuntimeError(f"{self.name}: agent returned a non-integer action: {action!r}")
        return action

    def deck_submission(self, observation: dict) -> list[int]:
        submitted = _validate_deck(
            self.act(observation), f"{self.name}: initial deck action"
        )
        if Counter(submitted) != Counter(self.configured_deck):
            raise RuntimeError(
                f"{self.name}: agent's submitted deck does not match its folder deck"
            )
        return submitted


@dataclass
class GameResult:
    game: int
    side_0: str
    side_1: str
    first_player_side: int
    first_player: str
    second_player: str
    result_side: int
    winner: str | None
    draw: bool
    actions: int
    elapsed_seconds: float


def _run_game(
    game_number: int,
    side_bots: tuple[Bot, Bot],
    max_actions: int,
) -> GameResult:
    from cg_download.game import battle_finish, battle_select, battle_start

    decks = [bot.configured_deck for bot in side_bots]
    observation = None
    started = False
    initialized_sides: set[int] = set()
    started_at = time.perf_counter()
    try:
        observation, start_data = battle_start(decks[0], decks[1])
        started = bool(start_data.battlePtr)
        if start_data.errorPlayer >= 0:
            raise RuntimeError(
                "engine rejected deck for side "
                f"{start_data.errorPlayer} with error type {start_data.errorType}"
            )
        if observation is None:
            raise RuntimeError("engine did not return an initial observation")

        first_side: int | None = None
        for side, bot in enumerate(side_bots):
            reset_observation = copy.deepcopy(observation)
            reset_observation["select"] = None
            current = reset_observation.get("current")
            if isinstance(current, dict):
                current["yourIndex"] = side
            bot.deck_submission(reset_observation)
            initialized_sides.add(side)

        actions = 0
        while True:
            current = observation.get("current") or {}
            observed_first = int(current.get("firstPlayer", -1))
            if observed_first in (0, 1):
                if first_side is not None and first_side != observed_first:
                    raise RuntimeError(
                        "engine changed firstPlayer during the game: "
                        f"{first_side} -> {observed_first}"
                    )
                first_side = observed_first
            result = int(current.get("result", -1))
            if result >= 0:
                break
            if actions >= max_actions:
                raise RuntimeError(
                    f"game {game_number} exceeded --max-actions={max_actions}"
                )
            acting_side = int(current.get("yourIndex", -1))
            if acting_side not in (0, 1):
                raise RuntimeError(f"engine returned invalid yourIndex={acting_side}")
            bot = side_bots[acting_side]
            if observation.get("select") is None:
                action = bot.deck_submission(observation)
                initialized_sides.add(acting_side)
            else:
                if acting_side not in initialized_sides:
                    raise RuntimeError(
                        f"engine requested a play from {bot.name} before its deck action"
                    )
                action = bot.act(observation)
            observation = battle_select(action)
            actions += 1

        if result not in (0, 1, 2):
            raise RuntimeError(f"engine returned unknown terminal result={result}")
        if first_side is None:
            raise RuntimeError("engine never assigned firstPlayer")
        draw = result == 2
        winner = None if draw else side_bots[result].name
        return GameResult(
            game=game_number,
            side_0=side_bots[0].name,
            side_1=side_bots[1].name,
            first_player_side=first_side,
            first_player=side_bots[first_side].name,
            second_player=side_bots[1 - first_side].name,
            result_side=result,
            winner=winner,
            draw=draw,
            actions=actions,
            elapsed_seconds=round(time.perf_counter() - started_at, 6),
        )
    finally:
        if started:
            battle_finish()


def _empty_bucket() -> dict[str, int]:
    return {"games": 0, "wins": 0, "losses": 0, "draws": 0}


def _with_rates(bucket: dict[str, int]) -> dict[str, int | float | None]:
    games = bucket["games"]
    return {
        **bucket,
        "win_rate": bucket["wins"] / games if games else None,
        "score_rate": (bucket["wins"] + 0.5 * bucket["draws"]) / games if games else None,
    }


def summarize(
    records: Sequence[GameResult],
    bot_a: str,
    bot_b: str,
) -> dict[str, dict[str, dict[str, int | float | None]]]:
    raw = {
        bot_a: {"overall": _empty_bucket(), "first": _empty_bucket(), "second": _empty_bucket()},
        bot_b: {"overall": _empty_bucket(), "first": _empty_bucket(), "second": _empty_bucket()},
    }
    for record in records:
        sides = (record.side_0, record.side_1)
        for side, name in enumerate(sides):
            order = "first" if side == record.first_player_side else "second"
            for bucket_name in ("overall", order):
                bucket = raw[name][bucket_name]
                bucket["games"] += 1
                if record.draw:
                    bucket["draws"] += 1
                elif record.result_side == side:
                    bucket["wins"] += 1
                else:
                    bucket["losses"] += 1
    return {
        name: {bucket_name: _with_rates(bucket) for bucket_name, bucket in buckets.items()}
        for name, buckets in raw.items()
    }


def _write_log(
    path: Path,
    started_at: str,
    bot_a: BotSource,
    bot_b: BotSource,
    configured_decks: dict[str, Sequence[int]],
    requested_games: int,
    records: Sequence[GameResult],
    error: str | None = None,
) -> None:
    payload = {
        "schema_version": 1,
        "started_at_utc": started_at,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_games": requested_games,
        "completed_games": len(records),
        "bots": {
            bot_a.name: {
                "folder": str(bot_a.folder),
                "entrypoint": str(bot_a.source),
                "deck_source": (
                    str(_deck_file(bot_a.folder))
                    if _deck_file(bot_a.folder) is not None
                    else f"{bot_a.source}:module_attribute"
                ),
                "configured_deck": list(configured_decks[bot_a.name]),
            },
            bot_b.name: {
                "folder": str(bot_b.folder),
                "entrypoint": str(bot_b.source),
                "deck_source": (
                    str(_deck_file(bot_b.folder))
                    if _deck_file(bot_b.folder) is not None
                    else f"{bot_b.source}:module_attribute"
                ),
                "configured_deck": list(configured_decks[bot_b.name]),
            },
        },
        "games": [asdict(record) for record in records],
        "summary": summarize(records, bot_a.name, bot_b.name),
        "error": error,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _rate(value: float | None) -> str:
    return "n/a" if value is None else f"{100.0 * value:.1f}%"


def _print_summary(summary: dict, names: Sequence[str]) -> None:
    print("\nFinal results")
    for name in names:
        buckets = summary[name]
        print(f"  {name}")
        for bucket_name in ("overall", "first", "second"):
            bucket = buckets[bucket_name]
            print(
                f"    {bucket_name:7s}: {bucket['wins']}-{bucket['losses']}"
                f"-{bucket['draws']} over {bucket['games']} games, "
                f"win rate {_rate(bucket['win_rate'])}, "
                f"score rate {_rate(bucket['score_rate'])}"
            )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bot_a", help="first agent folder")
    parser.add_argument("bot_b", help="second agent folder")
    parser.add_argument("games", type=int, help="total number of games")
    parser.add_argument("--name-a", help="display name for the first bot")
    parser.add_argument("--name-b", help="display name for the second bot")
    parser.add_argument(
        "--output",
        type=Path,
        help="JSON log path (default: match-logs/<timestamp>-<bots>.json)",
    )
    parser.add_argument(
        "--max-actions",
        type=int,
        default=20_000,
        help="abort a non-terminating game after this many engine selections",
    )
    args = parser.parse_args(argv)
    if args.games <= 0:
        parser.error("games must be positive")
    if args.max_actions <= 0:
        parser.error("--max-actions must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _wire_engine_imports()

    bot_a = BotSource.resolve(args.bot_a, args.name_a)
    bot_b = BotSource.resolve(args.bot_b, args.name_b)
    if bot_a.name == bot_b.name:
        raise RuntimeError("bot display names must be distinct; use --name-a/--name-b")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or (
        REPO_ROOT
        / "match-logs"
        / f"{timestamp}-{_slug(bot_a.name)}-vs-{_slug(bot_b.name)}.json"
    )
    output = output.expanduser().resolve()
    started_at = datetime.now(timezone.utc).isoformat()
    records: list[GameResult] = []
    configured_decks = {
        bot_a.name: bot_a.instantiate("deck-inspection-a").configured_deck,
        bot_b.name: bot_b.instantiate("deck-inspection-b").configured_deck,
    }
    _clear_agent_modules((bot_a.folder, bot_b.folder))

    print(f"Bot A: {bot_a.name} ({bot_a.folder})")
    print(f"Bot B: {bot_b.name} ({bot_b.folder})")
    print(f"Games: {args.games}; log: {output}")

    try:
        for index in range(args.games):
            _clear_agent_modules((bot_a.folder, bot_b.folder))
            first, second = (
                (bot_a, bot_b) if index % 2 == 0 else (bot_b, bot_a)
            )
            side_bots = (
                first.instantiate(f"game-{index + 1}-side-0"),
                second.instantiate(f"game-{index + 1}-side-1"),
            )
            result = _run_game(index + 1, side_bots, args.max_actions)
            records.append(result)
            outcome = "draw" if result.draw else f"{result.winner} won"
            print(
                f"[{index + 1:>4}/{args.games}] {outcome}; "
                f"first={result.first_player}; actions={result.actions}; "
                f"{result.elapsed_seconds:.2f}s",
                flush=True,
            )
            _write_log(
                output,
                started_at,
                bot_a,
                bot_b,
                configured_decks,
                args.games,
                records,
            )
    except BaseException as exc:
        _write_log(
            output,
            started_at,
            bot_a,
            bot_b,
            configured_decks,
            args.games,
            records,
            error=f"{type(exc).__name__}: {exc}",
        )
        print(f"\nMatch stopped after {len(records)} completed games. Partial log: {output}")
        raise

    summary = summarize(records, bot_a.name, bot_b.name)
    _print_summary(summary, (bot_a.name, bot_b.name))
    print(f"\nDetailed JSON log: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
