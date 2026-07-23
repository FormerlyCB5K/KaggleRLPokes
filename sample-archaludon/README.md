# sample-archaludon

Public rule-based Archaludon ex / Cinderace agent, taken verbatim (v6, 2026-06-27)
from the Kaggle notebook "A Sample Archaludon: 75% WR vs my 1300+ Starmie"
(`a-sample-archaludon-75-wr-vs-my-1300-starmie.ipynb`). Author reports 74.4% WR
over 1000 games vs their 1300+ leaderboard Starmie/Froslass submission.

Game plan: Cinderace Explosiveness start → turn-1 Turbo Flare energy to benched
Duraludon → evolve Archaludon ex (Assemble Alloy) → Metal Defender 220, with
Duraludon Raging Hammer as the alternate line. Includes matchup-specific
overrides (Crustle, Hop, Lucario, Alakazam, Starmie).

Used as a training-pool opponent for Ceruledge-RL — see
`Ceruledge-RL/specs/10-archaludon-opponent.md`. Logic is unmodified from the
source; the only change is a fallback import (`cg.api` → `cg_download.api`) so
the module loads in this repo as well as on Kaggle.
