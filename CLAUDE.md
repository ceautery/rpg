# RPG Simulator — Project Invariants

## Hard invariants

1. **No agent ever produces a random result by reasoning.** All randomness comes from `dice.py`, invoked only by the world-engine, and every roll is logged to `state/rng_log.jsonl`.
2. **Three powers, hard separation.** The orchestrator moves messages and applies results; the DM narrates and decides intent; the world-engine owns all mechanics and randomness. No actor does another's job.
3. **Players see only their own sheet + the perception packet.** `state/secret/` is never passed to a player agent or the human. Any leak is a bug.
4. **Every file has exactly one writer.** Read freely within your permitted scope; write only what you own. Clobber bugs are the hardest to debug.
5. **The gate is absolute.** A turn does not advance until every active player's action file for that turn exists in `state/actions/`. Human players are gated identically to agent players.
6. **State on disk is the source of truth.** The orchestrator reloads `state/public/*` fresh at the top of every turn. Context is disposable; disk is canonical.
7. **The rules oracle is pinned to one source document.** Default: `srd-2024` (SRD 5.2, CC-BY). Never blend sources within a session. `oracle.py` injects `document__key__in=srd-2024` on every query.

## File ownership

| File / directory | Writer |
|---|---|
| `state/public/party.json`, `encounter.json` (applied results) | orchestrator |
| `state/public/world.json`, `quest_log.json`, `scene.json`, `journal.json` | orchestrator |
| `state/public/events.jsonl` | orchestrator (appends on significant events) |
| `state/public/npc_relations.json` | orchestrator (updates after each significant NPC interaction) |
| `state/public/map.txt`, `encounter.json` (mechanical scaffold) | world-engine |
| `state/secret/monsters.json` | world-engine |
| `state/secret/hidden.json` | DM (when orchestrator authorizes) |
| `state/actions/<turn>.<actor>.json` | orchestrator (capturing player/human output) |
| `state/rng_log.jsonl` | dice.py (via world-engine) |
| `log/session.md` | orchestrator |
| `cache/*` | oracle.py |
| `campaign/config.json` | User |
| `campaign/dungeon.json` | world-engine (PREGEN_STRUCTURE → PREGEN_POPULATE), then DM (PREGEN_NARRATIVE adds `description` + `spotlight`) — sequential pre-gen dispatches only |
| `campaign/encounters.json` | world-engine (PREGEN_POPULATE) |
| `campaign/named_items.json` | DM (PREGEN_NARRATIVE) |
| `campaign/foreshadowing.json` | DM (PREGEN_NARRATIVE) |
| `campaign/npcs.json` | DM (PREGEN_NARRATIVE) |
| `campaign/quests.json` | DM (PREGEN_NARRATIVE); orchestrator toggles `completed` flags only |

## Attribution

SRD content served by the Open5e API is CC-BY 4.0. Reproduce the attribution notice in any published session log.
