# Project Initializer — Multi-Agent Tabletop RPG Simulator

**Mission:** Build a turn-based, multi-agent simulation of a tabletop RPG session. A DM agent runs the world, one or more player agents play characters, a world-engine agent is the authoritative source of all randomness and mechanics, and a human can join as a player with the exact same abilities as a player agent. The whole thing must be *watchable* and *auditable*.

---

## 0. How to approach this (read first)

1. **Plan before you build.** Produce a short design doc (`DESIGN.md`) reflecting the architecture below, note anything you'd change, and list open decisions. Wait for my review on the big calls before writing the full loop.
2. **Build the smallest playable vertical slice first** (see Milestones), then stop. Do *not* build the whole game in one pass.
3. Keep dependencies minimal. Prefer Python 3 for the helper scripts and plain files for state. No database, no web framework for the MVP.
4. When something here is unrealistic or fights how Claude Code actually works, say so and propose the pragmatic version instead of silently working around it.

---

## 1. The two hard constraints that drive the design

- **Subagents do not talk to each other.** In Claude Code, the main context dispatches a subagent, the subagent returns text, and it stops. There is no peer-to-peer chat. **Therefore the main context is a neutral conductor** that drives the turn loop, dispatches agents, and mediates all messages. Agents coordinate *only* by reading/writing shared files on disk (a "blackboard"). State lives on disk so it survives context compaction and long sessions.
- **LLMs cannot generate trustworthy random numbers.** All dice, character rolls, monster/loot selection rolls, and trap triggers must go through a real RNG via an external script. The world-engine agent is the *only* actor allowed to invoke it, and every roll is logged to an append-only audit file. No agent ever "imagines" a roll.

---

## 2. Architecture overview

```
                ┌──────────────────────────────────────────┐
                │   ORCHESTRATOR  (Claude Code main context) │
                │   neutral conductor: turn loop, dispatch,  │
                │   human I/O, applies results, writes log   │
                └──────────────────────────────────────────┘
                  │ dispatch (Task)         ▲ returns text
        ┌─────────┼───────────────┬─────────┴────────┐
        ▼         ▼               ▼                  ▼
   ┌────────┐ ┌────────┐    ┌──────────────┐   (prompts terminal)
   │  DM    │ │ PLAYER │..  │ WORLD-ENGINE │     ┌───────────┐
   │ agent  │ │ agent  │    │ (RNG+mechanics)│   │  HUMAN    │
   └────────┘ └────────┘    └──────────────┘     │  player   │
        │         │               │              └───────────┘
        └─────────┴───────┬───────┴──────────────────┘
                          ▼
                 SHARED STATE ON DISK  (the blackboard)
                 + dice.py (real RNG)  + oracle.py (rules data)
```

The orchestrator is **not** creative. It narrates nothing and decides nothing about the fiction. It only: loads state, decides whose turn it is, dispatches the right agent with the right inputs, gates on all actions being submitted, asks the world-engine to resolve mechanics, applies the results to state, and appends to the human-readable log.

---

## 3. Project layout to scaffold

```
rpg-sim/
  CLAUDE.md                 # project memory: the invariants in §6 go here
  DESIGN.md                 # your plan (write this first)
  README.md                 # how to run a session
  run.md                    # the orchestrator's operating procedure (the turn loop)
  .claude/
    agents/
      dm.md                 # DM subagent definition
      player.md             # player subagent definition
      world-engine.md       # world-engine subagent definition
  scripts/
    dice.py                 # authoritative RNG (see §8)
    oracle.py               # rules/content lookup wrapper (see §9)
    render_log.py           # optional: build session.html from session.md (§10)
  state/
    public/                 # readable by everyone, incl. player agents + human
      world.json            # current scene id, time, weather, known locations
      party.json            # PCs: sheet, hp, conditions, position, inventory
      scene.json            # current scene's public perception packet
      map.txt               # ASCII grid of current scene w/ token positions
      encounter.json        # initiative order, turn pointer, combatant positions
      quest_log.json
    secret/                 # DM + world-engine ONLY — never handed to players
      monsters.json         # true monster stats, hidden hp, tactics notes
      hidden.json           # undiscovered traps, secret doors, plot intentions
    actions/                # per-turn inbox; one file per actor per turn
      <turn>.<actor>.json
    rng_log.jsonl           # append-only audit of every roll (world-engine only)
  log/
    session.md              # append-only human-readable narration (the "watch" view)
    session.html            # optional auto-refreshing view
  cache/                    # cached oracle.py responses
```

