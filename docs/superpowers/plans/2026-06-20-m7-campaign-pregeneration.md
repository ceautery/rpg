# M7 — Campaign Pre-Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a three-dispatch pre-generation pipeline that builds a complete campaign (dungeon graph, encounter/loot/trap tables, room prose, NPCs, quests) before gameplay, so scene setup becomes a file read rather than a DM dispatch.

**Architecture:** At boot, the orchestrator checks for `campaign/dungeon.json`; if absent, it runs three sequential dispatches (world-engine: structure → world-engine: population → DM: narrative) and logs progress to `log/session.md`. During gameplay, scene setup reads the pre-written room description from `campaign/dungeon.json`, passes the pre-selected encounter roster to the world-engine, and eliminates the DM SCENE_SETUP dispatch. All other dispatches (adjudication, resolution, coordination) are unchanged.

**Tech Stack:** Claude Code agent system (`run.md` orchestrator, `.claude/agents/*.md` subagents), `scripts/dice.py` (RNG), `scripts/oracle.py` (Open5e API, srd-2024), JSON state files.

## Global Constraints

- All randomness through `scripts/dice.py` only; content queries through `oracle.py --source srd-2024`
- Every file has exactly one writer per turn; pre-gen dispatches are sequential (no concurrent writes)
- `state/secret/` never passed to player agents or human
- `campaign/*` files are read-only during gameplay except `completed` flags on quest objectives
- No narrative language in world-engine output; no mechanical numbers in DM narration

---

## File Map

