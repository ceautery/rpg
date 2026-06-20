# Design Doc — Multi-Agent RPG Simulator

## Architecture

```
ORCHESTRATOR  (Claude Code main context — run.md)
  │  dispatch via Agent tool
  ├─ dm          (subagent — fiction, tactics, scene narration)
  ├─ player×N    (subagent per agent PC — one action per turn)
  └─ world-engine (subagent — all dice, all mechanics)
         └── scripts/dice.py    (real RNG, append-only audit log)
         └── scripts/oracle.py  (Open5e API v2, pinned to srd-2024)

SHARED STATE ON DISK  (the blackboard)
  state/public/    — readable by all agents
  state/secret/    — orchestrator + DM + world-engine only
  state/actions/   — per-turn action inbox, one file per PC per turn
  state/rng_log.jsonl — append-only dice audit (every roll logged)
  log/session.md   — append-only human-readable session log
  campaign/        — (planned M6) pre-generated campaign assets
```

The blackboard pattern is correct for the Claude Code subagent model because subagents cannot talk to each other directly. Every agent reads from disk and writes only to its own files; the orchestrator is the sole applier of turn results to public state. This eliminates clobber races and makes state fully auditable.

---

## Confirmed decisions

**Ruleset:** SRD 5.2 (`srd-2024`, CC-BY 4.0) via Open5e v2 API. Single source pinned per session so no mid-session blending. Attribution notice required in published session logs.

**DM as subagent:** Two dispatches per turn (pre-roll + post-roll). Pre-roll: DM orders initiative, decides monster tactics, emits `mechanic_requests`. Post-roll: DM receives resolved facts and writes final narration. The split keeps fiction and randomness cleanly separated.

**encounter.json split-writer:** World-engine writes it fresh at scene setup; orchestrator mutates `turn_pointer` and removes defeated combatants in-place. Known coordination point, documented in CLAUDE.md invariants.

**oracle.py is a query wrapper, not a rules engine.** It fetches and caches; adjudication stays in world-engine and DM. The `--fields` flag keeps payloads small.

**Session log depth:** Configurable via `dm_log_depth` in `state/public/world.json` (default 5). Orchestrator trims `session.md` to that many turns before DM dispatch.

**Character creation:** 2-dispatch flow. Player subagent returns concept + `mechanics_request`; orchestrator routes to world-engine; world-engine rolls stats via `dice.py` and returns final sheet.

**MVP fog-of-war:** Whole-room. Line-of-sight deferred. Perception packet = everything in the current room not in `state/secret/`.

**In-world language:** Agent prompts (`dm.md`, `player.md`) and orchestrator (`run.md`) enforce that numeric HP, AC, spell slot counts, and roll totals never appear in narration or dialogue. Mechanical numbers are confined to the **Rolls** block and terse end-of-turn status lines. Voice-rules sections added to both agent prompts with translation tables.

---

## Known pragmatic adjustments

1. `python` is `python3` on macOS — all script invocations use `python3`.
2. `datetime.utcnow()` deprecated — fixed to `datetime.now(timezone.utc)` in `dice.py`.
3. Open5e v2 API: `fields` parameter must be appended unencoded (`query += "&fields=" + fields`) — urllib encodes commas as `%2C`, which returns 403.
4. Open5e v2 API: Python's default `User-Agent` is blocked by Cloudflare — custom header required.
5. Open5e v2 API: `equipment` endpoint split into `weapons`/`armor`/`items`; `monsters` renamed `creatures`. Handled via `ENDPOINT_ALIASES` in `oracle.py`.

---

## Milestones

### ✅ M1 — Scaffold
Directories, `CLAUDE.md` (7 invariants + file ownership table), `DESIGN.md`, `README.md`, agent stubs (`.claude/agents/dm.md`, `player.md`, `world-engine.md`).

### ✅ M2 — Tools
`scripts/dice.py` — authoritative RNG, NdM+modifier, `--adv`/`--dis`, keep-highest/lowest, `--ac`/`--dc`, `RPG_SEED` for replay, appends to `state/rng_log.jsonl`.
`scripts/oracle.py` — Open5e v2 wrapper, always injects `document__key__in=srd-2024`, SHA256 cache under `cache/`.

### ✅ M3 — Vertical slice
One room (stone cellar), one goblin (Skrix), one agent PC (Aldric Sootmantle, wizard). Full turn loop end-to-end: scene setup → DM pre-roll → world-engine resolve → DM post-roll → orchestrator apply. `rng_log.jsonl`, `party.json`, and `session.md` all reflect the same authoritative rolls.

