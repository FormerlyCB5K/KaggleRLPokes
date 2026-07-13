# Human Review — ambiguous tagging calls for the user

Format: card id | name | text | question.

## From round 0 (tag_audit_100.md)

- 284 | Larvitar | "Flip a coin. If heads, discard an Energy from your opponent's Active Pokémon." | `discard_energy` currently fires on BOTH self-cost discards ("discard 2 Energy from this Pokémon") and opponent energy denial like this — should the tag mean only self-discard (restrict regex with "from this Pokémon"), only denial, or both? Affects several cards.

## From round 1 (round-1-report.md)

- 142 | Genesect | "If this Pokémon has a Pokémon Tool attached, your opponent can't play any {ACE SPEC} cards from their hand." | ACE-SPEC lock is a partial item lock, but the ABILITY block has no item_lock field (only attacks have one, and the global flag tracks Budew/Frillish/Tyranitar). Ignore, or extend the global item-lock check?
- 385 | Arven's Toedscruel | "Switch in 1 of your opponent's Benched Pokémon to the Active Spot." (attack) | Gust-as-attack: the ATTACK block has no gust field. Ignore, or borrow a field / add to overrides some other way?
- 463 | Team Rocket's Murkrow | "Choose 1 of your opponent's Active Pokémon's attacks. During your opponent's next turn, that Pokémon can't use that attack." | Partial attack lock (one attack, not all) — should this set `cubchoo`?
- retreat-lock family: 52 Wugtrio ex ("the Defending Pokémon can't retreat"), 993 Orthworm ex, 1012 Ariados | "Can't retreat" effects recur but no tag exists for them. Worth a tag/override convention, or ignore?

## From round 2 (round-2-report.md)

- 480 Servine (+ likely others) | ATK1 effect text is untranslated JAPANESE in EN_Card_Data.csv ("コインを1回投げオモテなら…" = flip 1 coin, paralyze). | A handful of CSV rows carry Japanese text, so English regex tags nothing. Data-quality issue, not a regex bug. Ignore, patch the CSV, or hard-code these cards?
- 386 Cornerstone Mask Ogerpon (non-ex) | Seed override gives it an `immunity` ability it does not actually have (only the ex, 117, has Cornerstone Stance). | Confirm the seed should be corrected to remove 386 (also in override-worklist).
- 106 Palafin | "search your deck for a Palafin ex and switch it with this Pokémon" → tagged `search: 1`. | Correct by the "Search your deck" trigger, but it's really a self-evolve/switch tutor. Leave as search, or exclude?
- free-switch abilities: 847 Linoone, 924 Meowscarada ("Switch this Pokémon with your Active Pokémon") | Should self-repositioning free-switch abilities set the `switch` tag (which spec frames as retreat-reduction / free switching)? Currently untagged. (Applied in round 3 — now tagged; confirm this was wanted.)

## From round 4 (round-4-report.md)

- retaliation abilities (Rocky-Helmet style): 255 Maractus "**put** 6 damage counters on the Attacking Pokémon" (tagged `damage: 60`) vs 688 Spiritomb / 896 Mega Scrafty ex / 993 Orthworm ex / 882 TR Dugtrio "**place** N … on the Attacking Pokémon" (untagged). | Inconsistent because I kept the ability-damage verb as "put" only — adding "place" would tag all retaliation BUT also mis-tag 834 Toxtricity ("place 2 counters on that Pokémon" = your OWN benched Pokémon, a self-cost). DECISION NEEDED: (a) leave as-is (put tagged, place not), (b) tag all retaliation as `damage` and accept/override the Toxtricity self-FP, or (c) tag NO retaliation (also drop Maractus). Retaliation on an OPPONENT Pokémon is useful "attacking it is costly" signal for our agent.
