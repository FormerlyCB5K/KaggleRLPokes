"""The reported 2,370,259-parameter engine-native policy network."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import torch
import torch.nn.functional as F
from torch import nn

from .spec import (
    ATTACK_VOCAB_SIZE,
    CARD_VOCAB_SIZE,
    EFFECT_WIDTH,
    LIVE_NUMERIC_WIDTH,
    MATCH_WIDTH,
    MAX_TOKENS,
    MODEL_WIDTH,
    N_OPTION_TYPES,
    N_REGISTERS,
    N_ROLES,
    OPTION_NUMERIC_WIDTH,
    Role,
    OptionKind,
)
from .tables import FrozenTables


@dataclass(frozen=True)
class ModelConfig:
    d_model: int = MODEL_WIDTH
    n_layers: int = 4
    n_heads: int = 4
    d_ff: int = 448
    d_stat: int = 32
    d_eff: int = 48
    d_num: int = LIVE_NUMERIC_WIDTH
    n_registers: int = N_REGISTERS
    dropout: float = 0.0
    d_card: int = 64  # Deliberately dead, retained for friend-checkpoint compatibility.


@dataclass(frozen=True)
class PolicyOutput:
    logits: torch.Tensor
    incl: torch.Tensor
    value: torch.Tensor
    value_fog: torch.Tensor


class SharedCardRep(nn.Module):
    """Learned projections over frozen, non-persistent mechanical buffers."""

    def __init__(self, config: ModelConfig, tables: FrozenTables) -> None:
        super().__init__()
        tables.validate()
        self.provisional = tables.provisional
        self.register_buffer("STAT", tables.stat.clone(), persistent=False)
        self.register_buffer("ATK", tables.attack.clone(), persistent=False)
        self.register_buffer("ABL", tables.ability.clone(), persistent=False)
        self.register_buffer("PLAY", tables.play.clone(), persistent=False)
        self.register_buffer("PRIZE", tables.prize.clone(), persistent=False)
        self.register_buffer(
            "ATTACK_SLOT", tables.attack_slot.clone(), persistent=False
        )

        self.stat_proj = nn.Linear(self.STAT.shape[-1], config.d_stat)
        self.eff_proj = nn.Linear(EFFECT_WIDTH, config.d_eff)
        static_width = config.d_stat + 1 + 3 * config.d_eff
        self.card_proj = nn.Linear(static_width, config.d_model)

    def static_table(self) -> torch.Tensor:
        stat = self.stat_proj(self.STAT)
        effect_input = torch.stack(
            (self.ATK[:, 0], self.ATK[:, 1], self.ABL), dim=1
        )
        effects = self.eff_proj(effect_input).flatten(1)
        return self.card_proj(torch.cat((stat, self.PRIZE, effects), dim=-1))

    def option_effect(
        self,
        option_type: torch.Tensor,
        card_id: torch.Tensor,
        attack_id: torch.Tensor,
    ) -> torch.Tensor:
        card_id = card_id.remainder(CARD_VOCAB_SIZE)
        attack_id = attack_id.remainder(ATTACK_VOCAB_SIZE)
        slot = F.embedding(
            attack_id, self.ATTACK_SLOT.unsqueeze(-1)
        ).squeeze(-1)
        attack_index = card_id * 2 + slot
        attack_effect = F.embedding(attack_index, self.ATK.flatten(0, 1))
        ability_effect = F.embedding(card_id, self.ABL)
        play_effect = F.embedding(card_id, self.PLAY)

        out = torch.zeros_like(attack_effect)
        is_attack = option_type == int(OptionKind.ATTACK)
        is_ability = (option_type == int(OptionKind.ABILITY)) | (
            option_type == int(OptionKind.SKILL)
        )
        is_play = (
            (option_type == int(OptionKind.PLAY))
            | (option_type == int(OptionKind.CARD))
            | (option_type == int(OptionKind.TOOL_CARD))
            | (option_type == int(OptionKind.ENERGY_CARD))
        )
        out = torch.where(is_attack.unsqueeze(-1), attack_effect, out)
        out = torch.where(is_ability.unsqueeze(-1), ability_effect, out)
        return torch.where(is_play.unsqueeze(-1), play_effect, out)


class DeckFiLM(nn.Module):
    def __init__(self, width: int) -> None:
        super().__init__()
        self.to_gb = nn.Linear(width, 2 * width)
        nn.init.zeros_(self.to_gb.weight)
        nn.init.zeros_(self.to_gb.bias)

    def forward(self, board: torch.Tensor, condition: torch.Tensor) -> torch.Tensor:
        raw_gamma, beta = self.to_gb(condition).chunk(2, dim=-1)
        gamma = torch.tanh(raw_gamma)
        return (1.0 + gamma).unsqueeze(1) * board + beta.unsqueeze(1)


class EngineNativeNet(nn.Module):
    """Exact reported Python network, with oracle inputs optional."""

    def __init__(
        self,
        config: ModelConfig | None = None,
        tables: FrozenTables | None = None,
    ) -> None:
        super().__init__()
        self.config = config or ModelConfig()
        tables = tables or FrozenTables.placeholder()
        d = self.config.d_model

        self.card = SharedCardRep(self.config, tables)
        self.role_emb = nn.Embedding(N_ROLES, d)
        self.num_proj = nn.Linear(self.config.d_num, d)
        self.deckzone_proj = nn.Linear(4, d)
        self.deck_film = DeckFiLM(d)
        self.glob_proj = nn.Linear(MATCH_WIDTH, d)

        layer = nn.TransformerEncoderLayer(
            d_model=d,
            nhead=self.config.n_heads,
            dim_feedforward=self.config.d_ff,
            dropout=self.config.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(
            layer,
            num_layers=self.config.n_layers,
            enable_nested_tensor=False,
        )
        self.out_norm = nn.LayerNorm(d)

        self.opt_type_emb = nn.Embedding(N_OPTION_TYPES, d)
        self.opt_eff_proj = nn.Linear(EFFECT_WIDTH, d)
        self.optnum_proj = nn.Linear(OPTION_NUMERIC_WIDTH, d)
        self.optent_proj = nn.Linear(d, d)

        self.tool_gate = nn.Linear(d, d, bias=False)
        self.senergy_gate = nn.Linear(d, d, bias=False)
        nn.init.zeros_(self.tool_gate.weight)
        nn.init.zeros_(self.senergy_gate.weight)

        head_width = 3 * d
        self.score = nn.Sequential(
            nn.Linear(head_width, d),
            nn.GELU(),
            nn.Linear(d, 1),
        )
        self.incl = nn.Sequential(
            nn.Linear(head_width, d),
            nn.GELU(),
            nn.Linear(d, 1),
        )
        self.value = nn.Sequential(
            nn.Linear(d, d),
            nn.GELU(),
            nn.Linear(d, 1),
        )

        self.ora_zone_emb = nn.Embedding(8, d)
        self.ora_proj = nn.Linear(d, d)
        nn.init.zeros_(self.ora_proj.weight)
        nn.init.zeros_(self.ora_proj.bias)

        self.registers = nn.Parameter(
            torch.empty(self.config.n_registers + 1, d)
        )
        nn.init.normal_(self.registers, mean=0.0, std=0.02)
        self.no_entity = nn.Parameter(torch.zeros(d))

    @staticmethod
    def _card_lookup(card_id: torch.Tensor, table: torch.Tensor) -> torch.Tensor:
        return F.embedding(card_id.remainder(CARD_VOCAB_SIZE), table)

    def forward(self, batch: Mapping[str, torch.Tensor]) -> PolicyOutput:
        card_table = self.card.static_table()
        tok_card_id = batch["tok_card_id"].to(torch.int64)
        tok_role = batch["tok_role"].to(torch.int64)
        tok_num = batch["tok_num"].to(card_table.dtype)
        tok_mask = batch["tok_mask"].to(torch.bool)
        deck_ids = batch["deck_ids"].to(torch.int64)
        deck_zone = batch["deck_zone"].to(card_table.dtype)

        deck_reps = self._card_lookup(deck_ids, card_table)
        deck_reps = deck_reps + self.deckzone_proj(deck_zone)
        deck_mask = (deck_ids > 0).unsqueeze(-1).to(deck_reps.dtype)
        deck_pooled = (deck_reps * deck_mask).sum(dim=1) / deck_mask.sum(
            dim=1
        ).clamp(min=1.0)

        board = self._card_lookup(tok_card_id, card_table)
        board = board + self.role_emb(tok_role) + self.num_proj(tok_num)

        tool_id = batch["tok_tool_id"].to(torch.int64)
        has_tool = (tool_id > 0).unsqueeze(-1).to(board.dtype)
        board = board + self.tool_gate(
            self._card_lookup(tool_id, card_table)
        ) * has_tool

        senergy_id = batch["tok_senergy_id"].to(torch.int64)
        has_senergy = (senergy_id > 0).unsqueeze(-1).to(board.dtype)
        board = board + self.senergy_gate(
            self._card_lookup(senergy_id, card_table)
        ) * has_senergy
        board = self.deck_film(board, deck_pooled)

        deck_token = deck_pooled + self.role_emb.weight[int(Role.DECK)]
        glob_token = self.glob_proj(batch["glob"].to(board.dtype))
        glob_token = glob_token + self.role_emb.weight[int(Role.GLOBAL)]
        registers = self.registers.unsqueeze(0).expand(board.shape[0], -1, -1)
        sequence = torch.cat(
            (
                board,
                deck_token.unsqueeze(1),
                glob_token.unsqueeze(1),
                registers,
            ),
            dim=1,
        )
        extras_live = torch.ones(
            board.shape[0],
            2 + self.config.n_registers + 1,
            dtype=torch.bool,
            device=board.device,
        )
        padding_mask = ~torch.cat((tok_mask, extras_live), dim=1)
        encoded = self.out_norm(
            self.encoder(sequence, src_key_padding_mask=padding_mask)
        )
        board_encoded = encoded[:, :MAX_TOKENS]
        summary = encoded[:, -1]

        opt_type = batch["opt_type"].to(torch.int64)
        opt_card = batch["opt_card"].to(torch.int64)
        opt_target = batch["opt_tgt"].to(torch.int64)
        opt_attack = batch["opt_attack"].to(torch.int64)
        option_effect = self.card.option_effect(
            opt_type, opt_card, opt_attack
        )

        no_entity = self.no_entity.view(1, 1, -1).expand(
            board.shape[0], 1, -1
        )
        entity_bank = torch.cat((board_encoded, no_entity), dim=1)
        opt_ent = batch["opt_ent"].to(torch.int64)
        opt_ent = torch.where(
            (opt_ent >= 0) & (opt_ent < MAX_TOKENS),
            opt_ent,
            torch.full_like(opt_ent, MAX_TOKENS),
        )
        entity = torch.gather(
            entity_bank,
            1,
            opt_ent.unsqueeze(-1).expand(-1, -1, self.config.d_model),
        )

        option = (
            self.opt_type_emb(opt_type)
            + self._card_lookup(opt_card, card_table)
            + self._card_lookup(opt_target, card_table)
            + self.opt_eff_proj(option_effect)
            + self.optnum_proj(batch["opt_num"].to(board.dtype))
            + self.optent_proj(entity)
        )
        expanded_summary = summary.unsqueeze(1).expand_as(option)
        combined = torch.cat(
            (expanded_summary, option, expanded_summary * option), dim=-1
        )
        logits = self.score(combined).squeeze(-1)
        incl = self.incl(combined).squeeze(-1)
        option_mask = batch["opt_mask"].to(torch.bool)
        logits = logits.masked_fill(~option_mask, float("-inf"))
        incl = incl.masked_fill(~option_mask, -30.0)

        value_input = summary
        if "ora_id" in batch:
            ora_id = batch["ora_id"].to(torch.int64)
            ora_zone = batch["ora_zone"].to(torch.int64).clamp(0, 7)
            ora_mask = batch["ora_mask"].to(torch.bool)
            oracle = self._card_lookup(ora_id, card_table)
            oracle = oracle + self.ora_zone_emb(ora_zone)
            mask = ora_mask.unsqueeze(-1).to(oracle.dtype)
            oracle_pool = (oracle * mask).sum(dim=1) / mask.sum(
                dim=1
            ).clamp(min=1.0)
            value_input = summary + self.ora_proj(oracle_pool)
            value_fog = self.value(summary.detach()).squeeze(-1)
            value = self.value(value_input).squeeze(-1)
        else:
            value = self.value(value_input).squeeze(-1)
            value_fog = value.detach()
        return PolicyOutput(
            logits=logits,
            incl=incl,
            value=value,
            value_fog=value_fog,
        )

    def parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters())

    def parameter_ledger(self) -> dict[str, int]:
        modules: dict[str, nn.Module | nn.Parameter] = {
            "card": self.card,
            "role_emb": self.role_emb,
            "num_proj": self.num_proj,
            "deckzone_proj": self.deckzone_proj,
            "deck_film": self.deck_film,
            "glob_proj": self.glob_proj,
            "encoder": self.encoder,
            "out_norm": self.out_norm,
            "opt_type_emb": self.opt_type_emb,
            "opt_eff_proj": self.opt_eff_proj,
            "optnum_proj": self.optnum_proj,
            "optent_proj": self.optent_proj,
            "tool_gate": self.tool_gate,
            "senergy_gate": self.senergy_gate,
            "score": self.score,
            "incl": self.incl,
            "value": self.value,
            "ora_zone_emb": self.ora_zone_emb,
            "ora_proj": self.ora_proj,
            "registers": self.registers,
            "no_entity": self.no_entity,
        }
        ledger: dict[str, int] = {}
        for name, item in modules.items():
            if isinstance(item, nn.Parameter):
                ledger[name] = item.numel()
            else:
                ledger[name] = sum(p.numel() for p in item.parameters())
        return ledger
