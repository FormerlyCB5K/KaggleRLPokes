# Rising Tide Fixed Metal v15

This folder was materialized from
`rising-tide-fixed-metal-v15-reproducible-agent.ipynb`. The Python sources,
deck, and package metadata come from the notebook's `%%writefile` cells.

The default route in `main.py` is `metal_a`. Its submitted 60-card multiset
matches `deck.csv`.

From the repository root, run a local matchup with:

```powershell
.venv\Scripts\python.exe evaluate_agents.py `
  Rising-Tide-Fixed-Metal-v15 `
  sample-archaludon `
  100
```

The evaluator writes a detailed JSON match log under `match-logs/` by default.
It reports overall results and separate results for games in which each bot was
the engine's actual first or second player.
