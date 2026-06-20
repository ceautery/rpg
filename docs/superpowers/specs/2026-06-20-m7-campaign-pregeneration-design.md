# M7 — Campaign Pre-Generation Design

**Date:** 2026-06-20  
**Status:** Approved

---

## Goal

Separate world-building from gameplay. Before the first turn, the orchestrator detects that no campaign exists and runs a pre-generation phase — producing a complete dungeon (rooms, connections, encounters, loot, traps, NPCs, quests) that gameplay reads from rather than generating live. This enables consistent DM behavior and faster scene transitions.

---

## 1. Campaign Config and Trigger

The user creates `campaign/config.json` before running:

```json
{
  "name": "The Sunken Vault",
  "theme": "undead crypt",
  "room_count": 10,
  "party_level": 3
}
```

At the top of `run.md`, the orchestrator checks whether `campaign/dungeon.json` exists:
- **Exists** → skip to normal gameplay (turn 1)
- **Missing** → enter the pre-generation phase, logging progress to `log/session.md`

`campaign/config.json` is user-owned. The four output files (`dungeon.json`, `npcs.json`, `quests.json`, `encounters.json`) are written by world-engine and DM during generation, then treated as read-only during gameplay.

---

## 2. Pre-Generation Pipeline (Three Dispatches)

### Dispatch 1 — World-engine: Structure

**Input:** `campaign/config.json`  
**Output:** `campaign/dungeon.json` (room graph only — no encounter content yet)

Each room gets:
- `id` (e.g. `"r01"`)
- `type`: one of `entrance`, `corridor`, `chamber`, `vault`, `boss`
- `connections`: array of room ids

### Dispatch 2 — World-engine: Population

**Input:** `campaign/dungeon.json` (structure) + `campaign/config.json` (party level for CR targeting)  
**Output:** appends to each room in `campaign/dungeon.json`; writes `campaign/encounters.json`

For each room, world-engine adds:
- `encounter.table_ref` — pointer into `encounters.json`
- `loot.table_ref` — pointer into `encounters.json`
- `trap` — trap entry or `null`

Uses `oracle.py` for SRD monster/item lookups (pinned to `srd-2024`). All random selections go through `dice.py`.

### Dispatch 3 — DM: Narrative

**Input:** fully populated `campaign/dungeon.json` + `campaign/config.json`  
**Output:** prose added to each room in `dungeon.json`; `campaign/npcs.json`; `campaign/quests.json`

DM writes:
- Pre-written `description` prose for each room (referencing what world-engine placed)
- Named NPCs with goals, personality, and location
- Quest tree with hooks, objectives, and rewards

After dispatch 3, pre-generation is complete and gameplay begins at turn 1.

---

## 3. Gameplay Changes

**Scene setup becomes a file read, not a dispatch.**

| | M6 | M7 |
|---|---|---|
| Scene setup | DM dispatch → writes `scene.json` | Read room from `dungeon.json` → copy to `scene.json` |
| Encounter content | DM/WE generate live | WE rolls on pre-generated table in `encounters.json` |
| NPC behavior | DM reasons freely | DM reads goals from `npcs.json` for context |
| Quest state | Tracked in `quest_log.json` | Objectives defined in `quests.json`; `completed` flags toggled on resolution |

DM is still dispatched for: adjudicating resolved turns, NPC dialogue/reactions, quest state updates.  
World-engine is still dispatched for all mechanical resolution (unchanged).

---

## 4. File Schemas

### `campaign/dungeon.json`
```json
[{
  "id": "r01",
  "type": "entrance",
  "connections": ["r02", "r03"],
  "description": "Stone steps descend into darkness...",
  "encounter": {"table_ref": "enc_r01"},
  "loot": {"table_ref": "loot_r01"},
  "trap": null
}]
```

### `campaign/encounters.json`
```json
{
  "enc_r01": [{"monster": "zombie", "count": 2, "cr": "1/4"}],
  "loot_r01": [{"item": "gold piece", "count": 10}]
}
```

### `campaign/npcs.json`
```json
[{
  "id": "npc_01",
  "name": "Sister Maren",
  "room": "r04",
  "goal": "recover the stolen relic",
  "disposition": "fearful"
}]
```

### `campaign/quests.json`
```json
[{
  "id": "q01",
  "title": "The Sunken Relic",
  "hook": "A priest begs the party to recover a stolen holy symbol.",
  "objectives": [
    {"id": "q01a", "desc": "Find the relic in the vault", "completed": false}
  ],
  "reward": "200 XP"
}]
```

`completed` flags on quest objectives are the only fields updated during gameplay.

---

## File Ownership

| File | Writer |
|---|---|
| `campaign/config.json` | User |
| `campaign/dungeon.json` | World-engine (dispatches 1 & 2), DM (dispatch 3) |
| `campaign/encounters.json` | World-engine (dispatch 2) |
| `campaign/npcs.json` | DM (dispatch 3) |
| `campaign/quests.json` | DM (dispatch 3) |

During gameplay, `campaign/*` files are read-only except for `completed` flag toggles on quest objectives (written by orchestrator).