---

## 4. Roles & responsibilities

**Orchestrator (main context).** Owns the turn loop in `run.md`. Reads state fresh from disk each turn. Dispatches agents. Prompts the human. Applies adjudicated mechanical results to `state/public`. Appends narration to `log/session.md`. Owns the turn pointer. Enforces the information boundary (decides what each player is allowed to see).

**DM agent (`dm.md`).** Describes scenes, voices NPCs/townspeople, and decides monster *intentions and tactics* (who attacks whom, whether they flee, what spell they cast). It reads `state/secret`. It does **not** roll dice and does **not** decide outcomes of chance — it says *what is attempted and which check governs it*, then the world-engine resolves. It proposes scene setup needs (e.g. "I want a 3-room goblin warren") which the world-engine fills in mechanically.

**Player agent (`player.md`).** Plays one PC. On its turn it receives only (a) its own character sheet and (b) the public perception packet for what its character can currently see/know — never `state/secret`, never other players' private reasoning. It returns a single declared action in a fixed schema. At session start it can roll up a character (name, class, goals, personality) — but the *mechanical* rolls (stats, HP) are requested from the world-engine, not invented.

**World-engine agent (`world-engine.md`).** The authoritative mechanical layer and the only caller of `dice.py`. Rolls all dice, generates characters' numbers, selects monsters/loot/traps (via `oracle.py` + weighted RNG), builds the ASCII map and token positions, computes initiative, and resolves attacks/checks/saves into concrete results. Writes `rng_log.jsonl`, `map.txt`, and the mechanical parts of `secret/` and `encounter.json`. It is rules-bound and non-narrative: it outputs numbers and facts, the DM dresses them in prose.

**Human player.** Identical contract to a player agent: same perception packet in, same action schema out. The orchestrator just collects the human's action via a terminal prompt instead of a dispatch. The human must never be shown `state/secret`.

---

## 5. The blackboard: ownership & boundaries

- **Single-writer rule.** Each file has exactly one writer to avoid clobbering: orchestrator owns the turn pointer + applied results in `state/public`; world-engine owns `rng_log.jsonl`, `map.txt`, and mechanical fields of `encounter.json`/`secret/`; DM owns narrative fields of `secret/`; each player writes only its own `actions/<turn>.<actor>.json`. Everyone reads what they're permitted to read.
- **Information boundary (anti-metagaming).** `state/secret/` is the hard wall. Player agents and the human are handed a *constructed perception packet* (`scene.json` + their sheet), never raw secret files and never the monster's true HP. This is what makes it feel like a real table instead of an omniscient sim. Treat any leak of secret state to a player as a bug.
- **Provenance/license discipline (from prior research).** The rules oracle pulls from the Open5e API, which mixes multiple publishers' content. Pin a single source via `document__key` (default `srd-2024`, pure CC-BY) so agents never blend incompatible rulesets mid-combat. See §9.

---

## 6. Hard invariants (copy these into `CLAUDE.md`)

1. No agent ever produces a random result by reasoning. All randomness comes from `dice.py`, invoked only by the world-engine, and is logged to `rng_log.jsonl`.
2. The orchestrator never invents fiction and never decides outcomes; the DM never rolls; the world-engine never narrates. Keep the three powers separate.
3. Players (agent or human) only ever see their own sheet + the perception packet. `state/secret/` is never exposed to them.
4. Every file has one writer. Read freely (within permission), write only what you own.
5. A turn does not resolve until **every** active player's action for that turn is present in `state/actions/`. The human is gated on exactly like an agent.
6. The orchestrator reloads state from disk at the start of every turn so the game survives context loss.
7. The rules oracle is pinned to one source document; results are content data, not a rules engine — adjudication logic lives in the world-engine/DM, not in the API.

---

## 7. Turn protocol