### ✅ M4 — Human seat
Stone Bauer (human fighter) added as second party member. Terminal prompt path: scene + sheet presented, human types free text, orchestrator coerces to action schema. All-actions gate: turn does not advance until both PCs have action files. Agent PC dispatched in background while human is prompted simultaneously.

### ✅ M5 — Expand
- **Multi-room combat:** Guard Post Chamber (Room 2) with cover mechanics (barrel 3/4 cover, AC bonus), readied action (Vreck's shortbow on reaction), multi-round resolution.
- **Rest mechanic:** Short rest (Hit Dice spending via dice.py, per-PC) and long rest (orchestrator applies directly, no dispatch). Both described in `run.md` REST PROCEDURE section.
- **Quest system:** `state/public/quest_log.json` with structured quests, objectives, completion tracking, and plot hook flags.
- **Loot drops:** World-engine rolls loot quantities via `dice.py`; chest contents (coins, Potion of Healing, mentor's note) resolved post-combat. Lock DC mechanics.
- **Trap triggering:** Flagstone pressure plate (Room 3, E3) fires mid-movement; attack roll resolved by world-engine before PC's action completes.
- **scripts/render_log.py:** Converts `session.md` to `session.html` with `<meta http-equiv="refresh">` for live browser watch. Pure stdlib, no external deps.
- **In-world language rules (added post-M5):** Voice rules in `dm.md`, `player.md`, `run.md` — mechanical numbers banned from narration and dialogue.

**Session 1 complete:** Three-room undercroft dungeon.
- Room 1 (Stone Cellar): Skrix defeated, Aldric recovers mentor's grimoire (50 XP)
- Room 2 (Guard Post Chamber): Vreck defeated, cover + readied-action mechanics exercised (50 XP)
- Long rest between scenes
- Room 3 (Goblin Treasury): Gruk fled at 1 HP via crawl hole, trap fired (miss), Mage Hand opened chest. Loot: 10 sp, 1 gp, Potion of Healing, mentor's note seeding the Dobb/Crestfall plot hook (100 XP partial)
- Party XP: 200. Open quest hook: *The Dobb Name* (Crestfall market, north).

---

## Planned milestones (M6+)

### M6 — Quality of life + speed
- **Inter-PC coordination phase:** New `COORDINATE` mode for player subagent. Before action collection opens, orchestrator presents the scene and asks: *"Anything you want to say to [party member] before you act?"* Human's message (if any) is passed to agent PC(s); agents respond in character and optionally signal intent. Action files written after coordination closes. One optional round-trip per scene.
- **Haiku for fast agents:** Player agent `TAKE_TURN` and `COORDINATE` modes → `claude-haiku-4-5`. World-engine `RESOLVE` mode (pure dice + arithmetic) → Haiku. DM narration and world-engine `GENERATE` stay on Sonnet.
- **Ditch HTML log:** Remove `render_log.py` from the active turn loop. Script stays in repo. Players use `tail -f log/session.md` or follow in Claude Code's UI.
- **Milestone/roadmap tracking:** `MILESTONES.md` added to repo root.

### M7 — Campaign pre-generation
- **Separate world-building from gameplay.** New phase before play: DM + world-engine generate the full campaign module — all rooms, room connections, NPC roster with goals, quest tree, encounter tables, loot tables, trap placements.
- Output: `campaign/dungeon.json`, `campaign/npcs.json`, `campaign/quests.json`, `campaign/encounters.json`.
- Gameplay reads from `campaign/` rather than generating scenes live. Scene setup becomes a file read + token placement, not a dispatch.
- Enables consistent DM behavior (whole-dungeon context) and faster scene transitions.

### M8 — Import + session config
- **Foundry VTT module import:** `scripts/import_foundry.py` maps Foundry's JSON module format to `campaign/`. Community SRD modules provide real dungeon content without manual generation.
- **Session config menu:** `scripts/start_session.py` — number of human players (0–N), number of agent players (0–N), load campaign or generate new, difficulty preset. Zero human players = pure storytelling/playtest mode.

---

## File ownership (canonical)

| File / directory | Writer |
|---|---|
| `state/public/party.json`, `encounter.json` (applied results) | orchestrator |
| `state/public/world.json`, `quest_log.json`, `scene.json` | orchestrator |
| `state/public/map.txt`, `encounter.json` (mechanical scaffold) | world-engine |
| `state/secret/monsters.json` | world-engine |
| `state/secret/hidden.json` | DM (when orchestrator authorizes) |
| `state/actions/<turn>.<actor>.json` | orchestrator (capturing player/human output) |
| `state/rng_log.jsonl` | dice.py (via world-engine) |
| `log/session.md` | orchestrator |
| `campaign/*` | world-engine + DM (M7, pre-generation phase) |
| `cache/*` | oracle.py |
