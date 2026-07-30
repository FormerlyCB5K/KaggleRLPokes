import json

from evaluate_agents import BotSource, GameResult, _write_log, summarize


def _game(
    number: int,
    side_0: str,
    side_1: str,
    first_side: int,
    result_side: int,
) -> GameResult:
    sides = (side_0, side_1)
    return GameResult(
        game=number,
        side_0=side_0,
        side_1=side_1,
        first_player_side=first_side,
        first_player=sides[first_side],
        second_player=sides[1 - first_side],
        result_side=result_side,
        winner=None if result_side == 2 else sides[result_side],
        draw=result_side == 2,
        actions=10,
        elapsed_seconds=1.0,
    )


def test_summary_uses_actual_first_player_not_engine_side() -> None:
    games = [
        _game(1, "A", "B", first_side=1, result_side=0),
        _game(2, "B", "A", first_side=0, result_side=0),
        _game(3, "A", "B", first_side=0, result_side=2),
    ]

    summary = summarize(games, "A", "B")

    assert summary["A"]["overall"]["games"] == 3
    assert summary["A"]["overall"]["wins"] == 1
    assert summary["A"]["overall"]["losses"] == 1
    assert summary["A"]["overall"]["draws"] == 1
    assert summary["A"]["first"]["games"] == 1
    assert summary["A"]["first"]["draws"] == 1
    assert summary["A"]["second"]["games"] == 2
    assert summary["A"]["second"]["win_rate"] == 0.5

    assert summary["B"]["first"]["games"] == 2
    assert summary["B"]["first"]["wins"] == 1
    assert summary["B"]["first"]["losses"] == 1
    assert summary["B"]["second"]["games"] == 1
    assert summary["B"]["second"]["draws"] == 1


def test_evaluation_log_records_both_configured_decks(tmp_path) -> None:
    folders = []
    sources = []
    for name, start in (("A", 1), ("B", 101)):
        folder = tmp_path / name
        folder.mkdir()
        source = folder / "main.py"
        source.write_text("def agent(obs): return []\n", encoding="utf-8")
        (folder / "deck.csv").write_text(
            "".join(f"{value}\n" for value in range(start, start + 60)),
            encoding="utf-8",
        )
        folders.append(folder)
        sources.append(source)
    bot_a = BotSource(folders[0], "A", sources[0], tuple(range(1, 61)))
    bot_b = BotSource(folders[1], "B", sources[1], tuple(range(101, 161)))
    output = tmp_path / "results.json"

    _write_log(
        output,
        "2026-07-30T00:00:00+00:00",
        bot_a,
        bot_b,
        {"A": list(range(1, 61)), "B": list(range(101, 161))},
        1,
        [_game(1, "A", "B", first_side=0, result_side=0)],
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bots"]["A"]["configured_deck"] == list(range(1, 61))
    assert payload["bots"]["B"]["configured_deck"] == list(range(101, 161))
    assert payload["bots"]["A"]["deck_source"].endswith("deck.csv")