1. **Load.** Orchestrator reads `state/public` (and `secret` for its own bookkeeping) fresh from disk.
2. **Scene setup (if needed).** DM proposes the scene and NPC/monster intent; world-engine fills mechanics (monster stats → `secret/monsters.json`, map → `map.txt`, initiative → `encounter.json`). Orchestrator builds the public `scene.json` perception packet and appends the scene description to `log/session.md`.
3. **Collect actions (the gate).** For each active PC: if agent, dispatch the player subagent with its perception packet + sheet and capture its returned action into `state/actions/<turn>.<actor>.json`; if human, prompt in the terminal and write the same file. **Block until all are present.**
4. **Adjudicate.** Orchestrator hands the full action set to the DM, ordered by initiative. For each action requiring chance, the DM names the mechanic (e.g. "attack vs AC 15" / "DC 13 DEX save") and the world-engine rolls it via `dice.py`. Monster turns: DM picks tactics, world-engine rolls. Outcomes become concrete facts.
5. **Apply.** Orchestrator writes resolved changes (HP, conditions, positions, inventory, loot, quest flags) to `state/public`.
6. **Narrate.** DM writes the prose outcome of the turn; orchestrator appends it to `log/session.md`.
7. **Check end conditions** (scene cleared, party down, quest beat, human says quit). Loop to step 2 or 3.

---

## 8. `dice.py` spec (authoritative RNG)

- CLI: `python scripts/dice.py "2d6+3" --reason "goblin shortbow damage" --actor world-engine`
- Supports: `NdM`, modifiers, `adv`/`dis` (roll-twice keep high/low), keep-highest/lowest (`4d6kh3` for stat gen), and a `--dc`/`--ac` compare flag that also reports success/failure.
- Output: JSON to stdout `{ "formula", "rolls": [...], "modifier", "total", "vs": {...}, "success": bool|null, "reason", "ts" }`.
- Side effect: append that record to `state/rng_log.jsonl`.
- Reproducibility: honor `RPG_SEED` env var for deterministic test runs.

## 9. `oracle.py` spec (rules/content data)

- Thin wrapper over the Open5e v2 API (`https://api.open5e.com/v2/`). One generic command covers all content types.
- CLI: `python scripts/oracle.py creatures --where name__icontains=goblin --source srd-2024 --fields name,armor_class,hit_points,actions`
- Always injects `document__key__in=<source>` (default `srd-2024`) so results stay within one licensed ruleset.
- Always passes `?fields=` to trim payloads; caches responses under `cache/` keyed by the full query.
- Endpoints to support at minimum: `creatures`, `spells`, `equipment`, `magicitems`, `classes`, `conditions`, plus the cross-dataset `search`.
- Note in `README.md` the CC-BY attribution requirement for SRD content.

---

## 10. Watchability

- **MVP:** `log/session.md` is the canonical "watch" surface — append-only, readable, the human tails it (`tail -f`) or just reads the main-context narration as it streams. Format each turn with a clear header (turn number, scene), the actions taken, the rolls (with results), and the DM's narration.
- **Stretch:** `render_log.py` converts `session.md` to a self-contained `session.html` with a `<meta http-equiv="refresh">` so an open browser tab updates as turns resolve. Keep it dependency-free (string templating, no framework). Do this only after the loop works.

---

## 11. Milestones (build in this order, stop after the slice)

1. **Scaffold + plan.** Create the tree, write `CLAUDE.md` (invariants), `DESIGN.md`, and the three agent stubs with their contracts. **Pause for my review.**
2. **Tools.** Implement and test `dice.py` and `oracle.py` standalone (no agents yet). Show me example outputs and the audit log.
3. **Vertical slice.** One room, one goblin, one *agent* player character, no human, no advanced combat. Drive ~3 turns end-to-end through the full protocol. Prove the blackboard + gate + authoritative rolls + log all work.
4. **Human seat.** Add the terminal prompt path so I can occupy a PC with the same contract. Add the all-actions gate for mixed human+agent parties.
5. **Expand** only after 3–4 are solid: multi-room maps, multiple players, initiative-ordered combat, loot/traps/quests, then the HTML view.

---

## 12. Surface these decisions to me

- Default ruleset/source (proposing SRD 5.2 / `srd-2024`, CC-BY).
- Whether the DM should be a subagent (cleaner role separation, recommended) or fold into the main context (fewer round-trips, less clean). Default to subagent and flag the tradeoff.
- How many concurrent player agents for the first real game (suggest 1, to keep cost/latency sane).
- Anything in this spec you think is over-engineered for an MVP — push back.

## Non-goals (for now)

No persistent web server, no real-time multiplayer, no GUI, no rules engine beyond what the world-engine implements, no content outside the pinned SRD source.
