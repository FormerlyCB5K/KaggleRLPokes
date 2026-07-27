# 09a — Registry, Multi-Agent Loading & Deck Resolution

Part 1 of [`09-opponent-pool.md`](09-opponent-pool.md). Pure plumbing — no changes to
`collect_episode` or the training loop yet. Delivers the data structures and functions
the later parts consume.

## Purpose

Stand up the hardcoded `OPPONENTS` registry and the two resolver functions it needs:
a **collision-safe module loader** and a **deck resolver** that normalizes the mixed
deck sources. After this part, any opponent's policy callable and 60-card deck can be
obtained by name, with all four file-based agents loadable *simultaneously*.

## Behavior

### Registry

Add the `OPPONENTS` dict from the [overview's shared reference](09-opponent-pool.md).
Resolve module/deck paths relative to `_parent`.

### Collision-safe module loader

Three of the four agent files are named `main.py`. The current
`importlib.import_module("main")` caches under `"main"` and would return the **first**
agent loaded for every later one. Replace with:

```python
spec = importlib.util.spec_from_file_location(unique_name, abs_path)
module = importlib.util.module_from_spec(spec)
sys.modules[unique_name] = module   # so the agent's own `import` sees itself
spec.loader.exec_module(module)
```

- `unique_name` = the opponent key (e.g. `"opp_clefable"`), never `"main"`.
- Preserve each agent's `sys.path` needs: before `exec_module`, insert the agent's own
  directory on `sys.path` so its local imports and `deck.csv` discovery still work
  (mirror what `_load_rules_agent` does today).
- Cache loaded modules so each agent is imported at most once per process.

### Deck resolver

Return a `list[int]` for each opponent, normalized across sources:

- **CSV** (`"...deck.csv"`, `"...Deck.csv"`):
  `[int(l) for l in open(path).read().splitlines() if l.strip()]`.
- **Inline** (`"inline:DECK"`): load the module (via the loader above) and read
  `getattr(module, "DECK")`.
- **`"FULL_DECK"`**: return `FULL_DECK` imported from `features.py`.

### Result of this part

A function like `resolve_opponent(name) -> {policy, deck}` (or two functions,
`load_policy(name)` / `load_deck(name)`) that later parts call. `policy` is: the agent
module's `agent` callable for file agents, `random_agent` for `random`, and a sentinel
for `self` (the frozen snapshot is created in the training loop, not here).

## Data

Reads agent module files and deck sources under `_parent`. Writes nothing to disk.

## Interfaces / seams

- Consumes `FULL_DECK` from `features.py` and `random_agent` from `random_agent.py`.
- Produces the resolvers that `09b` (dispatch) and `09d` (validation) call.

## Validation steps

Write a standalone check (a `test_opponents.py` unit test or a `__main__` probe in the
new module — match the repo's existing `test_features.py` style):

1. **Simultaneous load without collision.** Load `ceruledge_rules`, `clefable`, and
   `alakazam` (all from files named `main.py`) in the same process. Assert all three
   modules are distinct objects and each exposes a callable `agent`. Assert
   `sys.modules` does **not** key any of them under `"main"`.
2. **Deck resolution.** Resolve every opponent's deck. Assert each is a non-empty
   `list[int]`; assert the exact counts observed in the repo (all three CSVs = 60
   entries — note `wc -l` reports 59 for Ceruledge because its last line lacks a
   trailing newline; `splitlines()` yields 60 — and Lucario's inline `DECK` = 60).
   Assert `FULL_DECK` is returned for `random` and `self`.
3. **Casing trap.** Confirm the Alakazam entry resolves `Deck.csv` (capital D) and that a
   deliberately wrong-cased path raises a clear error (guards the Linux-cluster case).
4. **Idempotent caching.** Load the same agent twice; assert the second call returns the
   cached module (identity equality), not a re-exec.

## Success conditions

- All four file agents load in one process with no module-cache collision; each `agent`
  is callable.
- Every registry deck resolves to a `list[int]` of the expected length.
- The check script/test runs green with no NaNs, no import side-effect errors, and no
  reliance on `import_module("main")`.

## Out of scope

- Any use of these resolvers inside `collect_episode` or `battle_start` (that is `09b`).
- Sampling, CLI, validation-at-startup, metrics (later parts).
