Ceruledge Agent Architecture — Auditor's Reference
Scope. Fine-grained description of every architecture/design choice in the two Ceruledge-deck agents built so far:

Ceruledge-RL/ — a PPO-trained neural policy (primary deliverable).
Ceruledge-Agent/ — a hand-written rules-based agent (standalone submission and RL training opponent).
Written so a reviewer with no prior exposure can reconstruct what the code intends, verify what it actually does, and find the sharp edges. PPO-math correctness lives in PPO_AUDIT.md; this cross-references rather than repeats it, and adds architecture-level findings that audit didn't cover.

Convention. Shapes/constants are verbatim from source. Where a comment disagrees with code, it's flagged [AUDIT] — highest-value checks.

1. System overview
1.1 Component map
File	Role
Ceruledge-RL/model.py	Policy+value net (CeruledgePolicy): two-stage actor, shared encoder, single critic.
Ceruledge-RL/features.py	Observation → input tensors; per-game GameStateTracker.
Ceruledge-RL/actions.py	Maps net outputs ↔ engine option indices; Stage 1 categorisation, Stage 2 scoring, sub-selection.
Ceruledge-RL/train.py	PPO loop: rollout, GAE, update, logging, checkpoint; setup/IS_FIRST heuristics.
Ceruledge-RL/random_agent.py	Uniform-random legal-action opponent.
Ceruledge-Agent/main.py	Rules-based priority-list agent.
Ceruledge-Agent/deck.csv	60-card decklist (loaded at import).
1.2 Game-engine interface (cg_download)
All agents use: battle_start(deck_a, deck_b)→(obs_dict, start_data), battle_select(list[int])→obs_dict, battle_finish(). to_observation_class wraps the dict. Each decision arrives as obs.select with a context (MAIN, SETUP_*, TO_HAND, DISCARD, SWITCH, TO_ACTIVE, IS_FIRST, …), an option list (each with type, area/inPlayArea, index fields), and minCount/maxCount. The agent returns option indices. The whole architecture is organised around this contract.

[AUDIT — engine constraint] cg_download is not usable from child processes (fork or spawn) — parallel multiprocessing.Pool collection was abandoned (workers hang in battle_start). Collection is strictly sequential; future parallelism must isolate the engine at a subprocess boundary.

2. Two-stage action abstraction
Raw option lists are too unstructured to learn over (count/meaning changes each turn), so each MAIN decision factorises into:

Stage 1 — what kind: fixed vocabulary of 19 categories (N_ACTIONS=19). One logit per category; illegal masked; one chosen.
Stage 2 — which target: if the category has >1 concrete option, a dot-product scorer ranks candidates.
Non-MAIN decisions (setup, discard, search, switch, promote) use separate context-specific logic, not the Stage 1 head.

2.1 Stage 1 vocabulary (model.py)
ID	Constant	Meaning
0	ACTION_PLAY_CERULEDGE	Play/Evolve Ceruledge ex
1	ACTION_PLAY_CHARCADET	Play Charcadet
2	ACTION_PLAY_SOLROCK	Play Solrock
3	ACTION_PLAY_LUNATONE	Play Lunatone
4	ACTION_PLAY_DRILBUR	Play Drilbur
5	ACTION_PLAY_NIGHT_STRETCHER	Play Night Stretcher
6	ACTION_PLAY_BLENDER	Play Brilliant Blender
7	ACTION_PLAY_FIGHTING_GONG	Play Fighting Gong
8	ACTION_PLAY_ULTRA_BALL	Play Ultra Ball
9	ACTION_PLAY_POKE_PAD	Play Poké Pad
10	ACTION_PLAY_BOSS_ORDERS	Play Boss's Orders
11	ACTION_PLAY_EG	Play Explorer's Guidance
12	ACTION_PLAY_CARMINE	Play Carmine
13	ACTION_ATTACH_FIRE	Attach Fire Energy
14	ACTION_ATTACH_FIGHTING	Attach Fighting Energy
15	ACTION_RETREAT	Retreat active
16	ACTION_ATTACK	Attack
17	ACTION_LUNATONE_ABILITY	Lunatone "Lunar Cycle"
18	ACTION_PASS	End turn
Vocabulary is deck-specific, not general PTCG.

