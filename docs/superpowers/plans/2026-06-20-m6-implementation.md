# M6 Implementation Plan — Quality of Life + Speed

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add inter-PC coordination dialogue before action collection, switch fast agent dispatches to Haiku, and remove the HTML log from the active turn loop.

**Architecture:** Three independent edits to existing files — no new files, no state schema changes. `player.md` gets a new `COORDINATE` mode. `run.md` gets a coordination phase step, model annotations on all dispatch templates, and a `tail` note. `.gitignore` drops `log/session.html`.

**Tech Stack:** Markdown prompt files, `.gitignore`, git CLI.

---

## File map

| File | What changes |
|---|---|
| `.claude/agents/player.md` | Add `COORDINATE` mode (third mode after `CREATE_CHARACTER` and `TAKE_TURN`) |
| `run.md` | Add step 2b (coordination phase); add `model:` annotations to all dispatch templates; add `tail` note to log section |
| `.gitignore` | Add `log/session.html` |
| `DESIGN.md` | Update M6 milestone status to complete |

---

## Task 1: Add COORDINATE mode to player.md

**Files:**
- Modify: `.claude/agents/player.md` — `## Two modes` section

- [ ] **Step 1: Add COORDINATE mode between the two existing modes**

In `.claude/agents/player.md`, replace the `## Two modes` section:

```markdown
## Three modes
**CREATE_CHARACTER** (session start): invent a character — name, class/archetype, personality, goals, a sentence of backstory, and how they tend to approach problems. Request mechanical numbers (ability scores, starting HP, starting gear) from the world-engine by describing what you want; do **not** invent stats or roll them yourself. Return the concept; the orchestrator routes the mechanics.

**COORDINATE** (before a new encounter, when the orchestrator signals it): your character can speak briefly with party members before action collection opens. Nothing is decided here — this is conversation before commitment. The orchestrator passes you the scene and any prior exchange from this coordination round.

Return a **plain string** (not JSON): one or two lines of in-character dialogue. Apply the same voice rules as `description` — no mechanical terms, no numbers. If your character would be quiet, say so in one line ("Stone says nothing, just checks the grip on his sword.").

**TAKE_TURN**: given your sheet + perception packet, declare one action.
```

- [ ] **Step 2: Verify the edit looks right**

Read `.claude/agents/player.md` and confirm:
- `## Three modes` heading (not `## Two modes`)
- `COORDINATE` block appears between `CREATE_CHARACTER` and `TAKE_TURN`
- Output instruction says "plain string (not JSON)"
- Voice rules reminder is present

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/player.md
git commit -m "feat(player): add COORDINATE mode for pre-encounter party dialogue"
```

---

## Task 2: Add coordination phase step to run.md

**Files:**
- Modify: `run.md` — turn loop section, between step 2 and step 3

- [ ] **Step 1: Insert step 2b — Coordination phase**

In `run.md`, after the closing of `### 2. Scene setup` and before `### 3. Collect actions`, insert:

```markdown
### 2b. Coordination phase (optional — runs after scene setup, before action collection)

Skip this step during: looting after a cleared scene, rest sequences, routine movement between cleared rooms.

**Human + agent party:**
1. Print the scene to the human (already done in step 2).
2. Prompt: *"Before you act — anything to say to [agent PC name(s)]? (blank or 'go' to skip)"*
3. If the human types something meaningful (not a signal word):
   a. Print their words in the UI.
   b. Dispatch each agent PC in `COORDINATE` mode (model: haiku) with: the scene prose, the human's message, and the coordination transcript so far.
   c. Print agent response(s) in the UI.
   d. Append the full exchange to `log/session.md` using the format below.
   e. Prompt again: *"Anything else? ('go' to act)"*
   f. Repeat from step 3.
4. When the human types a signal (`go`, `ready`, `done`, blank line, or any clear readiness phrase like "move in" or "let's go"): proceed to step 3.
5. If the human skips step 2 entirely: proceed to step 3 immediately.

**Agent-only party — when to coordinate:**
Run coordination when any of the following is true:
- First turn of an encounter with two or more enemies
- The room contains a noted hazard (trap, puzzle, obscured enemy)
- The previous turn ended with an unexpected outcome (ambush, PC downed, enemy fled)
- The party has not yet faced this enemy type in the session

When triggered: dispatch each agent PC in `COORDINATE` mode (model: haiku) in initiative order. Agent A speaks; Agent B receives the transcript and responds. One round only (each agent speaks once). Append to `log/session.md` and proceed to step 3.

**Coordination log format** (append to `log/session.md` before the Turn heading):
```
**[PC names] — before entering:**
Stone: "Watch the corners when we go in."
Aldric: "I'll hold back unless you need fire."
```
Replace "before entering" with a location cue when relevant: "before crossing the bridge", "before the ambush".
```

- [ ] **Step 2: Verify the insertion**

Read `run.md` and confirm:
- Step 2b appears between `### 2. Scene setup` and `### 3. Collect actions`
- Both human+agent and agent-only protocols are present
- Signal words are listed
- Log format block is included
- "model: haiku" appears in both dispatch calls

- [ ] **Step 3: Commit**

```bash
git add run.md
git commit -m "feat(orchestrator): add inter-PC coordination phase (step 2b)"
```

---

## Task 3: Add model annotations to dispatch templates in run.md

**Files:**
- Modify: `run.md` — `## Dispatch templates` section

- [ ] **Step 1: Replace the dispatch templates section**

In `run.md`, replace the entire `## Dispatch templates` section with:

