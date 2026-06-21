# Foundry VTT Module Importer — Design Spec

**Date:** 2026-06-21  
**Milestone:** M8  
**Scope:** `scripts/import_foundry.py` only. Session config menu (`start_session.py`) is a separate follow-up.

---

## Overview

A standalone Python script that reads a Foundry VTT module (zip or extracted directory) and writes the full `campaign/` file set, replacing the manual pre-generation flow. No LLM calls. No external dependencies beyond Python stdlib.

Target module format: Foundry v9/v10 NeDB (line-delimited JSON `.db` files).

---

## Invocation

```
python scripts/import_foundry.py path/to/module.zip
python scripts/import_foundry.py path/to/extracted-dir/
```

**Flags:**
- `--force` — skip clobber confirmation prompt

---

## Architecture: Seven Phases

### Phase 1 — Load

Parse all `.db` files from `data/` as JSONL. Build `_id`-keyed in-memory indexes for:
- `actors` — monsters and NPCs
- `journals` — narrative entries
- `items` — standalone items
- `folders` — organizational structure (used for context only)
- `scenes` — battle maps (primary room source)
- `tables` — rollable loot tables

### Phase 2 — Classify Actors

Split the 21 actors into two buckets:

**Monsters:** `data.details.cr` is set AND `token.disposition != 1`  
**NPCs:** `token.disposition == 1` (friendly) OR no CR present

### Phase 3 — Build Rooms (→ dungeon.json, config.json)

Each Foundry scene becomes one dungeon room, ordered by `navOrder`.

| Foundry field | dungeon.json field | Notes |
|---|---|---|
| scene `name` slugified | `id` (r01…rN) | sequential by navOrder |
| keyword heuristic (see below) | `type` | entrance/corridor/chamber/vault/boss |
| tokens present? | `room_type` | "combat" if hostile tokens; "social" if only friendly; "trap" not inferrable from Foundry data |
| linked journal, HTML stripped | `description` | falls back to scene `description` field |
| sequential chain | `connections` | Foundry has no room graph; defaults to linear |
| `"enc_<id>"` | `encounter` | populated in encounters.json |
| `"loot_<id>"` | `loot` | populated if loot tokens present |
| `null` | `trap` | not present in Foundry data model |
| `null` | `spotlight` | no equivalent |

**Room type keyword heuristic** (matched against scene name + linked journal heading):
- "entrance", "gate", "road" → `entrance`
- "hall", "corridor", "passage" → `corridor`
- "boss", "dragon", "lord", "chief" → `boss`
- "vault", "treasury", "store" → `vault`
- default → `chamber`

**config.json** is written from `world.json`: name ← title, theme ← first sentence of description, room_count ← scene count, party_level ← 3 (default; not present in Foundry data).

### Phase 4 — Build Encounters (→ encounters.json)

For each scene, group `tokens[]` by `actorId` and count instances. Each unique actor produces one entry in the room's encounter array.

**Standard monster entry:**
```json
{ "monster": "kobold", "count": 4, "cr": "1/8", "ac": 12, "hp": 5 }
```

**Custom monster entry** (name not in SRD oracle):
```json
{
  "monster": "booze-server-kobold",
  "count": 3,
  "cr": "1/8",
  "ac": 12,
  "hp": 5,
  "custom": true,
  "foundry_stats": {
    "abilities": { "str": 7, "dex": 15, "con": 9, "int": 8, "wis": 7, "cha": 8 },
    "speed": 30,
    "attacks": [
      { "name": "Dagger", "attack_bonus": 4, "damage": "1d4+2", "type": "piercing" }
    ]
  }
}
```

The `custom: true` flag tells the world-engine to fall back to `foundry_stats` when the oracle returns no match.

**Loot:** Item tokens on a scene → loot entries. If none present, writes a placeholder `{ "item": "gold", "amount_gp": 0 }` to keep the schema valid.

**Stat field mapping:**
- `cr` ← `data.details.cr`
- `ac` ← `data.attributes.ac.value` or `.flat`
- `hp` ← `data.attributes.hp.max`
- `speed` ← `data.attributes.movement.walk`
- `abilities` ← `data.abilities` (str/dex/con/int/wis/cha values)
- `attacks` ← embedded `items[]` filtered to `type` in ("weapon", "feat") with `actionType` set; map `name`, `data.attackBonus`, `data.damage.parts[0]`

