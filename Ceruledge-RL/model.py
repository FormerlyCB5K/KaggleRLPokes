"""
model.py — Ceruledge policy network (generalized encoder, specs/completed/02).

Architecture:
  4 input MLPs (our-Pokemon, opp-Pokemon, Zone, Global) → D_MODEL=64
  Type embedding (9 types, 23 words)
  2-layer Transformer encoder (2 heads, D_FF=128)
  Attention-weighted pooling → (64,)
  Stage 1 linear head → (N_ACTIONS,) logits
  Stage 2 dot-product scorer with learned STOP token
"""
import torch
import torch.nn as nn

D_MODEL  = 64
D_FF     = 128
N_HEADS  = 2
N_LAYERS = 2

N_OUR_POKEMON_FEATURES = 19
N_OPP_POKEMON_FEATURES = 75
N_ZONE_FEATURES        = 16
N_GLOBAL_FEATURES      = 24
N_POKEMON_SLOTS        = 9    # active + 8 bench slots, per player
N_WORDS                = 23   # 9 our + 9 opp pokemon + 4 zones + 1 global

# Word type IDs — differentiate board roles for the type embedding
# 0: our active      1: our bench (×8)
# 2: opp active      3: opp bench (×8)
# 4: hand            5: discard
# 6: deck            7: prizes
# 8: global
N_WORD_TYPES = 9

_WORD_TYPE_IDS: list[int] = (
    [0]       # our active
    + [1] * 8 # our bench
    + [2]     # opp active
    + [3] * 8 # opp bench
    + [4]     # hand
    + [5]     # discard
    + [6]     # deck
    + [7]     # prizes
    + [8]     # global
)  # length 23

# Stage 1 action vocabulary
ACTION_PLAY_CERULEDGE      = 0
ACTION_PLAY_CHARCADET      = 1
ACTION_PLAY_SOLROCK        = 2
ACTION_PLAY_LUNATONE       = 3
ACTION_PLAY_DRILBUR        = 4
ACTION_PLAY_NIGHT_STRETCHER= 5
ACTION_PLAY_BLENDER        = 6
ACTION_PLAY_FIGHTING_GONG  = 7
ACTION_PLAY_ULTRA_BALL     = 8
ACTION_PLAY_POKE_PAD       = 9
ACTION_PLAY_BOSS_ORDERS    = 10
ACTION_PLAY_EG             = 11   # Explorer's Guidance
ACTION_PLAY_CARMINE        = 12
ACTION_ATTACH_FIRE         = 13
ACTION_ATTACH_FIGHTING     = 14
ACTION_RETREAT             = 15
ACTION_ATTACK              = 16
ACTION_LUNATONE_ABILITY    = 17
ACTION_PASS                = 18

N_ACTIONS = 19


def _mlp(in_dim: int, out_dim: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(in_dim, in_dim * 2),
        nn.GELU(),
        nn.Linear(in_dim * 2, out_dim),
    )


