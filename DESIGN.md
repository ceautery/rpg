# Design Doc — Multi-Agent RPG Simulator

## Architecture (as specified)

```
ORCHESTRATOR  (Claude Code main context — run.md)
  │  dispatch via Agent tool
  ├─ dm          (subagent — fiction, tactics, scene narration)
  ├─ player×N    (subagent per agent PC — one action per turn)
  └─ world-engine (subagent — all dice, all mechanics)
         └── scripts/dice.py  (real RNG, audit log)
         └── scripts/oracle.py (Open5e API, pinned to srd-2024)

SHARED STATE ON DISK  (the blackboard)
  state/public/   — readable by all
  state/secret/   — orchestrator + DM + world-engine only
  state/actions/  — per-turn action inbox
  state/rng_log.jsonl — append-only dice audit
  log/session.md  — human-readable watch surface
```

The blackboard pattern is correct for the Claude Code subagent model because subagents cannot talk to each other. Every agent reads from disk and writes to its own files; the orchestrator is the sole applier of turn results to public state. This avoids clobber races and makes the state fully auditable.

---

## Decisions confirmed

**Ruleset:** SRD 5.2 (`srd-2024`, CC-BY) via Open5e v2 API. Clean license, broad monster/spell/item coverage, single source so no mid-session blending.

**DM as subagent:** Yes. Subagent gives cleaner role separation — the DM sees secret state and returns structured JSON, and the orchestrator never has to merge creative and mechanical reasoning. Tradeoff: 2 DM dispatches per turn (pre-roll + post-roll) instead of 1; this is acceptable and matches the spec. The alternative (folding DM into the orchestrator) risks the orchestrator inventing fiction and muddies the three-power separation.

**Party size for first run:** 1 agent PC, no human. Minimum surface area to prove the loop. Human seat comes in Milestone 4.

---

## Changes / pragmatic adjustments

**1. `rng_log.jsonl` lives at `state/rng_log.jsonl`, not `state/rng_log.jsonl` in the root.**
The spec puts it under `state/` — we keep it there. `dice.py` receives the path as a constant.

**2. `encounter.json` has a split-writer tension.**
The spec says world-engine writes mechanical fields and orchestrator writes applied results. In practice, both will rewrite the same file. Mitigation: world-engine writes it fresh at scene setup; orchestrator only mutates `turn_pointer` and `combatants` (removing defeated). Document this in the file's header comment and treat it as a known coordination point.

**3. `oracle.py` is a query wrapper, not a rules engine.**
Open5e returns data; adjudication logic stays in the world-engine and DM. `oracle.py` never decides anything — it fetches and caches. The `--fields` flag keeps payloads small to avoid flooding agent context.

**4. MVP fog-of-war is whole-room.**
Line-of-sight is deferred. The perception packet = everything in the current room that isn't in `secret/`. This is explicitly called out in run.md.

**5. Context-window pressure from the session log.**
`session.md` is handed to the DM for continuity, but it will grow indefinitely. For the MVP the DM reads only the last N turns (orchestrator trims the excerpt before dispatch). Exact N TBD by testing — start at 5.

---

## Decisions

1. **`encounter.json` split-writer** — keep as one file. World-engine writes it at scene setup; orchestrator mutates `turn_pointer` and removes defeated combatants in-place. Documented as a known coordination point.
2. **Session log excerpt depth** — configurable. Stored as `dm_log_depth` in `state/public/world.json` (default 5). Orchestrator trims `session.md` to that many turns before passing to the DM.
3. **Character creation flow** — 2-dispatch flow: player subagent returns concept + `mechanics_request` → orchestrator routes to world-engine → world-engine rolls stats and returns them.

---

## Milestones

1. ✅ **Scaffold + plan** — directories, CLAUDE.md, DESIGN.md, README.md, agent stubs. **→ Pause for review.**
2. **Tools** — implement and test `dice.py` and `oracle.py` standalone. Show outputs + rng_log.
3. **Vertical slice** — one room, one goblin, one agent PC, ~3 turns end-to-end.
4. **Human seat** — terminal prompt path, all-actions gate for mixed parties.
5. **Expand** — multi-room, multi-player, initiative-ordered combat, loot/traps/quests, HTML view.