3. Feature extraction (features.py)
extract_features(obs, our_idx, tracker) → (pokemon_tensor, zone_tensor, global_tensor).

3.1 Deck
Both players use the same 60-card FULL_DECK — training is a mirror match. 15 unique IDs/counts: Ceruledge ex(320)×4, Charcadet(796)×4, Solrock(676)×2, Lunatone(675)×2, Drilbur(81)×1, Fire(2)×7, Fighting(6)×13, Night Stretcher(1097)×4, Brilliant Blender(1128)×1, Fighting Gong(1142)×4, Ultra Ball(1121)×4, Poké Pad(1152)×3, Boss's Orders(1182)×3, Explorer's Guidance(1185)×4, Carmine(1192)×4.

3.2 Pokémon tensor — (12, 12)
12 slots: our active(1), our bench(5), opp active(1), opp bench(5). Empty = zeros. Occupied = 12 floats: species one-hot[5]; hp_max÷270; hp_curr÷270; fire_e÷4; fight_e÷4; retreat=min(cost,2)/2; dmg÷410 (Ceruledge=30+20×energy_in_discard, else static: Solrock 70/Lunatone 50/Drilbur 20); can_atk (required energy type present).

[AUDIT — feature bug #1] energy_in_discard is computed once from our discard (features.py:256) and applied to every slot including opponent Pokémon (:272,276) — opponent Ceruledge damage feature uses our discard.
[AUDIT — feature bug #2] _encode_pokemon(poke, our_ps, energy_in_discard) never uses our_ps — dead param (fixing it would also fix #1).
[AUDIT — coarse] can_atk checks only that ≥1 energy of the required type is attached, not full cost; Lunatone (req=None) is 1.0 with any energy.
[AUDIT — stale comment] features.py:278 labels it (12,13); actually (12,12).

3.3 Zone tensor — (3, 16)
Words: hand, discard, prizes. Each = 15 normalised counts (count/DECK_COUNTS[card]) + 1 is_unknown. Hand/discard observable. Prizes hidden → [-1.0]×15+[1.0] until deducible.

3.4 Prize inference (GameStateTracker.infer_prizes)
By elimination on first full-deck search: prize_counts = Counter(FULL_DECK) − seen (hand+discard+in-play+attached energy+revealed deck). Latches (prizes_known). Other tracker fields: lunar_used, supporter_used (per-turn reset via new_turn, set from actions.py), _last_turn.

3.5 Global tensor — (14,)
our/opp prizes ÷6; deck ÷47; our/opp hand ÷10; energyAttached bool; lunar_used; supporter_used; Solrock+Lunatone-both-in-play bool; fire-in-hand ÷4; fighting-in-hand ÷4; #attackers(Ceruledge/Charcadet) ÷4; min(turn,10)/10; going-second (1.0 if firstPlayer!=our_idx, else 0.0, 0.5 unknown).

[AUDIT — stale comment] features.py:295 says "12 floats"; length is 14.

4. Network (model.py)
Shared Transformer encoder → one actor head (Stage 1), one dot-product scorer (Stage 2), one critic.

4.1 Dims
D_MODEL=64, N_HEADS=2, D_FF=128, N_LAYERS=2, N_WORDS=16 (12 pokemon+3 zones+1 global), N_WORD_TYPES=8, N_ACTIONS=19.

4.2 Forward (encode)
Three input MLPs → 64: pokemon_mlp 12→24→64 (per slot), pile_mlp 16→32→64 (per zone), global_mlp 14→28→64. Each is Linear→GELU→Linear (hidden 2×).
Concat → (B,16,64).
Add learned type embedding (type_embed, 8 types) indexed by fixed _WORD_TYPE_IDS: our-active(0), our-bench(1×5), opp-active(2), opp-bench(3×5), hand(4), discard(5), prizes(6), global(7) — encodes board role.
Transformer: 2 layers/2 heads, dim_feedforward=128, dropout=0.0, GELU, pre-norm (norm_first=True), batch_first=True, enable_nested_tensor=False. No positional encoding beyond type embedding (slot identity is implicitly positional via fixed word order).
Attention pooling: learned pool_query softmax-scores the 16 words → pooled (B,64).
Outputs words (B,16,64), pooled (B,64).

4.3 Heads
Stage 1 actor stage1_head: Linear(64→19) on pooled.
Critic value_head: Linear(64→1) on pooled.
Stage 2 scorer stage2_scores: dot product of pooled with each candidate; optionally appends learned stop_token for variable-length picks.
Pile encoder encode_pile_candidate: a card's 16-float zone vector through the same pile_mlp.
[AUDIT — init] Trained from scratch (random init) — no supervised pre-train / loaded value net. Early logits can be inf/NaN under masking; defended in §5.5.

5. Action mapping & training
5.1 Stage 1 legal set (build_action_map)
Walks the option list, classifies each legal option into one of 19 categories; keys = legal Stage 1 actions; a (19,) additive mask (0.0/−inf) is built from them.

5.2 Stage 2 targeting (select_main_stage2)
Attach fire/fighting & evolve Ceruledge → candidate vectors are transformer word vectors of the target slot (words[0] active, words[1+i] bench). Other multi-candidate categories currently use zeros(D_MODEL) placeholders. _stage2_pick_n does sequential dot-product selection (optional STOP).

5.3 Sub-selection (select_sub_action)
TO_HAND/DISCARD/DISCARD_ENERGY_CARD/SWITCH/TO_ACTIVE/ACTIVATE use dedicated handlers scoring via stage2_scores (Boss's Orders = opp bench words 7–11, retreat/promote = our bench 1–5, pile = encode_pile_candidate). In rollout these are greedy and their log-probs discarded.

[AUDIT — design limitation, cross-ref PPO_AUDIT] Stage-2/sub-selection log-probs are never recorded or recomputed, so stop_token, the Stage-2 dot-product path, and pile_mlp's scoring role get no direct policy gradient — only indirect gradient via the shared encoder. Consistent (old/new log-probs both Stage-1-only → valid ratio), but Stage 2 is undertrained.

5.4 Episode collection (collect_episode)
Both decks FULL_DECK. our_side/go_first alternate across episodes (ep%2, (ep//2)%2==0). Setup/IS_FIRST via train.py heuristics (_setup_active: Solrock→Charcadet→Lunatone→Drilbur; _setup_bench: Charcadet→Lunatone→Solrock→Drilbur; _answer_yes_no). A pending-step buffer holds each MAIN decision until the next value/terminal, then emits a Step. If a MAIN turn has no legal Stage-1 action, no step is recorded (avoids lp=0.0 invalid ratio). Reward: +1 win / −1 loss / 0 draw (result==our_side win, ==2 draw, else loss); optional PRIZE_REWARD shaping (default 0.0). Each Step stores pokemon/zones/glob/action/log_prob/value/reward/done and the per-step mask (legal set changes each turn; can't be recomputed at update time without replaying the engine).

5.5 PPO update / GAE
GAE γ=0.99, λ=0.95, bootstrap reset at done (verified in PPO_AUDIT). Clipped surrogate PPO_CLIP=0.2, per-batch advantage norm. Clipped value loss (CleanRL 0.5·max(unclipped²,clipped²)) with stored old values. Entropy over masked dist. Masks re-applied before every log-softmax so new_lp/old_lp share a distribution. NaN defence: nan_to_num(logits+mask, nan=−inf); non-finite loss skips the gradient step. Adam lr=3e-4, eps=1e-5, max_grad_norm=0.5, PPO_EPOCHS=4.

5.6 Hyperparameters (defaults; script may override)
Param	Default
EPISODES_PER_UPDATE	128 (raised from 16 — noisy env)
PPO_EPOCHS	4
PPO_CLIP	0.2
VALUE_LOSS_COEF	0.5 (effective vf 0.25)
ENTROPY_COEF	0.01
GAMMA/GAE_LAMBDA	0.99 / 0.95
MAX_GRAD_NORM	0.5
LR	3e-4 (eps 1e-5)
N_UPDATES	100 (script 300)
PRIZE_REWARD	0.0
USE_EPSILON_GREEDY/USE_STOCHASTIC_SAMPLING	False / False
ε decay is gated behind USE_EPSILON_GREEDY. Both switches off ⇒ deterministic argmax rollout — decide whether that's intended for noisy-env experiments (--use-stochastic-sampling recommended).

5.7 Device handling (recent fix — audit focus)
Collection on CPU, update on DEVICE:

model.eval(); model.cpu()
results = [collect_episode(model, …) for ep in range(EPISODES_PER_UPDATE)]
model.to(DEVICE)
ppo_update(model, optimizer, all_steps, advantages, returns, DEVICE)
Rationale: single-game inference is engine-bound; GPU only helps the batched update. Also sidesteps device-mismatch: several actions.py paths call stage2_scores/encode_pile_candidate directly with CPU feature tensors, so a wholly-CPU model during collection guarantees consistency. Verify no residual CPU-pinned tensors and that CPU self-play opponents never mix devices.

6. Opponents (train.py)
random — uniform legal indices respecting min/max.
rules — lazy import of Ceruledge-Agent/main.py, calls agent(); on exception prints and falls back to random. (Failed imports aren't cached → a broken import re-raised every call; deck.csv path recently fixed to resolve relative to main.py.)
self — frozen deepcopy on CPU, refreshed every SELF_PLAY_UPDATE_EVERY (50), acts greedily; no Step recorded.
7. Rules-based agent (Ceruledge-Agent/main.py)
Deterministic priority list — first legal action wins. Decklist from deck.csv (module-relative, /kaggle_simulations/agent/ fallback).

MAIN order (3.1–3.27): establish board (Drilbur→Lunatone→Solrock≤2→Charcadet until line≥3→evolve Ceruledge) → Lunar Cycle → items (Blender→Gong→Pad) → energy attach (fighting→Solrock; fire→Ceruledge active-then-bench; generic→active when bench attacker ready) → Night Stretcher recovery chain + Ultra Ball (_ultra_ball_playable excess logic) → positioning (retreat into ready attacker; Boss's Orders snipe) → draw (EG/Carmine when deck>8) → late attach → attack → end.

Sub-selection dispatched in agent() by match ctx: TO_HAND routes by effect.id to per-card selectors (_ns_to_hand, _ub_to_hand, _gong_to_hand, _pad_to_hand, _eg_to_hand with a 1–26 priority table, _gather_strength_to_hand); DISCARD→_bb_discard (Blender thinning steps A–D)/Drilbur/_ub_discard; SWITCH→Boss's Orders highest-HP KO-able / retreat best attacker; TO_ACTIVE→_promote_after_ko; ACTIVATE→YES; else _greedy. This agent is both a baseline submission and the rules opponent, so its correctness affects RL results when selected.

8. Consolidated audit focus (ranked)
PPO correctness — read PPO_AUDIT.md (4 bugs fixed; GAE verified; minor second-pass items).
Stage-2 has no direct policy gradient (§5.3).
Opponent Ceruledge damage uses our discard + dead our_ps param (§3.2).
Exploration off by default in a noisy env (§5.6).
Device round-trip after CPU-collect/GPU-update split (§5.7).
Sequential collection is a hard engine constraint (§1.2).
Cosmetic stale comments in features.py.
9. Run / smoke tests
Inference: python smoke_test_ceruledge_rl.py (5 policy-vs-random games) — passes locally.
Full loop: python Ceruledge-RL/train.py --episodes-per-update 4 --n-updates 2 --log-every 1 --no-wandb --out-dir <tmp>; add --opponent self|rules.
Cluster: Ceruledge-RL/submit-batch-ceruledge-ppo.sh (SLURM, 1 GPU, sequential CPU collection, wandb optional, self-requeue).