### Phase 5 — Classify Journals (→ quests.json, foreshadowing.json, campaign/lore.json)

Any journal entry **not** referenced by a scene's `journal` field goes through keyword classification:

| Trigger keywords in name or content | Output |
|---|---|
| "quest", "mission", "objective", "reward", "bounty" | `quests.json` |
| "secret", "prophecy", "omen", "foreshadow", "portent" | `foreshadowing.json` |
| anything else | `campaign/lore.json` |

**quests.json mapping:**
- `id` ← `"q" + zero-padded index`
- `title` ← journal `name`
- `hook` ← first `<p>` content, HTML stripped
- `objectives` ← `<li>` elements if present; else `[{ "id": "q01_o1", "desc": "See DM notes", "completed": false }]`
- `reward` ← parse "xp"/"gp" patterns; default `{ "xp": 0, "gold": 0, "narrative": "" }`

**foreshadowing.json mapping:**
- `id` ← `"fs" + zero-padded index`
- `detail` ← first paragraph, HTML stripped
- `planted_in` / `pays_off_in` ← `null` (DM fills in)
- `payoff` / `dm_hint` ← remaining paragraphs joined

**lore.json** (new file, not part of existing schema — DM reference only):
```json
[{ "id": "lore_01", "title": "...", "content": "..." }]
```

### Phase 6 — Extract NPCs and Items (→ npcs.json, named_items.json)

**npcs.json:**
- `id` ← slugified name
- `name` ← actor `name`
- `room` ← id of scene where actor appears as a token (`null` if not placed)
- `goal` ← `data.details.biography.value` first sentence, HTML stripped
- `disposition` ← map token.disposition int: `1` → "friendly", `0` → "neutral", `-1` → "hostile"

**named_items.json:**
- `id` ← slugified name
- `name`, `type` ← item fields
- `in_room` ← `null` (standalone items.db entries are not placed in scenes)
- `description` ← `data.description.value`, HTML stripped
- `secret` ← `null`
- `investigation_dc` ← `null`
- `value` ← `data.price`

### Phase 7 — Write Outputs

**Clobber protection:** If `campaign/dungeon.json` exists and is non-empty, prompt:
```
Campaign data already exists in campaign/. Overwrite? [y/N]:
```
`--force` skips this prompt.

**Files always written:**
- `campaign/config.json`
- `campaign/dungeon.json`
- `campaign/encounters.json`
- `campaign/npcs.json`
- `campaign/named_items.json`
- `campaign/quests.json`
- `campaign/foreshadowing.json`

**Written only if content exists:**
- `campaign/lore.json`

**Summary printed on completion:**
```
Imported "Clash at the Kobold Cauldron"
  5 rooms, 21 actors (14 monsters / 7 NPCs), 6 items
  3 quests, 0 foreshadowing seeds, 11 lore entries
  Custom monsters: booze-server-kobold, cask-hauler-kobold, molten-ooze (flagged with foundry_stats)
  ⚠  connections defaulted to linear chain — review campaign/dungeon.json
  ⚠  party_level defaulted to 3 — no level data found in module
```

---

## World-Engine Change

The world-engine must be updated to handle `custom: true` monster entries in `encounters.json`. When an oracle lookup returns no match and the encounter entry has `custom: true`, read stats from `foundry_stats` directly instead of erroring.

---

## HTML Stripping

All rich text fields are stripped with: `re.sub(r'<[^>]+>', '', html).strip()`

No external dependencies. This is sufficient for extracting readable plain text from Foundry's journal HTML.

---

## Out of Scope

- Session config menu (`start_session.py`) — separate M8 follow-up
- Newer Foundry v11+ LevelDB format (`.ldb` files) — not needed for this module
- Image/audio assets — ignored entirely
- Trap extraction — not represented in Foundry data model
- Spotlight generation — requires DM judgment, not importable
- AI-assisted content enrichment — deliberately excluded; import is deterministic