```markdown
## Dispatch templates (inline in the Agent tool prompt)

Model assignments: **haiku** for fast/bounded tasks, **sonnet** for creative/generative tasks. Pass `model: "haiku"` or `model: "sonnet"` as the `model` parameter in the Agent tool call — this overrides the agent file's frontmatter.

**Player (coordinate):** model: haiku
```
Use the player subagent. MODE: COORDINATE. Turn <n>. You control <actor>.
Scene: <prose>. Sheet: <json>. Prior exchange: <transcript or "none">.
Speak one or two lines in character. Return plain text, not JSON.
```

**Player (take turn):** model: haiku
```
Use the player subagent. MODE: TAKE_TURN. Turn <n>. You control <actor>.
Sheet: <json>. Perception packet: <json>. Return only the action JSON.
```

**Player (create character):** model: sonnet
```
Use the player subagent. MODE: CREATE_CHARACTER.
[character concept prompt]. Return the character concept JSON.
```

**Player (rest):** model: haiku
```
Use the player subagent. MODE: REST. You control <actor>.
Sheet: <json>. You may spend 0 to <N> Hit Dice. Return {"hit_dice_to_spend": N}.
```

**DM (scene setup):** model: sonnet
```
Use the dm subagent. MODE: SCENE_SETUP.
World state: <json>. Goal: <description>. Return the directive JSON.
```

**DM (adjudicate):** model: sonnet
```
Use the dm subagent. MODE: ADJUDICATE. Turn <n>. Initiative: <order>.
Player actions: <json[]>. Resolved facts: <none | world-engine results json>.
Return the directive JSON.
```

**World-engine (generate):** model: sonnet
```
Use the world-engine subagent. MODE: GENERATE.
Scene setup request: <json>. Generate encounter, write map/monsters/encounter files.
```

**World-engine (resolve):** model: haiku
```
Use the world-engine subagent. MODE: RESOLVE.
Mechanic requests: <json[]>. Roll each via dice.py and return rolls + results JSON.
```
```

- [ ] **Step 2: Verify**

Read `run.md` dispatch templates section and confirm:
- Every dispatch template has a `model:` label
- haiku: COORDINATE, TAKE_TURN, REST, RESOLVE
- sonnet: CREATE_CHARACTER, SCENE_SETUP, ADJUDICATE, GENERATE
- New COORDINATE template is present with correct fields

- [ ] **Step 3: Commit**

```bash
git add run.md
git commit -m "feat(orchestrator): annotate dispatch templates with model selection (haiku/sonnet)"
```

---

## Task 4: Log simplification — gitignore and untrack session.html

**Files:**
- Modify: `.gitignore`
- Remove from git tracking: `log/session.html`
- Modify: `run.md` — log format section

- [ ] **Step 1: Add log/session.html to .gitignore**

In `.gitignore`, after the `# Python` block, add:

```
# Generated log artifacts (run scripts/render_log.py manually if needed)
log/session.html
```

- [ ] **Step 2: Untrack log/session.html from git**

`log/session.html` was committed in the initial commit. Remove it from tracking without deleting the file:

```bash
git rm --cached log/session.html
```

Expected output:
```
rm 'log/session.html'
```

- [ ] **Step 3: Verify gitignore works**

```bash
git status
```

Expected: `log/session.html` does NOT appear in modified/untracked files. `.gitignore` appears as modified.

- [ ] **Step 4: Add tail note to run.md log section**

In `run.md`, after the log format code block (the one ending with `**Outcome:** <DM pass-2 narration>`), add:

```markdown
To watch the session live in a terminal: `tail -f log/session.md`

To generate an auto-refreshing HTML view (optional): `python3 scripts/render_log.py`
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore run.md
git commit -m "chore: remove session.html from git tracking; add tail note to run.md"
```

---

## Task 5: Update DESIGN.md and push

**Files:**
- Modify: `DESIGN.md` — M6 milestone entry

- [ ] **Step 1: Update M6 milestone status in DESIGN.md**

In `DESIGN.md`, change the M6 entry from:

```markdown
### M6 — Quality of life + speed
```

to:

```markdown
### ✅ M6 — Quality of life + speed
```

And add a completion summary below the bullet points:

```markdown
**Completed 2026-06-20.** Coordination phase, model selection (haiku/sonnet), and log simplification all landed in one batch.
```

- [ ] **Step 2: Commit and push everything**

```bash
git add DESIGN.md
git commit -m "docs: mark M6 complete in DESIGN.md"
git push
```

Expected output: `main -> main` on `github.com:ceautery/rpg.git`.

- [ ] **Step 3: Verify remote**

```bash
git log --oneline -5
```

Expected: 5 commits visible, newest being the M6 docs commit.

---

## Self-review against spec

| Spec requirement | Covered by |
|---|---|
| COORDINATE mode in player.md | Task 1 |
| Human+agent loop with signal words | Task 2 step 1 |
| Agent-only heuristic triggers | Task 2 step 1 |
| One round for agent-only | Task 2 step 1 |
| Coordination log format | Task 2 step 1 |
| model: haiku for COORDINATE, TAKE_TURN, REST, RESOLVE | Task 3 |
| model: sonnet for CREATE_CHARACTER, SCENE_SETUP, ADJUDICATE, GENERATE | Task 3 |
| render_log.py stays in repo | Not changed — already there |
| session.html removed from git tracking | Task 4 |
| `tail -f` note in run.md | Task 4 step 4 |
| DESIGN.md M6 marked complete | Task 5 |
