from evaluate_agents import GameResult, summarize


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