| File | Change | Owner after M7 |
|---|---|---|
| `campaign/config.json` | **Create** — user-editable campaign parameters | User |
| `campaign/.gitkeep` | **Create** — tracks empty directory in git | — |
| `campaign/dungeon.json` | **Created by agents** — room graph, then encounter refs, then prose | WE (dispatch 1+2), DM (dispatch 3) |
| `campaign/encounters.json` | **Created by agents** — encounter/loot/trap tables | World-engine |
| `campaign/npcs.json` | **Created by agents** — NPC roster | DM |
| `campaign/quests.json` | **Created by agents** — quest tree | DM; orchestrator toggles `completed` only |
| `.claude/agents/world-engine.md` | **Modify** — add PREGEN_STRUCTURE + PREGEN_POPULATE modes; add campaign/* write permission | — |
| `.claude/agents/dm.md` | **Modify** — add PREGEN_NARRATIVE mode; add campaign/* read+write permission | — |
| `run.md` | **Modify** — boot campaign check, 3 dispatch templates, updated scene setup, world.json current_room_id | — |
| `CLAUDE.md` | **Modify** — add campaign/* to ownership table | — |
| `DESIGN.md` | **Modify** — mark M7 complete | — |

---

### Task 1: Create campaign/config.json template

**Files:**
- Create: `campaign/config.json`
- Create: `campaign/.gitkeep`

**Interfaces:**
- Produces: `campaign/config.json` with keys `name`, `theme`, `room_count`, `party_level` — consumed by all three pre-gen dispatch templates

- [ ] **Step 1: Create the campaign directory and config template**

  Create `campaign/config.json` with this exact content:
  ```json
  {
    "name": "The Sunken Vault",
    "theme": "undead crypt",
    "room_count": 8,
    "party_level": 3
  }
  ```

- [ ] **Step 2: Create .gitkeep**

  ```bash
  touch /Users/curtis/dev/claude_projects/rpg/campaign/.gitkeep
  ```

- [ ] **Step 3: Verify**

  ```bash
  ls /Users/curtis/dev/claude_projects/rpg/campaign/
  # Expected: .gitkeep  config.json

  python3 -c "import json; d=json.load(open('campaign/config.json')); assert set(d)=={'name','theme','room_count','party_level'}; print('OK')"
  # Expected: OK
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add campaign/config.json campaign/.gitkeep
  git commit -m "feat(campaign): add config.json template for M7 pre-generation"
  ```

---

### Task 2: Add PREGEN_STRUCTURE mode to world-engine.md

**Files:**
- Modify: `.claude/agents/world-engine.md` — input section, write-permission section, new procedure block
- Modify: `run.md` — new dispatch template

**Interfaces:**
- Consumes: `campaign/config.json`
- Produces: `campaign/dungeon.json` — array of `{id, type, connections}` objects, no encounter/description fields yet

- [ ] **Step 1: Add campaign/* to world-engine write permissions**

  In `.claude/agents/world-engine.md`, find:
  ```
  ## What you may write (you are the single writer for these)
  - `state/rng_log.jsonl` (append-only; written by dice.py)
  - `state/public/map.txt`, `state/public/encounter.json` (mechanical fields: combatants, positions, initiative, turn pointer scaffold)
  - `state/secret/monsters.json` (true stat blocks, current/hidden HP, mechanical tactics flags)
  Do not write narrative fields or `party.json` applied-results — the orchestrator applies resolved deltas to the party.
  ```

  Replace with:
  ```
  ## What you may write (you are the single writer for these)
  - `state/rng_log.jsonl` (append-only; written by dice.py)
  - `state/public/map.txt`, `state/public/encounter.json` (mechanical fields: combatants, positions, initiative, turn pointer scaffold)
  - `state/secret/monsters.json` (true stat blocks, current/hidden HP, mechanical tactics flags)
  - `campaign/dungeon.json` (during PREGEN_STRUCTURE and PREGEN_POPULATE only)
  - `campaign/encounters.json` (during PREGEN_POPULATE only)
  Do not write narrative fields or `party.json` applied-results — the orchestrator applies resolved deltas to the party.
  ```

- [ ] **Step 2: Add PREGEN_STRUCTURE and PREGEN_POPULATE to the input section**

  In `.claude/agents/world-engine.md`, find:
  ```
  ## Input you will receive (from the orchestrator)
  - **GENERATE** — character creation request, or an encounter/scene setup request from the DM. Produce numbers, rosters, maps.
  - **RESOLVE** — a list of the DM's `mechanic_requests`. Roll and resolve each one.
  ```

  Replace with:
  ```
  ## Input you will receive (from the orchestrator)
  - **GENERATE** — character creation request, or an encounter/scene setup request from the DM. Produce numbers, rosters, maps.
  - **RESOLVE** — a list of the DM's `mechanic_requests`. Roll and resolve each one.
  - **PREGEN_STRUCTURE** — campaign config. Generate the dungeon room graph and write `campaign/dungeon.json`.
  - **PREGEN_POPULATE** — campaign config + `campaign/dungeon.json` (structure only). For each room, roll encounter rosters, loot, and trap data via `dice.py` and `oracle.py`. Append refs to `campaign/dungeon.json`; write full tables to `campaign/encounters.json`.
  ```

- [ ] **Step 3: Add PREGEN_STRUCTURE procedure block to world-engine.md**

  In `.claude/agents/world-engine.md`, after the existing `## Procedure` section (after line 63), add:

  ```markdown
  ## PREGEN_STRUCTURE procedure

  Read `campaign/config.json`. Generate exactly `room_count` rooms:

  - Room 1 type: `entrance`. Last room type: `boss`. Remaining rooms: roll 1d4 via `dice.py` per room — 1–2 = `corridor`, 3 = `chamber`, 4 = `vault`.
  - Connect rooms into a tree: each room connects to the previous one. Roll 1d6 per room (after the first two); on a 6, also add a connection back to a random earlier room (creating a loop). Use `dice.py` for every roll.

  Write `campaign/dungeon.json` as an array — only `id`, `type`, `connections` fields:
  ```json
  [
    {"id": "r01", "type": "entrance", "connections": ["r02", "r03"]},
    {"id": "r02", "type": "corridor", "connections": ["r01", "r04"]},
    {"id": "r03", "type": "vault",    "connections": ["r01"]},
    {"id": "r04", "type": "boss",     "connections": ["r02"]}
  ]
  ```

  Do not add `encounter`, `loot`, `trap`, or `description` fields — those come in later dispatches.

  Return: `{"mode": "PREGEN_STRUCTURE", "files_written": ["campaign/dungeon.json"], "rooms_generated": <N>}`

  ## PREGEN_POPULATE procedure

  Read `campaign/config.json` (for `party_level`) and `campaign/dungeon.json` (room graph). Build a table for each room. Collect all tables into `campaign/encounters.json` keyed by ref name, and rewrite `campaign/dungeon.json` adding `encounter`, `loot`, `trap` to each room. Do not add `description` — that is PREGEN_NARRATIVE's job.

  **Encounter table** (`enc_<id>`) — query `oracle.py` for monsters appropriate to room type and `party_level`:
  - `entrance`: empty encounter (patrol — 1–2 CR ¼ monsters). Roll count with `dice.py` (`1d2`).
  - `corridor`/`chamber`: 2–4 monsters at CR ≤ `party_level/2`. Roll count with `1d3+1`.
  - `vault`: 1 monster at CR = `party_level/2`, plus `1d2` lesser guards.
  - `boss`: 1 monster at CR = `party_level`. No roll needed for count.

  Example oracle query:
  ```bash
  python scripts/oracle.py creatures --where challenge_rating__lte=1 --source srd-2024 --fields name,challenge_rating,armor_class,hit_points
  ```
  Use `dice.py` to pick from the returned list by rolling `1dN` where N is the result count.

  **Loot table** (`loot_<id>`) — Roll `1d6` via `dice.py`:
  - 1–2: minor consumable (healing potion — query `oracle.py magic-items --where name__icontains=healing`)
  - 3–4: coins only — roll `2d10` gold
  - 5–6: no loot
  - Entrance room always has no loot regardless of roll.
  - Boss room always has `1d6 * 10` gold plus one magic item (query `oracle.py magic-items --source srd-2024 --fields name,rarity`; pick with `1dN`).

  **Trap** (`trap_<id>`) — Roll `1d6` via `dice.py`: 1–2 = trap present, 3–6 = none.
  - If present: roll DC = `1d4+10`, damage = `1d8`, save = `"dex"`.
  - Entrance and boss rooms: no trap.

  After building tables, rewrite `campaign/dungeon.json` adding refs to each room:
  ```json
  {"id": "r02", "type": "corridor", "connections": ["r01", "r04"],
   "encounter": {"table_ref": "enc_r02"}, "loot": {"table_ref": "loot_r02"},
   "trap": {"table_ref": "trap_r02"}}
  ```
  Rooms with no trap use `"trap": null`.

  Write `campaign/encounters.json`:
  ```json
  {
    "enc_r01": [{"monster": "skeleton", "count": 1, "cr": "1/4"}],
    "loot_r01": [],
    "enc_r02": [{"monster": "zombie", "count": 3, "cr": "1/4"}],
    "loot_r02": [{"item": "healing potion", "count": 1}],
    "trap_r02": {"dc": 13, "damage_die": "1d8", "save": "dex"}
  }
  ```

  Return: `{"mode": "PREGEN_POPULATE", "files_written": ["campaign/dungeon.json", "campaign/encounters.json"]}`
  ```

- [ ] **Step 4: Add pregen-structure dispatch template to run.md**

  In `run.md`, after the `**World-engine (resolve):**` template block (line ~205), add:

  ```
  **World-engine (pregen-structure):** model: sonnet
  ```
  Use the world-engine subagent. MODE: PREGEN_STRUCTURE.
  Config: <campaign/config.json contents>.
  Generate the dungeon room graph. Write campaign/dungeon.json with room ids, types, and connections only — no encounter data yet.
  ```
  ```

- [ ] **Step 5: Verify**

  ```bash
  grep -n "PREGEN_STRUCTURE\|PREGEN_POPULATE" .claude/agents/world-engine.md | wc -l
  # Expected: 6 or more (input section x2, procedure headings x2, body refs)

  grep -n "pregen-structure" run.md
  # Expected: 1 hit
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add .claude/agents/world-engine.md run.md
  git commit -m "feat(world-engine): add PREGEN_STRUCTURE and PREGEN_POPULATE modes"
  ```

---

### Task 3: Add pregen-populate dispatch template to run.md

**Files:**
- Modify: `run.md` — one new dispatch template

**Interfaces:**
- Consumes: `campaign/config.json`, `campaign/dungeon.json` (from PREGEN_STRUCTURE)
- Produces: (template only — agent produces `campaign/encounters.json` + enriched `campaign/dungeon.json` at runtime)

- [ ] **Step 1: Add pregen-populate dispatch template**

  In `run.md`, after the pregen-structure dispatch template added in Task 2, add:

  ```
  **World-engine (pregen-populate):** model: sonnet
  ```
  Use the world-engine subagent. MODE: PREGEN_POPULATE.
  Config: <campaign/config.json contents>. Dungeon structure: <campaign/dungeon.json contents>.
  Populate each room with encounter rosters, loot tables, and traps. Update campaign/dungeon.json with table refs and write campaign/encounters.json with the full tables.
  ```
  ```

- [ ] **Step 2: Verify**

  ```bash
  grep -n "pregen-structure\|pregen-populate" run.md
  # Expected: 2 hits, in order
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add run.md
  git commit -m "feat(run): add pregen-populate dispatch template"
  ```

---

### Task 4: Add PREGEN_NARRATIVE mode to dm.md

**Files:**
- Modify: `.claude/agents/dm.md` — read permission section, write permission section, input section, new procedure block
- Modify: `run.md` — new dispatch template

**Interfaces:**
- Consumes: `campaign/config.json`, `campaign/dungeon.json` (fully populated from Tasks 2–3)
- Produces: `campaign/dungeon.json` (with `description` in each room), `campaign/npcs.json`, `campaign/quests.json`

- [ ] **Step 1: Add campaign/* to DM read permissions**

  In `.claude/agents/dm.md`, find:
  ```
  ## What you may read
  - `state/public/*` (world, party, scene, map, encounter, quest_log)
  - `state/secret/*` (monsters' true stats, hidden traps, plot intentions) — this is yours to know
  - `log/session.md` for continuity
  ```

  Replace with:
  ```
  ## What you may read
  - `state/public/*` (world, party, scene, map, encounter, quest_log)
  - `state/secret/*` (monsters' true stats, hidden traps, plot intentions) — this is yours to know
  - `log/session.md` for continuity
  - `campaign/*` (dungeon, encounters, npcs, quests) — for PREGEN_NARRATIVE and for NPC/quest context during gameplay
  ```

- [ ] **Step 2: Add campaign/* to DM write permissions**

  In `.claude/agents/dm.md`, find:
  ```
  ## What you may write
  Nothing directly to public state. You return a structured directive (below); the orchestrator and world-engine act on it. You may write narrative fields you own under `state/secret/hidden.json` **only if** the orchestrator's prompt explicitly authorizes it this turn.
  ```

  Replace with:
  ```
  ## What you may write
  Nothing directly to public state during normal gameplay. You return a structured directive (below); the orchestrator and world-engine act on it. You may write narrative fields you own under `state/secret/hidden.json` **only if** the orchestrator's prompt explicitly authorizes it this turn.

  During **PREGEN_NARRATIVE** only: you write directly to `campaign/dungeon.json` (adding `description` to each room), `campaign/npcs.json`, and `campaign/quests.json`.
  ```

- [ ] **Step 3: Add PREGEN_NARRATIVE to the input section**

  In `.claude/agents/dm.md`, find:
  ```
  ## Input you will receive (from the orchestrator)
  A dispatch in one of two modes:
  - **SCENE_SETUP** — current world state + a goal ("the party enters the warren"). Produce a scene.
  - **ADJUDICATE** — the full set of player actions for this turn (initiative order included) + any resolved facts the world-engine has already returned. Produce intent + narration.
  ```

  Replace with:
  ```
  ## Input you will receive (from the orchestrator)
  A dispatch in one of three modes:
  - **SCENE_SETUP** — current world state + a goal ("the party enters the warren"). Produce a scene.
  - **ADJUDICATE** — the full set of player actions for this turn (initiative order included) + any resolved facts the world-engine has already returned. Produce intent + narration.
  - **PREGEN_NARRATIVE** — campaign config + fully populated `campaign/dungeon.json`. Write room descriptions, a full NPC roster, and a quest tree directly to `campaign/` files.
  ```

- [ ] **Step 4: Add PREGEN_NARRATIVE procedure block to dm.md**

  In `.claude/agents/dm.md`, after the existing `## Procedure` section (after line 91), add:

  ```markdown
  ## PREGEN_NARRATIVE procedure

  Read `campaign/config.json` (theme and name) and `campaign/dungeon.json` (all rooms with encounter/loot/trap data). You have whole-dungeon context — use it for tonal consistency.

  **1. Room descriptions** — For each room, write a `description`: 2–4 sentences establishing atmosphere. Reference what the room contains in in-world terms (rusted chains, the smell of rot, a altar stained dark) — never mechanical stats or numbers. Entrance orients the party. Boss room must feel climactic. Keep the same voice throughout; this is one dungeon.

  Rewrite `campaign/dungeon.json` by adding `"description": "..."` to every room object. Do not alter `id`, `type`, `connections`, `encounter`, `loot`, or `trap` fields.

  **2. NPC roster** — Invent 1–3 named NPCs appropriate to the campaign theme. Place each in a specific room by `id`. Possible archetypes: survivor, prisoner, villain's lieutenant, spirit, merchant. Write `campaign/npcs.json`:
  ```json
  [
    {
      "id": "npc_01",
      "name": "Sister Maren",
      "room": "r04",
      "goal": "recover the stolen relic before it is used in the ritual",
      "disposition": "fearful but determined"
    }
  ]
  ```

  **3. Quest tree** — Write 1 primary quest and 1–2 side objectives rooted in the theme. Write `campaign/quests.json`:
  ```json
  [
    {
      "id": "q01",
      "title": "The Sunken Relic",
      "hook": "A priest at the surface begs the party to descend — something sacred was stolen three days ago.",
      "objectives": [
        {"id": "q01a", "desc": "Find the relic in the vault", "completed": false},
        {"id": "q01b", "desc": "Return it to Sister Maren", "completed": false}
      ],
      "reward": "200 XP and Sister Maren's gratitude"
    }
  ]
  ```

  Apply all voice rules to descriptions and hook prose. No HP, AC, or spell slots.

  Return: `{"mode": "PREGEN_NARRATIVE", "files_written": ["campaign/dungeon.json", "campaign/npcs.json", "campaign/quests.json"]}`
  ```

- [ ] **Step 5: Add pregen-narrative dispatch template to run.md**

  In `run.md`, after the pregen-populate dispatch template (added in Task 3), add:

  ```
  **DM (pregen-narrative):** model: sonnet
  ```
  Use the dm subagent. MODE: PREGEN_NARRATIVE.
  Config: <campaign/config.json contents>. Populated dungeon: <campaign/dungeon.json contents>.
  Write a 2–4 sentence description for every room into campaign/dungeon.json. Write campaign/npcs.json (1–3 named NPCs with goals) and campaign/quests.json (1 primary quest + 1–2 side objectives).
  ```
  ```

- [ ] **Step 6: Verify**

  ```bash
  grep -n "PREGEN_NARRATIVE\|campaign/\*" .claude/agents/dm.md | wc -l
  # Expected: 6 or more

  grep -n "pregen-narrative" run.md
  # Expected: 1 hit
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add .claude/agents/dm.md run.md
  git commit -m "feat(dm): add PREGEN_NARRATIVE mode; add campaign/* read+write permissions"
  ```

---

### Task 5: Wire pre-generation pipeline into run.md boot sequence

**Files:**
- Modify: `run.md:19-23` (Boot sequence)

**Interfaces:**
- Consumes: `campaign/config.json`, dispatch templates from Tasks 2–4
- Produces: Automatic three-dispatch pipeline when `campaign/dungeon.json` is absent; halt with clear message if config is also absent

- [ ] **Step 1: Replace the boot sequence section**

  In `run.md`, find and replace the entire Boot sequence section:

  Find:
  ```
  ## Boot sequence
  1. Verify `scripts/dice.py` and `scripts/oracle.py` exist and run (`python scripts/dice.py "1d20" --reason boot-check`). If either is missing or errors, stop and report — do not improvise rolls or data.
  2. Determine **new game** vs **resume**: if `state/public/world.json` exists and has a live scene, resume; otherwise start fresh.
  3. On resume, load all of `state/public` (and `state/secret` for your own bookkeeping) and continue at the current turn. State on disk is the source of truth; your context is disposable.
  ```

  Replace with:
  ```
  ## Boot sequence
  1. Verify `scripts/dice.py` and `scripts/oracle.py` exist and run (`python scripts/dice.py "1d20" --reason boot-check`). If either is missing or errors, stop and report — do not improvise rolls or data.
  2. **Campaign check:** If `campaign/dungeon.json` does not exist:
     a. If `campaign/config.json` also does not exist: print `"No campaign found. Create campaign/config.json (see template in campaign/) and re-run."` and halt.
     b. If `campaign/config.json` exists: run the pre-generation pipeline:
        - Log to `log/session.md`: `## Campaign Generation — <config.name> (<config.room_count> rooms, level <config.party_level>)`
        - **Dispatch 1:** world-engine in `PREGEN_STRUCTURE` mode (model: sonnet). Pass `campaign/config.json` contents inline. After the dispatch returns, verify `campaign/dungeon.json` exists — if not, stop and report.
        - **Dispatch 2:** world-engine in `PREGEN_POPULATE` mode (model: sonnet). Pass `campaign/config.json` and the just-written `campaign/dungeon.json` contents inline. After it returns, verify `campaign/encounters.json` exists — if not, stop and report.
        - **Dispatch 3:** dm in `PREGEN_NARRATIVE` mode (model: sonnet). Pass `campaign/config.json` and the fully-populated `campaign/dungeon.json` contents inline. After it returns, verify `campaign/npcs.json` and `campaign/quests.json` exist — if not, stop and report.
        - Log to `log/session.md`: `*Campaign ready: <room_count> rooms · <npc_count> NPCs · <quest_count> quests.*`
  3. Determine **new game** vs **resume**: if `state/public/world.json` exists and has a live scene, resume; otherwise start fresh.
  4. On resume, load all of `state/public` (and `state/secret` for your own bookkeeping) and continue at the current turn. State on disk is the source of truth; your context is disposable.
  ```

- [ ] **Step 2: Verify the edit**

  ```bash
  grep -n "Campaign check\|Dispatch 1\|Dispatch 2\|Dispatch 3" run.md
  # Expected: 4 hits, all in the Boot sequence section (roughly lines 20-35)
  ```

- [ ] **Step 3: End-to-end smoke test**

  Remove any existing generated files, then run the orchestrator. After pre-gen completes:
  ```bash
  ls campaign/
  # Expected: .gitkeep  config.json  dungeon.json  encounters.json  npcs.json  quests.json

  # Verify dungeon.json has descriptions (PREGEN_NARRATIVE ran last)
  python3 -c "
  import json
  rooms = json.load(open('campaign/dungeon.json'))
  missing = [r['id'] for r in rooms if not r.get('description')]
  print('Rooms missing description:', missing or 'none')
  print('Total rooms:', len(rooms))
  "
  # Expected: Rooms missing description: none

  # Verify rng_log has entries (dice.py was called)
  tail -3 state/rng_log.jsonl
  # Expected: JSON lines with reason strings mentioning dungeon generation
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add run.md
  git commit -m "feat(run): wire campaign pre-generation pipeline into boot sequence"
  ```

---

### Task 6: Update scene setup to read from campaign/

**Files:**
- Modify: `run.md:26-31` (Session start step 4 — world.json initialization)
- Modify: `run.md:42-48` (Turn loop step 2 — Scene setup)

**Interfaces:**
- Consumes: `campaign/dungeon.json` (description + connections + encounter ref), `campaign/encounters.json` (roster), `state/public/world.json` (current_room_id)
- Produces: `state/public/scene.json` built from pre-generated data (no DM SCENE_SETUP dispatch); `state/public/world.json` updated with `current_room_id` on room transitions

- [ ] **Step 1: Update world.json initialization in Session start**

  In `run.md`, find in the Session start section:
  ```
  4. Initialize `state/public/world.json` (scene pointer = none yet, time, etc.) and an empty `state/public/quest_log.json`.
  ```

  Replace with:
  ```
  4. Initialize `state/public/world.json` with `{"current_room_id": "r01", "turn": 0, "time": "dawn"}` (use the `id` of the first room with `"type": "entrance"` in `campaign/dungeon.json`) and an empty `state/public/quest_log.json`.
  ```

- [ ] **Step 2: Replace scene setup step in the turn loop**

  In `run.md`, find the Scene setup section:
  ```
  ### 2. Scene setup (only when a new scene/encounter is needed)
  1. Dispatch **dm** in `SCENE_SETUP` mode with current world state and the goal. It returns scene narration + a `scene_setup_request`.
  2. Dispatch **world-engine** in `GENERATE` mode with that request. It writes `map.txt`, `encounter.json`, `state/secret/monsters.json`, and returns rosters/hazards.
  3. Build `state/public/scene.json` — the public perception packet: the DM's scene prose, the public map, visible creatures *by name and apparent state only* (never true HP), exits, and ambient dialogue. **Strip anything from `secret/`.**
  4. Place PC tokens (positions) in `party.json` and on the map.
  5. Append the scene to `log/session.md` (see Log format).
  ```

  Replace with:
  ```
  ### 2. Scene setup (only when a new scene/encounter is needed)
  1. Read `current_room_id` from `state/public/world.json`. Find the matching room object in `campaign/dungeon.json`. Its `description` field is the scene prose — no DM dispatch needed.
  2. Look up `encounter.table_ref` for this room in `campaign/encounters.json` to get the pre-selected monster roster. Dispatch **world-engine** in `GENERATE` mode, passing the roster as an explicit list (not a free-selection request). World-engine rolls each monster's HP, writes `map.txt`, `encounter.json`, and `state/secret/monsters.json`.
     - If the room's `trap` is non-null, include the trap ref in the GENERATE request so world-engine places it on the map with the pre-rolled DC.
  3. Build `state/public/scene.json` from: the pre-written `description`, the public map, visible creatures by name and apparent state (never numeric HP), exits derived from the room's `connections` list, and an empty `npc_dialogue` list. **Strip anything from `secret/`.**
  4. Place PC tokens in `party.json` and on the map.
  5. Append the scene to `log/session.md` (see Log format).

  **On room transition:** when the party moves to a connected room, update `current_room_id` in `state/public/world.json` to the destination room's `id`, then run scene setup (steps 1–5) for the new room.
  ```

- [ ] **Step 3: Verify**

  ```bash
  grep -n "current_room_id\|campaign/dungeon\|SCENE_SETUP" run.md
  # Expected:
  #   current_room_id — 2+ hits (session start + scene setup)
  #   campaign/dungeon — 2+ hits (scene setup step 1 + step 2 area)
  #   SCENE_SETUP — 0 hits in the turn loop body (only in the dispatch templates section is OK)
  ```

- [ ] **Step 4: Integration test — run through first scene setup**

  Start a new game (with pre-generated campaign from Task 5). After scene setup in turn 1:
  ```bash
  # scene.json should have a description from dungeon.json
  python3 -c "
  import json
  s = json.load(open('state/public/scene.json'))
  d = json.load(open('campaign/dungeon.json'))
  entrance = next(r for r in d if r['type'] == 'entrance')
  assert s.get('description') == entrance['description'], 'scene description mismatch'
  print('OK — scene.json description matches dungeon.json entrance room')
  "

  # world.json should have current_room_id
  python3 -c "
  import json
  w = json.load(open('state/public/world.json'))
  assert 'current_room_id' in w, 'current_room_id missing from world.json'
  print('current_room_id:', w['current_room_id'])
  "
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add run.md
  git commit -m "feat(run): scene setup reads from campaign/dungeon.json; track current_room_id in world.json"
  ```

---

### Task 7: Update CLAUDE.md and DESIGN.md

**Files:**
- Modify: `CLAUDE.md` — file ownership table
- Modify: `DESIGN.md` — M7 milestone status

**Interfaces:**
- None — documentation only

- [ ] **Step 1: Add campaign/* rows to CLAUDE.md ownership table**

  In `CLAUDE.md`, find the last row of the File ownership table:
  ```
  | `state/rng_log.jsonl` | dice.py (via world-engine) |
  | `log/session.md` | orchestrator |
  | `cache/*` | oracle.py |
  ```

  Replace with:
  ```
  | `state/rng_log.jsonl` | dice.py (via world-engine) |
  | `log/session.md` | orchestrator |
  | `cache/*` | oracle.py |
  | `campaign/config.json` | User |
  | `campaign/dungeon.json` | world-engine (PREGEN_STRUCTURE → PREGEN_POPULATE), then DM (PREGEN_NARRATIVE) — sequential pre-gen dispatches only |
  | `campaign/encounters.json` | world-engine (PREGEN_POPULATE) |
  | `campaign/npcs.json` | DM (PREGEN_NARRATIVE) |
  | `campaign/quests.json` | DM (PREGEN_NARRATIVE); orchestrator toggles `completed` flags only |
  ```

- [ ] **Step 2: Mark M7 complete in DESIGN.md**

  In `DESIGN.md`, find:
  ```
  ### M7 — Campaign pre-generation
  ```

  Replace with:
  ```
  ### M7 — Campaign pre-generation ✓ *completed 2026-06-20*
  ```

- [ ] **Step 3: Verify**

  ```bash
  grep -n "campaign/" CLAUDE.md | wc -l
  # Expected: 5 (one per new ownership row)

  grep -n "M7" DESIGN.md
  # Expected: includes "completed 2026-06-20"
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add CLAUDE.md DESIGN.md
  git commit -m "docs: add campaign/* ownership to CLAUDE.md; mark M7 complete in DESIGN.md"
  ```

---

## Self-Review

**Spec coverage:**
- ✓ `campaign/config.json` template — Task 1
- ✓ Boot trigger (check dungeon.json, halt if no config) — Task 5
- ✓ Dispatch 1 PREGEN_STRUCTURE (world-engine: room graph) — Tasks 2, 5
- ✓ Dispatch 2 PREGEN_POPULATE (world-engine: encounters/loot/traps) — Tasks 2, 3, 5
- ✓ Dispatch 3 PREGEN_NARRATIVE (DM: descriptions, NPCs, quests) — Tasks 4, 5
- ✓ All four campaign file schemas — Tasks 2, 3, 4
- ✓ Scene setup reads from campaign/dungeon.json (no DM SCENE_SETUP dispatch) — Task 6
- ✓ World-engine GENERATE receives pre-selected roster — Task 6
- ✓ `current_room_id` in world.json — Task 6
- ✓ CLAUDE.md ownership table — Task 7
- ✓ DESIGN.md M7 complete — Task 7
- ✓ Log entries for pre-gen progress — Task 5

**Type consistency:** `table_ref` keys in encounters.json use `enc_<id>` / `loot_<id>` / `trap_<id>` pattern consistently in Tasks 2, 3, 4, and 6. `current_room_id` referenced identically in Tasks 5 and 6.

**Placeholder scan:** All procedure blocks have complete content — no TBDs or "handle edge cases" stubs.

**Scope:** All seven tasks together produce a working end-to-end campaign pre-generation flow. Each task is independently reviewable and committable.
