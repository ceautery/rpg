# Multi-Agent RPG Simulator

A turn-based tabletop RPG simulation driven by Claude Code subagents. A DM agent runs the world, player agents (and/or a human) play characters, and a world-engine agent is the authoritative source of all randomness and mechanics.

## How to run

```bash
# Start or resume a session
claude   # then: /run
```

The orchestrator's operating procedure is in `run.md`. It drives the entire loop — you just watch or play.

## Watching a session

```bash
tail -f log/session.md
```

`log/session.md` is the append-only human-readable record: scene prose, declared actions, dice results, and narrated outcomes. Every roll in it corresponds to an entry in `state/rng_log.jsonl`.

## Playing as a human

When the orchestrator prompts *"What do you do?"*, type your action in plain English. It will confirm intent/target if ambiguous before committing. Your view is the same perception packet an agent PC would receive — you never see monster stats or hidden traps.

## Prerequisites

- Python 3.9+
- Internet access (for the Open5e API; responses are cached under `cache/`)

No other dependencies. No database, no web server.

## Project layout

```
CLAUDE.md              project invariants (enforced by all agents)
DESIGN.md              architecture notes and open decisions
run.md                 orchestrator operating procedure (the turn loop)
.claude/agents/
  dm.md                DM subagent definition
  player.md            player subagent definition
  world-engine.md      world-engine subagent definition
scripts/
  dice.py              authoritative RNG; appends to rng_log.jsonl
  oracle.py            Open5e API wrapper (pinned to srd-2024)
state/
  public/              readable by everyone including player agents
  secret/              DM + world-engine only (never shown to players)
  actions/             per-turn action inbox
  rng_log.jsonl        append-only audit of every dice roll
log/
  session.md           the watchable session record
cache/                 cached oracle.py API responses
```

## Attribution

Rules content is sourced from the [Open5e API](https://open5e.com/) using the SRD 5.2 dataset (`srd-2024`), which is published under [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/). Content is © Wizards of the Coast LLC and contributors under that license.