class CeruledgePolicy(nn.Module):

    def __init__(self):
        super().__init__()

        # Input MLPs
        self.our_pokemon_mlp = _mlp(N_OUR_POKEMON_FEATURES, D_MODEL)  # 19→38→64
        self.opp_pokemon_mlp = _mlp(N_OPP_POKEMON_FEATURES, D_MODEL)  # 75→150→64
        self.pile_mlp        = _mlp(N_ZONE_FEATURES,        D_MODEL)  # 16→32→64 (shared, all 4 zones)
        self.global_mlp      = _mlp(N_GLOBAL_FEATURES,      D_MODEL)  # 24→48→64

        # Type embedding
        self.register_buffer(
            'type_ids',
            torch.tensor(_WORD_TYPE_IDS, dtype=torch.long),
        )
        self.type_embed = nn.Embedding(N_WORD_TYPES, D_MODEL)

        # Transformer encoder
        enc_layer = nn.TransformerEncoderLayer(
            d_model=D_MODEL,
            nhead=N_HEADS,
            dim_feedforward=D_FF,
            dropout=0.0,
            activation='gelu',
            batch_first=True,
            norm_first=True,
        )
        self.transformer = nn.TransformerEncoder(enc_layer, num_layers=N_LAYERS,
                                                  enable_nested_tensor=False)

        # Attention-weighted pooling query
        self.pool_query = nn.Parameter(torch.randn(D_MODEL) * 0.02)

        # Stage 1 policy head
        self.stage1_head = nn.Linear(D_MODEL, N_ACTIONS)

        # Value head (critic)
        self.value_head = nn.Linear(D_MODEL, 1)

        # Stage 2 STOP token (learned embedding, no MLP input)
        self.stop_token = nn.Parameter(torch.randn(D_MODEL) * 0.02)

    # ── Core encode ───────────────────────────────────────────────────────────

    def encode(
        self,
        our_pokemon: torch.Tensor,  # (B, 9, 19)
        opp_pokemon: torch.Tensor,  # (B, 9, 75)
        zones:       torch.Tensor,  # (B, 4, 16)
        glob:        torch.Tensor,  # (B, 24)
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Returns:
            words:  (B, 23, D_MODEL)  — all word vectors post-transformer
            pooled: (B, D_MODEL)      — attention-pooled summary
        """
        our_words   = self.our_pokemon_mlp(our_pokemon)            # (B, 9, 64)
        opp_words   = self.opp_pokemon_mlp(opp_pokemon)            # (B, 9, 64)
        zone_words  = self.pile_mlp(zones)                         # (B, 4, 64)
        glob_word   = self.global_mlp(glob).unsqueeze(1)           # (B, 1, 64)

        words = torch.cat([our_words, opp_words, zone_words, glob_word], dim=1)
        words = words + self.type_embed(self.type_ids)                  # (B, 23, 64)
        words = self.transformer(words)                                 # (B, 23, 64)

        scores  = (words * self.pool_query).sum(-1)                # (B, 23)
        weights = torch.softmax(scores, dim=-1).unsqueeze(-1)      # (B, 23, 1)
        pooled  = (words * weights).sum(dim=1)                     # (B, 64)

        return words, pooled

    # ── Stage 1 ───────────────────────────────────────────────────────────────

    def stage1_logits(self, pooled: torch.Tensor) -> torch.Tensor:
        """Logits over all N_ACTIONS. Shape: (B, N_ACTIONS)."""
        return self.stage1_head(pooled)

    # ── Stage 2 ───────────────────────────────────────────────────────────────

    def stage2_scores(
        self,
        pooled:       torch.Tensor,   # (D_MODEL,) or (B, D_MODEL)
        candidates:   torch.Tensor,   # (N, D_MODEL) or (B, N, D_MODEL)
        include_stop: bool = False,
    ) -> torch.Tensor:
        """
        Score each candidate via dot product with pooled state.
        Optionally appends the STOP token as the last candidate.
        Returns logits of shape (N,) or (B, N) — or +1 if include_stop.
        """
        squeezed = pooled.dim() == 1
        if squeezed:
            pooled     = pooled.unsqueeze(0)      # (1, D)
            candidates = candidates.unsqueeze(0)  # (1, N, D)

        if candidates.dim() == 2:
            candidates = candidates.unsqueeze(0).expand(pooled.shape[0], -1, -1)

        if include_stop:
            stop = self.stop_token.view(1, 1, D_MODEL).expand(pooled.shape[0], 1, D_MODEL)
            candidates = torch.cat([candidates, stop], dim=1)

        scores = (candidates * pooled.unsqueeze(1)).sum(-1)  # (B, N[+1])

        return scores.squeeze(0) if squeezed else scores

    def encode_pile_candidate(self, zone_vec: list[float]) -> torch.Tensor:
        """
        Encode a single Stage 2 candidate card (from deck/discard/hand)
        as a D_MODEL vector via pile_mlp.
        zone_vec is a 16-float vector from encode_card_as_zone().
        """
        t = torch.tensor(zone_vec, dtype=torch.float32).unsqueeze(0)
        return self.pile_mlp(t).squeeze(0)  # (D_MODEL,)

    def get_value(self, pooled: torch.Tensor) -> torch.Tensor:
        """State value estimate. Shape: (B,) or scalar."""
        return self.value_head(pooled).squeeze(-1)

    def forward(
        self,
        our_pokemon: torch.Tensor,
        opp_pokemon: torch.Tensor,
        zones:       torch.Tensor,
        glob:        torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Convenience forward for training.
        Returns: words (B,23,64), pooled (B,64), stage1_logits (B, N_ACTIONS), value (B,)
        """
        words, pooled = self.encode(our_pokemon, opp_pokemon, zones, glob)
        logits = self.stage1_logits(pooled)
        value  = self.get_value(pooled)
        return words, pooled, logits, value
