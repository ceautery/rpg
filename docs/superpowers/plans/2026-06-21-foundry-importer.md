# Foundry VTT Importer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `scripts/import_foundry.py` to convert a Foundry VTT NeDB module (zip or directory) into the full `campaign/` file set, ready to play without any further PREGEN dispatch.

**Architecture:** Single-file script, seven sequential phases: load → classify actors → build rooms → build encounters → classify journals → extract NPCs/items → write outputs. No LLM calls. All imported monsters carry `foundry_stats` so the world-engine can fall back when oracle returns nothing. A companion change to `.claude/agents/world-engine.md` teaches the world-engine to use that fallback.

**Tech Stack:** Python 3.10+, stdlib only (`json`, `re`, `zipfile`, `pathlib`, `argparse`, `shutil`, `tempfile`)

## Global Constraints

- No external dependencies — stdlib only
- Output schemas must exactly match the existing `campaign/` JSON (see spec at `docs/superpowers/specs/2026-06-21-foundry-importer-design.md`)
- All monsters from Foundry get a `foundry_stats` field; world-engine tries oracle first, falls back to `foundry_stats` if no result
- HTML stripping: `re.sub(r'<[^>]+>', '', html or '').strip()`
- Room connections default to sequential linear chain (r01 ↔ r02 ↔ r03 …)
- `--force` skips clobber confirmation
- Test command: `pytest tests/test_import_foundry.py -v`
- After a successful import, the campaign is fully ready — do NOT run PREGEN_STRUCTURE, PREGEN_POPULATE, or PREGEN_NARRATIVE

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/import_foundry.py` | Create | All importer logic — loader, classifiers, builders, writers, CLI entry point |
| `tests/test_import_foundry.py` | Create | Full unit + integration test suite |
| `.claude/agents/world-engine.md` | Modify | Add custom monster fallback instruction to GENERATE procedure |

---

### Task 1: File Scaffold + Loader + HTML Stripper

**Files:**
- Create: `scripts/import_foundry.py`
- Create: `tests/test_import_foundry.py`

**Interfaces:**
- Produces:
  - `load_module(path: str) -> dict` — returns `{actors, journals, items, scenes, tables, world}` where `actors/journals/items/tables` are `dict[str, dict]` keyed by `_id`, and `scenes` is `list[dict]` sorted by `navOrder`
  - `strip_html(html: str | None) -> str` — returns plain text

- [ ] **Step 1: Write the failing tests**

Create `tests/test_import_foundry.py`:

```python
import json
import zipfile
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from import_foundry import load_module, strip_html


def make_module_dir(tmp_path, actors="", journals="", items="", scenes="", tables="", world=None):
    """Helper: write a minimal Foundry module directory."""
    mod = tmp_path / "module"
    data = mod / "data"
    data.mkdir(parents=True)
    (data / "actors.db").write_text(actors)
    (data / "journal.db").write_text(journals)
    (data / "items.db").write_text(items)
    (data / "scenes.db").write_text(scenes)
    (data / "tables.db").write_text(tables)
    (mod / "world.json").write_text(json.dumps(world or {"title": "Test Module", "description": "A test."}))
    return mod


def make_module_zip(tmp_path, **kwargs):
    """Helper: write a minimal Foundry module zip."""
    mod_dir = make_module_dir(tmp_path / "src", **kwargs)
    zip_path = tmp_path / "module.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in mod_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(tmp_path / "src"))
    return zip_path


# --- strip_html ---

def test_strip_html_removes_tags():
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"

def test_strip_html_empty_string():
    assert strip_html("") == ""

def test_strip_html_none():
    assert strip_html(None) == ""

def test_strip_html_plain_text():
    assert strip_html("No tags here") == "No tags here"

def test_strip_html_nested():
    assert strip_html("<div><p>Deep <em>text</em></p></div>") == "Deep text"


# --- load_module from directory ---

def test_load_module_from_dir_indexes_actors(tmp_path):
    actor_line = json.dumps({"_id": "a1", "name": "Kobold"})
    mod = make_module_dir(tmp_path, actors=actor_line + "\n")
    data = load_module(str(mod))
    assert "a1" in data["actors"]
    assert data["actors"]["a1"]["name"] == "Kobold"

def test_load_module_from_dir_reads_world(tmp_path):
    mod = make_module_dir(tmp_path, world={"title": "My Adventure", "description": "Cool stuff."})
    data = load_module(str(mod))
    assert data["world"]["title"] == "My Adventure"

def test_load_module_from_dir_sorts_scenes_by_nav_order(tmp_path):
    scenes = "\n".join([
        json.dumps({"_id": "s3", "name": "Room C", "navOrder": 3}),
        json.dumps({"_id": "s1", "name": "Room A", "navOrder": 1}),
        json.dumps({"_id": "s2", "name": "Room B", "navOrder": 2}),
    ])
    mod = make_module_dir(tmp_path, scenes=scenes)
    data = load_module(str(mod))
    assert [s["_id"] for s in data["scenes"]] == ["s1", "s2", "s3"]

def test_load_module_from_dir_handles_empty_db(tmp_path):
    mod = make_module_dir(tmp_path)  # all dbs are empty string
    data = load_module(str(mod))
    assert data["actors"] == {}
    assert data["scenes"] == []


# --- load_module from zip ---

def test_load_module_from_zip(tmp_path):
    actor_line = json.dumps({"_id": "a1", "name": "Goblin"})
    zip_path = make_module_zip(tmp_path, actors=actor_line + "\n",
                               world={"title": "Zip Test", "description": "Zipped."})
    data = load_module(str(zip_path))
    assert data["world"]["title"] == "Zip Test"
    assert "a1" in data["actors"]

def test_load_module_raises_on_missing_data_dir(tmp_path):
    bad = tmp_path / "empty"
    bad.mkdir()
    with pytest.raises(ValueError, match="No data/actors.db"):
        load_module(str(bad))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/curtis/dev/claude_projects/rpg
pytest tests/test_import_foundry.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'import_foundry'`

- [ ] **Step 3: Implement scaffold, loader, and HTML stripper**

Create `scripts/import_foundry.py`:

```python
"""Import a Foundry VTT NeDB module into campaign/ files."""
import argparse
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------

def strip_html(html: str | None) -> str:
    return re.sub(r'<[^>]+>', '', html or '').strip()


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_module(path: str) -> dict:
    """Load a Foundry module from a zip or directory. Returns indexed data."""
    p = Path(path)
    if p.suffix == '.zip':
        return _load_from_zip(p)
    return _load_from_dir(p)


def _parse_db(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _index(records: list[dict]) -> dict:
    return {r['_id']: r for r in records}


def _load_from_dir(p: Path) -> dict:
    # data/ may be nested inside a subdirectory
    candidates = [d for d in p.rglob('data') if (d / 'actors.db').exists()]
    if not candidates:
        raise ValueError(f"No data/actors.db found under {p}")
    data_dir = candidates[0]

    world_files = list(p.rglob('world.json'))
    world = json.loads(world_files[0].read_text()) if world_files else {}

    def read(name: str) -> list[dict]:
        f = data_dir / name
        return _parse_db(f.read_text()) if f.exists() else []

    return {
        'actors':   _index(read('actors.db')),
        'journals': _index(read('journal.db')),
        'items':    _index(read('items.db')),
        'scenes':   sorted(read('scenes.db'), key=lambda s: s.get('navOrder', 0)),
        'tables':   _index(read('tables.db')),
        'world':    world,
    }


def _load_from_zip(p: Path) -> dict:
    tmp = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(p) as zf:
            zf.extractall(tmp)
        return _load_from_dir(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Placeholder main (expanded in Task 6)
# ---------------------------------------------------------------------------

def main():
    pass


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_import_foundry.py -v -k "strip_html or load_module"
```

Expected: all `test_strip_html_*` and `test_load_module_*` tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/import_foundry.py tests/test_import_foundry.py
git commit -m "feat(importer): scaffold loader and HTML stripper"
```

---

### Task 2: Actor Classifier + Room Builder

**Files:**
- Modify: `scripts/import_foundry.py`
- Modify: `tests/test_import_foundry.py`

**Interfaces:**
- Consumes: `load_module()` output
- Produces:
  - `classify_actors(actors: dict) -> tuple[dict, dict]` — returns `(monsters_by_id, npcs_by_id)`; a monster has `data.details.cr` set and `token.disposition != 1`
  - `infer_room_type(name: str, content: str) -> str` — returns one of `entrance|corridor|chamber|vault|boss`
  - `build_rooms(scenes: list, journals: dict, monsters_by_id: dict) -> list[dict]` — returns dungeon.json room array
  - `build_config(world: dict, room_count: int) -> dict` — returns config.json dict

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_import_foundry.py`:

```python
from import_foundry import classify_actors, infer_room_type, build_rooms, build_config


# Shared fixtures
ACTOR_MONSTER = {
    "_id": "am1", "name": "Kobold", "type": "npc",
    "token": {"disposition": -1},
    "data": {
        "details": {"cr": "1/8", "biography": {"value": ""}},
        "attributes": {"ac": {"value": 12}, "hp": {"max": 5}, "movement": {"walk": 30}},
        "abilities": {"str": {"value": 7}, "dex": {"value": 15}, "con": {"value": 9},
                      "int": {"value": 8}, "wis": {"value": 7}, "cha": {"value": 8}},
    },
    "items": [],
}

ACTOR_NPC = {
    "_id": "an1", "name": "Kollias", "type": "npc",
    "token": {"disposition": 1},
    "data": {
        "details": {"cr": None, "biography": {"value": "<p>A loyal guard.</p>"}},
        "attributes": {"ac": {"value": 16}, "hp": {"max": 52}, "movement": {"walk": 30}},
        "abilities": {"str": {"value": 16}, "dex": {"value": 12}, "con": {"value": 14},
                      "int": {"value": 10}, "wis": {"value": 11}, "cha": {"value": 10}},
    },
    "items": [],
}

SCENE_1 = {
    "_id": "sc1", "name": "Entrance Hall", "navOrder": 1,
    "journal": "j1",
    "tokens": [
        {"_id": "t1", "actorId": "am1"},
        {"_id": "t2", "actorId": "am1"},
    ],
}

JOURNAL_1 = {
    "_id": "j1", "name": "Entrance Hall",
    "content": "<p>A wide stone hall.</p>",
}


# --- classify_actors ---

def test_classify_actors_monster_by_disposition():
    monsters, npcs = classify_actors({"am1": ACTOR_MONSTER})
    assert "am1" in monsters
    assert "am1" not in npcs

def test_classify_actors_npc_by_disposition():
    monsters, npcs = classify_actors({"an1": ACTOR_NPC})
    assert "an1" in npcs
    assert "an1" not in monsters

def test_classify_actors_no_cr_is_npc():
    actor = dict(ACTOR_MONSTER)
    actor = {**ACTOR_MONSTER, "_id": "ax1",
             "data": {**ACTOR_MONSTER["data"],
                      "details": {"cr": None, "biography": {"value": ""}}},
             "token": {"disposition": -1}}
    monsters, npcs = classify_actors({"ax1": actor})
    assert "ax1" in npcs  # no CR means NPC even if hostile disposition

def test_classify_actors_mixed():
    monsters, npcs = classify_actors({"am1": ACTOR_MONSTER, "an1": ACTOR_NPC})
    assert "am1" in monsters and "an1" in npcs


# --- infer_room_type ---

def test_infer_room_type_entrance():
    assert infer_room_type("Entrance Hall", "") == "entrance"

def test_infer_room_type_boss():
    assert infer_room_type("The Dragon's Lair", "") == "boss"

def test_infer_room_type_vault():
    assert infer_room_type("Treasury Vault", "") == "vault"

def test_infer_room_type_corridor():
    assert infer_room_type("Dark Corridor", "") == "corridor"

def test_infer_room_type_default_chamber():
    assert infer_room_type("Meeting Room", "") == "chamber"

def test_infer_room_type_checks_content():
    assert infer_room_type("Side Room", "the boss waits here") == "boss"


# --- build_rooms + build_config ---

def test_build_rooms_basic():
    monsters = {"am1": ACTOR_MONSTER}
    rooms = build_rooms([SCENE_1], {"j1": JOURNAL_1}, monsters)
    assert len(rooms) == 1
    r = rooms[0]
    assert r["id"] == "r01"
    assert r["type"] == "entrance"
    assert r["room_type"] == "combat"
    assert r["description"] == "A wide stone hall."
    assert r["encounter"] == "enc_r01"
    assert r["loot"] == "loot_r01"
    assert r["trap"] is None
    assert r["spotlight"] is None

def test_build_rooms_connections_sequential():
    scene2 = {**SCENE_1, "_id": "sc2", "name": "Back Room", "navOrder": 2,
              "journal": None, "tokens": []}
    rooms = build_rooms([SCENE_1, scene2], {"j1": JOURNAL_1}, {})
    assert "r02" in rooms[0]["connections"]
    assert "r01" in rooms[1]["connections"]

def test_build_rooms_social_if_no_hostile_tokens():
    scene = {**SCENE_1, "tokens": [{"_id": "t1", "actorId": "an1"}]}
    npcs = {"an1": ACTOR_NPC}
    # npcs are not in monsters_by_id — so no hostile tokens
    rooms = build_rooms([scene], {"j1": JOURNAL_1}, {})
    assert rooms[0]["room_type"] == "social"

def test_build_config():
    world = {"title": "Kobold Cauldron", "description": "A fiery adventure."}
    cfg = build_config(world, room_count=5)
    assert cfg["name"] == "Kobold Cauldron"
    assert cfg["theme"] == "A fiery adventure."
    assert cfg["room_count"] == 5
    assert cfg["party_level"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_import_foundry.py -v -k "classify or infer_room or build_rooms or build_config"
```

Expected: `ImportError` — functions not yet defined

- [ ] **Step 3: Implement classifier and room builder**

Append to `scripts/import_foundry.py` (before `main()`):

```python
# ---------------------------------------------------------------------------
# Actor classifier
# ---------------------------------------------------------------------------

def classify_actors(actors: dict) -> tuple[dict, dict]:
    """Split actors into (monsters_by_id, npcs_by_id).

    Monster: has a CR value AND token disposition is not friendly (1).
    NPC: friendly disposition OR no CR.
    """
    monsters, npcs = {}, {}
    for aid, actor in actors.items():
        cr = (actor.get('data') or {}).get('details', {}).get('cr')
        disposition = (actor.get('token') or {}).get('disposition', 0)
        if cr and disposition != 1:
            monsters[aid] = actor
        else:
            npcs[aid] = actor
    return monsters, npcs


# ---------------------------------------------------------------------------
# Room type heuristic
# ---------------------------------------------------------------------------

_ROOM_TYPE_KEYWORDS = [
    ('boss',     ['boss', 'dragon', 'lord', 'chief', 'king', 'queen', 'warlord']),
    ('vault',    ['vault', 'treasury', 'store', 'armory', 'armour']),
    ('entrance', ['entrance', 'gate', 'road', 'foyer', 'lobby']),
    ('corridor', ['corridor', 'hall', 'passage', 'tunnel', 'path']),
]

def infer_room_type(name: str, content: str) -> str:
    text = (name + ' ' + content).lower()
    for room_type, keywords in _ROOM_TYPE_KEYWORDS:
        if any(kw in text for kw in keywords):
            return room_type
    return 'chamber'


# ---------------------------------------------------------------------------
# Room builder
# ---------------------------------------------------------------------------

def build_rooms(scenes: list, journals: dict, monsters_by_id: dict) -> list[dict]:
    """Build dungeon.json room array from scenes."""
    rooms = []
    n = len(scenes)
    for i, scene in enumerate(scenes):
        rid = f"r{i + 1:02d}"

        # Resolve description from linked journal
        journal_id = scene.get('journal')
        journal = journals.get(journal_id) if journal_id else None
        description = strip_html(journal.get('content', '') if journal else
                                 scene.get('description', ''))

        # Room type
        journal_content = strip_html(journal.get('content', '') if journal else '')
        room_type_key = infer_room_type(scene.get('name', ''), journal_content)

        # Room encounter type: combat if any hostile token's actor is in monsters_by_id
        actor_ids_in_scene = {t.get('actorId') for t in scene.get('tokens', [])}
        has_hostile = any(aid in monsters_by_id for aid in actor_ids_in_scene)
        room_encounter_type = 'combat' if has_hostile else 'social'

        # Sequential connections
        connections = []
        if i > 0:
            connections.append(f"r{i:02d}")
        if i < n - 1:
            connections.append(f"r{i + 2:02d}")

        rooms.append({
            'id': rid,
            'type': room_type_key,
            'room_type': room_encounter_type,
            'description': description,
            'connections': connections,
            'encounter': f'enc_{rid}',
            'loot': f'loot_{rid}',
            'trap': None,
            'spotlight': None,
        })
    return rooms


# ---------------------------------------------------------------------------
# Config builder
# ---------------------------------------------------------------------------

def build_config(world: dict, room_count: int) -> dict:
    description = world.get('description', '')
    # First sentence only for theme
    theme = re.split(r'[.!?]', strip_html(description))[0].strip()
    return {
        'name': world.get('title', 'Imported Campaign'),
        'theme': theme,
        'room_count': room_count,
        'party_level': 3,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_import_foundry.py -v -k "classify or infer_room or build_rooms or build_config"
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/import_foundry.py tests/test_import_foundry.py
git commit -m "feat(importer): add actor classifier and room builder"
```

---

### Task 3: Encounter Builder

**Files:**
- Modify: `scripts/import_foundry.py`
- Modify: `tests/test_import_foundry.py`

**Interfaces:**
- Consumes: `scenes` list, `actors` dict (all actors, indexed by `_id`), `rooms` list (from `build_rooms`)
- Produces:
  - `build_encounters(scenes: list, actors: dict, rooms: list) -> dict` — returns encounters.json dict keyed by `enc_r01`, `loot_r01`, etc.
  - Each monster entry: `{monster, count, cr, ac, hp, foundry_stats: {abilities, speed, attacks}}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_import_foundry.py`:

```python
from import_foundry import build_encounters

ACTOR_CUSTOM = {
    "_id": "ac1", "name": "Booze Server Kobold", "type": "npc",
    "token": {"disposition": -1},
    "data": {
        "details": {"cr": "1/8", "biography": {"value": ""}},
        "attributes": {"ac": {"value": 12}, "hp": {"max": 5}, "movement": {"walk": 30}},
        "abilities": {"str": {"value": 7}, "dex": {"value": 15}, "con": {"value": 9},
                      "int": {"value": 8}, "wis": {"value": 7}, "cha": {"value": 8}},
    },
    "items": [
        {
            "name": "Dagger", "type": "weapon",
            "data": {
                "actionType": "mwak",
                "attackBonus": 4,
                "damage": {"parts": [["1d4+2", "piercing"]]},
            },
        }
    ],
}

SCENE_WITH_TOKENS = {
    "_id": "sc1", "name": "Entrance", "navOrder": 1,
    "journal": None,
    "tokens": [
        {"_id": "t1", "actorId": "am1"},
        {"_id": "t2", "actorId": "am1"},
        {"_id": "t3", "actorId": "ac1"},
    ],
}

ROOMS_1 = [{"id": "r01", "encounter": "enc_r01", "loot": "loot_r01"}]


def test_build_encounters_groups_same_actor():
    actors = {"am1": ACTOR_MONSTER, "ac1": ACTOR_CUSTOM}
    enc = build_encounters([SCENE_WITH_TOKENS], actors, ROOMS_1)
    monsters = enc["enc_r01"]
    kobold = next(m for m in monsters if m["monster"] == "kobold")
    assert kobold["count"] == 2

def test_build_encounters_extracts_cr_ac_hp():
    actors = {"am1": ACTOR_MONSTER}
    scene = {**SCENE_WITH_TOKENS, "tokens": [{"_id": "t1", "actorId": "am1"}]}
    enc = build_encounters([scene], actors, ROOMS_1)
    m = enc["enc_r01"][0]
    assert m["cr"] == "1/8"
    assert m["ac"] == 12
    assert m["hp"] == 5

def test_build_encounters_includes_foundry_stats():
    actors = {"ac1": ACTOR_CUSTOM}
    scene = {**SCENE_WITH_TOKENS, "tokens": [{"_id": "t1", "actorId": "ac1"}]}
    enc = build_encounters([scene], actors, ROOMS_1)
    m = enc["enc_r01"][0]
    assert "foundry_stats" in m
    assert m["foundry_stats"]["abilities"]["dex"] == 15
    assert m["foundry_stats"]["speed"] == 30

def test_build_encounters_extracts_weapon_attacks():
    actors = {"ac1": ACTOR_CUSTOM}
    scene = {**SCENE_WITH_TOKENS, "tokens": [{"_id": "t1", "actorId": "ac1"}]}
    enc = build_encounters([scene], actors, ROOMS_1)
    attacks = enc["enc_r01"][0]["foundry_stats"]["attacks"]
    assert len(attacks) == 1
    assert attacks[0]["name"] == "Dagger"
    assert attacks[0]["damage"] == "1d4+2"

def test_build_encounters_loot_placeholder_when_no_items():
    actors = {"am1": ACTOR_MONSTER}
    scene = {**SCENE_WITH_TOKENS, "tokens": [{"_id": "t1", "actorId": "am1"}]}
    enc = build_encounters([scene], actors, ROOMS_1)
    assert enc["loot_r01"] == [{"item": "gold", "amount_gp": 0}]

def test_build_encounters_empty_scene():
    scene = {**SCENE_WITH_TOKENS, "tokens": []}
    enc = build_encounters([scene], {}, ROOMS_1)
    assert enc["enc_r01"] == []
    assert enc["loot_r01"] == [{"item": "gold", "amount_gp": 0}]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_import_foundry.py -v -k "build_encounters"
```

Expected: `ImportError` — `build_encounters` not yet defined

- [ ] **Step 3: Implement encounter builder**

Append to `scripts/import_foundry.py` (before `main()`):

```python
# ---------------------------------------------------------------------------
# Encounter builder
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def _extract_foundry_stats(actor: dict) -> dict:
    data = actor.get('data', {})
    attrs = data.get('attributes', {})
    abilities_raw = data.get('abilities', {})
    abilities = {k: v.get('value', 10) for k, v in abilities_raw.items()}

    attacks = []
    for item in actor.get('items', []):
        idata = item.get('data', {})
        if item.get('type') in ('weapon', 'feat') and idata.get('actionType'):
            parts = idata.get('damage', {}).get('parts', [])
            attacks.append({
                'name': item.get('name', 'Attack'),
                'attack_bonus': idata.get('attackBonus', 0),
                'damage': parts[0][0] if parts else '1',
                'type': parts[0][1] if parts else 'bludgeoning',
            })

    movement = attrs.get('movement', {})
    speed = movement.get('walk', 30) if isinstance(movement, dict) else 30

    return {
        'abilities': abilities,
        'speed': speed,
        'attacks': attacks,
    }


def build_encounters(scenes: list, actors: dict, rooms: list) -> dict:
    """Build encounters.json dict from scene token placements."""
    result = {}
    for i, scene in enumerate(scenes):
        room = rooms[i]
        enc_key = room['encounter']
        loot_key = room['loot']

        # Group tokens by actorId, count instances
        counts: dict[str, int] = {}
        for token in scene.get('tokens', []):
            aid = token.get('actorId')
            if aid and aid in actors:
                counts[aid] = counts.get(aid, 0) + 1

        monsters = []
        for aid, count in counts.items():
            actor = actors[aid]
            data = actor.get('data', {})
            attrs = data.get('attributes', {})

            ac_field = attrs.get('ac', {})
            ac = ac_field.get('value') or ac_field.get('flat') or 10
            hp = attrs.get('hp', {}).get('max', 1)
            cr = data.get('details', {}).get('cr', '0')

            entry = {
                'monster': _slugify(actor.get('name', 'unknown')),
                'count': count,
                'cr': cr,
                'ac': ac,
                'hp': hp,
                'foundry_stats': _extract_foundry_stats(actor),
            }
            monsters.append(entry)

        result[enc_key] = monsters
        result[loot_key] = [{'item': 'gold', 'amount_gp': 0}]

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_import_foundry.py -v -k "build_encounters"
```

Expected: all `test_build_encounters_*` tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/import_foundry.py tests/test_import_foundry.py
git commit -m "feat(importer): add encounter builder with foundry_stats fallback"
```

---

### Task 4: Journal Classifier

**Files:**
- Modify: `scripts/import_foundry.py`
- Modify: `tests/test_import_foundry.py`

**Interfaces:**
- Consumes: `journals: dict[str, dict]`, `linked_ids: set[str]` (journal IDs already used as room descriptions)
- Produces:
  - `classify_journals(journals: dict, linked_ids: set) -> tuple[list, list, list]` — returns `(quests, foreshadowing_seeds, lore_entries)`
  - Quest schema: `{id, title, hook, objectives: [{id, desc, completed}], reward: {xp, gold, narrative}}`
  - Foreshadowing schema: `{id, detail, planted_in, pays_off_in, payoff, dm_hint}`
  - Lore schema: `{id, title, content}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_import_foundry.py`:

```python
from import_foundry import classify_journals

JOURNAL_QUEST = {
    "_id": "jq1", "name": "Rescue the Prisoners",
    "content": "<p>The party must rescue captives.</p><ul><li>Find them</li><li>Escape</li></ul><p>Reward: 200 gp for the effort.</p>",
}
JOURNAL_FORESHADOW = {
    "_id": "jf1", "name": "A Dark Omen",
    "content": "<p>A prophecy carved in stone foretells ruin.</p><p>The payoff comes later.</p>",
}
JOURNAL_LORE = {
    "_id": "jl1", "name": "History of the Cauldron",
    "content": "<p>The kobolds have held this distillery for three generations.</p>",
}


def test_classify_journals_skips_linked_ids():
    journals = {"jq1": JOURNAL_QUEST}
    quests, _, _ = classify_journals(journals, linked_ids={"jq1"})
    assert quests == []

def test_classify_journals_detects_quest():
    journals = {"jq1": JOURNAL_QUEST}
    quests, foreshadowing, lore = classify_journals(journals, linked_ids=set())
    assert len(quests) == 1
    assert quests[0]["title"] == "Rescue the Prisoners"

def test_classify_journals_quest_hook_is_first_paragraph():
    journals = {"jq1": JOURNAL_QUEST}
    quests, _, _ = classify_journals(journals, linked_ids=set())
    assert quests[0]["hook"] == "The party must rescue captives."

def test_classify_journals_quest_objectives_from_list_items():
    journals = {"jq1": JOURNAL_QUEST}
    quests, _, _ = classify_journals(journals, linked_ids=set())
    assert len(quests[0]["objectives"]) == 2
    assert quests[0]["objectives"][0]["desc"] == "Find them"
    assert quests[0]["objectives"][0]["completed"] is False

def test_classify_journals_quest_default_reward():
    journals = {"jq1": JOURNAL_QUEST}
    quests, _, _ = classify_journals(journals, linked_ids=set())
    # reward keys present even if parsing fails
    assert "xp" in quests[0]["reward"]
    assert "gold" in quests[0]["reward"]

def test_classify_journals_detects_foreshadowing():
    journals = {"jf1": JOURNAL_FORESHADOW}
    _, foreshadowing, _ = classify_journals(journals, linked_ids=set())
    assert len(foreshadowing) == 1
    assert foreshadowing[0]["detail"] == "A prophecy carved in stone foretells ruin."
    assert foreshadowing[0]["planted_in"] is None

def test_classify_journals_lore_fallback():
    journals = {"jl1": JOURNAL_LORE}
    _, _, lore = classify_journals(journals, linked_ids=set())
    assert len(lore) == 1
    assert lore[0]["title"] == "History of the Cauldron"

def test_classify_journals_ids_are_sequential():
    journals = {"jq1": JOURNAL_QUEST, "jq2": {**JOURNAL_QUEST, "_id": "jq2"}}
    quests, _, _ = classify_journals(journals, linked_ids=set())
    ids = [q["id"] for q in quests]
    assert "q01" in ids and "q02" in ids
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_import_foundry.py -v -k "classify_journals"
```

Expected: `ImportError` — `classify_journals` not yet defined

- [ ] **Step 3: Implement journal classifier**

Append to `scripts/import_foundry.py` (before `main()`):

```python
# ---------------------------------------------------------------------------
# Journal classifier
# ---------------------------------------------------------------------------

_QUEST_KEYWORDS = {'quest', 'mission', 'objective', 'reward', 'bounty'}
_FORESHADOW_KEYWORDS = {'secret', 'prophecy', 'omen', 'foreshadow', 'portent'}


def _classify_entry(entry: dict) -> str:
    text = (entry.get('name', '') + ' ' + strip_html(entry.get('content', ''))).lower()
    if any(kw in text for kw in _QUEST_KEYWORDS):
        return 'quest'
    if any(kw in text for kw in _FORESHADOW_KEYWORDS):
        return 'foreshadowing'
    return 'lore'


def _parse_list_items(html: str) -> list[str]:
    items = re.findall(r'<li[^>]*>(.*?)</li>', html, re.IGNORECASE | re.DOTALL)
    return [strip_html(item) for item in items if strip_html(item)]


def _first_paragraph(html: str) -> str:
    m = re.search(r'<p[^>]*>(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
    return strip_html(m.group(1)) if m else strip_html(html)


def _map_to_quest(entry: dict, idx: int) -> dict:
    content = entry.get('content', '')
    hook = _first_paragraph(content)
    list_items = _parse_list_items(content)
    objectives = (
        [{'id': f"q{idx:02d}_o{j + 1}", 'desc': desc, 'completed': False}
         for j, desc in enumerate(list_items)]
        if list_items else
        [{'id': f"q{idx:02d}_o1", 'desc': 'See DM notes.', 'completed': False}]
    )
    # Naive gold parse: find first integer after "gp" mention
    gold_match = re.search(r'(\d+)\s*gp', strip_html(content), re.IGNORECASE)
    xp_match = re.search(r'(\d+)\s*xp', strip_html(content), re.IGNORECASE)
    return {
        'id': f"q{idx:02d}",
        'title': entry.get('name', ''),
        'hook': hook,
        'objectives': objectives,
        'reward': {
            'xp': int(xp_match.group(1)) if xp_match else 0,
            'gold': int(gold_match.group(1)) if gold_match else 0,
            'narrative': '',
        },
    }


def _map_to_foreshadowing(entry: dict, idx: int) -> dict:
    content = entry.get('content', '')
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', content, re.IGNORECASE | re.DOTALL)
    detail = strip_html(paragraphs[0]) if paragraphs else strip_html(content)
    dm_hint = ' '.join(strip_html(p) for p in paragraphs[1:]) if len(paragraphs) > 1 else ''
    return {
        'id': f"fs{idx:02d}",
        'detail': detail,
        'planted_in': None,
        'pays_off_in': None,
        'payoff': '',
        'dm_hint': dm_hint,
    }


def classify_journals(journals: dict, linked_ids: set) -> tuple[list, list, list]:
    """Classify unlinked journals into quests, foreshadowing seeds, and lore."""
    quests, foreshadowing, lore = [], [], []
    q_idx = fs_idx = lore_idx = 1

    for jid, entry in journals.items():
        if jid in linked_ids:
            continue
        kind = _classify_entry(entry)
        if kind == 'quest':
            quests.append(_map_to_quest(entry, q_idx))
            q_idx += 1
        elif kind == 'foreshadowing':
            foreshadowing.append(_map_to_foreshadowing(entry, fs_idx))
            fs_idx += 1
        else:
            lore.append({
                'id': f"lore_{lore_idx:02d}",
                'title': entry.get('name', ''),
                'content': strip_html(entry.get('content', '')),
            })
            lore_idx += 1

    return quests, foreshadowing, lore
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_import_foundry.py -v -k "classify_journals"
```

Expected: all `test_classify_journals_*` tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/import_foundry.py tests/test_import_foundry.py
git commit -m "feat(importer): add journal classifier for quests, foreshadowing, lore"
```

---

### Task 5: NPC + Item Extractor

**Files:**
- Modify: `scripts/import_foundry.py`
- Modify: `tests/test_import_foundry.py`

**Interfaces:**
- Consumes: `npcs_by_id: dict`, `scenes: list`, `rooms: list`, `items: dict`
- Produces:
  - `build_npcs(npcs_by_id: dict, scenes: list, rooms: list) -> list[dict]`
  - `build_named_items(items: dict) -> list[dict]`
  - NPC schema: `{id, name, room, goal, disposition}`
  - Item schema: `{id, name, type, in_room, description, secret, investigation_dc, value}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_import_foundry.py`:

```python
from import_foundry import build_npcs, build_named_items

ITEM_1 = {
    "_id": "item1", "name": "Red Claw Regalia", "type": "equipment",
    "data": {
        "description": {"value": "<p>A gilded breastplate.</p>"},
        "price": 250,
    },
}

SCENE_WITH_NPC = {
    "_id": "sc1", "name": "Tavern", "navOrder": 1,
    "journal": None,
    "tokens": [{"_id": "t1", "actorId": "an1"}],
}

ROOMS_WITH_ID = [{"id": "r01"}]


def test_build_npcs_maps_name_and_id():
    npcs = build_npcs({"an1": ACTOR_NPC}, [SCENE_WITH_NPC], ROOMS_WITH_ID)
    assert len(npcs) == 1
    assert npcs[0]["name"] == "Kollias"
    assert npcs[0]["id"] == "kollias"

def test_build_npcs_room_from_token_placement():
    npcs = build_npcs({"an1": ACTOR_NPC}, [SCENE_WITH_NPC], ROOMS_WITH_ID)
    assert npcs[0]["room"] == "r01"

def test_build_npcs_goal_from_biography():
    npcs = build_npcs({"an1": ACTOR_NPC}, [SCENE_WITH_NPC], ROOMS_WITH_ID)
    assert npcs[0]["goal"] == "A loyal guard."

def test_build_npcs_disposition_friendly():
    npcs = build_npcs({"an1": ACTOR_NPC}, [SCENE_WITH_NPC], ROOMS_WITH_ID)
    assert npcs[0]["disposition"] == "friendly"

def test_build_npcs_null_room_when_not_placed():
    npcs = build_npcs({"an1": ACTOR_NPC}, [], [])
    assert npcs[0]["room"] is None

def test_build_named_items_basic():
    items = build_named_items({"item1": ITEM_1})
    assert len(items) == 1
    it = items[0]
    assert it["name"] == "Red Claw Regalia"
    assert it["id"] == "red-claw-regalia"
    assert it["description"] == "A gilded breastplate."
    assert it["value"] == 250
    assert it["in_room"] is None
    assert it["secret"] is None
    assert it["investigation_dc"] is None

def test_build_named_items_type():
    items = build_named_items({"item1": ITEM_1})
    assert items[0]["type"] == "equipment"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_import_foundry.py -v -k "build_npcs or build_named_items"
```

Expected: `ImportError` — functions not yet defined

- [ ] **Step 3: Implement NPC and item extractors**

Append to `scripts/import_foundry.py` (before `main()`):

```python
# ---------------------------------------------------------------------------
# NPC extractor
# ---------------------------------------------------------------------------

_DISPOSITION_MAP = {1: 'friendly', 0: 'neutral', -1: 'hostile'}


def build_npcs(npcs_by_id: dict, scenes: list, rooms: list) -> list[dict]:
    """Map friendly actors to npcs.json entries."""
    # Build actor_id → room_id lookup from token placements
    actor_room: dict[str, str] = {}
    for i, scene in enumerate(scenes):
        rid = rooms[i]['id'] if i < len(rooms) else None
        for token in scene.get('tokens', []):
            aid = token.get('actorId')
            if aid and rid and aid not in actor_room:
                actor_room[aid] = rid

    result = []
    for aid, actor in npcs_by_id.items():
        data = actor.get('data', {})
        bio_html = data.get('details', {}).get('biography', {}).get('value', '')
        bio_text = strip_html(bio_html)
        # First sentence
        goal = re.split(r'[.!?]', bio_text)[0].strip() if bio_text else ''

        disposition_int = (actor.get('token') or {}).get('disposition', 1)
        disposition = _DISPOSITION_MAP.get(disposition_int, 'neutral')

        result.append({
            'id': _slugify(actor.get('name', aid)),
            'name': actor.get('name', aid),
            'room': actor_room.get(aid),
            'goal': goal,
            'disposition': disposition,
        })
    return result


# ---------------------------------------------------------------------------
# Named item extractor
# ---------------------------------------------------------------------------

def build_named_items(items: dict) -> list[dict]:
    """Map items.db entries to named_items.json entries."""
    result = []
    for iid, item in items.items():
        data = item.get('data', {})
        desc_html = data.get('description', {}).get('value', '')
        result.append({
            'id': _slugify(item.get('name', iid)),
            'name': item.get('name', iid),
            'type': item.get('type', 'loot'),
            'in_room': None,
            'description': strip_html(desc_html),
            'secret': None,
            'investigation_dc': None,
            'value': data.get('price'),
        })
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_import_foundry.py -v -k "build_npcs or build_named_items"
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/import_foundry.py tests/test_import_foundry.py
git commit -m "feat(importer): add NPC and named item extractors"
```

---

### Task 6: Main Entry Point + Output Writer + Integration Test

**Files:**
- Modify: `scripts/import_foundry.py` — replace `main()` stub
- Modify: `tests/test_import_foundry.py` — add integration test

**Interfaces:**
- Consumes: all builder functions from Tasks 1–5
- Produces: complete `campaign/` file set written to disk; summary printed to stdout

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_import_foundry.py`:

```python
import subprocess
from import_foundry import run_import

KOBOLD_ZIP = Path(__file__).parent.parent / "tmp" / "kobold-cauldron.zip"


def test_run_import_writes_all_campaign_files(tmp_path):
    """Integration test against the kobold-cauldron module."""
    if not KOBOLD_ZIP.exists():
        pytest.skip("kobold-cauldron.zip not present")
    run_import(str(KOBOLD_ZIP), campaign_dir=tmp_path, force=True)
    for fname in ("config.json", "dungeon.json", "encounters.json",
                  "npcs.json", "named_items.json", "quests.json", "foreshadowing.json"):
        assert (tmp_path / fname).exists(), f"Missing {fname}"

def test_run_import_dungeon_has_rooms(tmp_path):
    if not KOBOLD_ZIP.exists():
        pytest.skip("kobold-cauldron.zip not present")
    run_import(str(KOBOLD_ZIP), campaign_dir=tmp_path, force=True)
    rooms = json.loads((tmp_path / "dungeon.json").read_text())
    assert len(rooms) == 5  # kobold-cauldron has 5 scenes

def test_run_import_encounters_keyed_by_room(tmp_path):
    if not KOBOLD_ZIP.exists():
        pytest.skip("kobold-cauldron.zip not present")
    run_import(str(KOBOLD_ZIP), campaign_dir=tmp_path, force=True)
    enc = json.loads((tmp_path / "encounters.json").read_text())
    assert "enc_r01" in enc
    assert "loot_r01" in enc

def test_run_import_monsters_have_foundry_stats(tmp_path):
    if not KOBOLD_ZIP.exists():
        pytest.skip("kobold-cauldron.zip not present")
    run_import(str(KOBOLD_ZIP), campaign_dir=tmp_path, force=True)
    enc = json.loads((tmp_path / "encounters.json").read_text())
    all_monsters = [m for key in enc if key.startswith("enc_") for m in enc[key]]
    assert all("foundry_stats" in m for m in all_monsters if m)

def test_run_import_clobber_prompt(tmp_path, monkeypatch):
    """Without --force and with existing data, prompt fires."""
    (tmp_path / "dungeon.json").write_text('[{"id":"r01"}]')
    monkeypatch.setattr("builtins.input", lambda _: "n")
    with pytest.raises(SystemExit):
        run_import(str(KOBOLD_ZIP) if KOBOLD_ZIP.exists() else "/nonexistent",
                   campaign_dir=tmp_path, force=False)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_import_foundry.py -v -k "run_import"
```

Expected: `ImportError` — `run_import` not yet defined

- [ ] **Step 3: Implement main entry point and output writer**

Replace the `main()` stub in `scripts/import_foundry.py`:

```python
# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------

def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def run_import(module_path: str, campaign_dir: Path = None, force: bool = False) -> None:
    """Run the full import pipeline and write campaign/ files."""
    if campaign_dir is None:
        campaign_dir = Path(__file__).parent.parent / 'campaign'

    # Clobber check
    existing = campaign_dir / 'dungeon.json'
    if existing.exists() and existing.stat().st_size > 2 and not force:
        answer = input("Campaign data already exists in campaign/. Overwrite? [y/N]: ")
        if answer.strip().lower() != 'y':
            raise SystemExit("Import cancelled.")

    # Phase 1: Load
    data = load_module(module_path)
    actors, journals, items, scenes, world = (
        data['actors'], data['journals'], data['items'],
        data['scenes'], data['world']
    )

    # Phase 2: Classify actors
    monsters_by_id, npcs_by_id = classify_actors(actors)

    # Phase 3: Build rooms + config
    rooms = build_rooms(scenes, journals, monsters_by_id)
    config = build_config(world, room_count=len(rooms))

    # Phase 4: Build encounters
    all_actors = {**monsters_by_id, **npcs_by_id}
    encounters = build_encounters(scenes, all_actors, rooms)

    # Phase 5: Classify journals
    linked_ids = {scene.get('journal') for scene in scenes if scene.get('journal')}
    quests, foreshadowing, lore = classify_journals(journals, linked_ids)

    # Phase 6: Extract NPCs and items
    npcs = build_npcs(npcs_by_id, scenes, rooms)
    named_items = build_named_items(items)

    # Phase 7: Write outputs
    campaign_dir.mkdir(parents=True, exist_ok=True)
    _write_json(campaign_dir / 'config.json', config)
    _write_json(campaign_dir / 'dungeon.json', rooms)
    _write_json(campaign_dir / 'encounters.json', encounters)
    _write_json(campaign_dir / 'npcs.json', npcs)
    _write_json(campaign_dir / 'named_items.json', named_items)
    _write_json(campaign_dir / 'quests.json', quests)
    _write_json(campaign_dir / 'foreshadowing.json', foreshadowing)
    if lore:
        _write_json(campaign_dir / 'lore.json', lore)

    # Summary
    custom = [m['monster'] for enc_list in encounters.values()
              if isinstance(enc_list, list)
              for m in enc_list if m.get('foundry_stats')]
    print(f"\nImported \"{world.get('title', module_path)}\"")
    print(f"  {len(rooms)} rooms, {len(actors)} actors "
          f"({len(monsters_by_id)} monsters / {len(npcs_by_id)} NPCs), "
          f"{len(items)} items")
    print(f"  {len(quests)} quests, {len(foreshadowing)} foreshadowing seeds, "
          f"{len(lore)} lore entries")
    if custom:
        print(f"  Monsters with foundry_stats: {', '.join(sorted(set(custom)))}")
    print("  ⚠  connections defaulted to linear chain — review campaign/dungeon.json")
    if config['party_level'] == 3:
        print("  ⚠  party_level defaulted to 3 — no level data found in module")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Import a Foundry VTT NeDB module into campaign/ files."
    )
    parser.add_argument('path', help='Path to module .zip or extracted directory')
    parser.add_argument('--force', action='store_true',
                        help='Overwrite existing campaign data without prompting')
    args = parser.parse_args()
    run_import(args.path, force=args.force)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_import_foundry.py -v
```

Expected: all tests PASS (integration tests run if kobold-cauldron.zip exists; skip otherwise)

- [ ] **Step 5: Smoke-test against the real module**

```bash
python scripts/import_foundry.py tmp/kobold-cauldron.zip --force
```

Expected output:
```
Imported "Clash at the Kobold Cauldron"
  5 rooms, 21 actors (N monsters / M NPCs), 6 items
  ...
```

Verify campaign/ files were written and are valid JSON:
```bash
python -c "import json,glob; [json.load(open(f)) for f in glob.glob('campaign/*.json')]; print('All valid')"
```

- [ ] **Step 6: Commit**

```bash
git add scripts/import_foundry.py tests/test_import_foundry.py
git commit -m "feat(importer): add main entry point, output writer, integration test"
```

---

### Task 7: World-Engine Custom Monster Fallback

**Files:**
- Modify: `.claude/agents/world-engine.md` — add custom monster fallback to GENERATE procedure

**Interfaces:**
- Consumes: `campaign/encounters.json` entries that may have `foundry_stats`
- Produces: `state/secret/monsters.json` entries with correct stats even when oracle returns nothing

This task requires no test (the world-engine is an AI agent, not testable via pytest). Verification is done by running a session with the imported campaign and confirming combat resolves correctly.

- [ ] **Step 1: Locate the insertion point in world-engine.md**

Open `.claude/agents/world-engine.md` and find the `## Procedure` section. It currently reads:

```
1. Read the request and any state you need for true numbers.
2. GENERATE: query `oracle.py` for content, run `dice.py` for every random choice ...
```

- [ ] **Step 2: Add the custom monster fallback instruction**

In `.claude/agents/world-engine.md`, find this block (around line 64):

```markdown
## Procedure
1. Read the request and any state you need for true numbers.
2. GENERATE: query `oracle.py` for content, run `dice.py` for every random choice (stat arrays via `4d6kh3`, HP, loot/monster weighting, trap DCs), write `map.txt`, `encounter.json`, and `secret/monsters.json`. RESOLVE: for each `mechanic_request`, invoke `dice.py` with a clear `--reason`, compare against the relevant AC/DC, compute deltas, and append hidden-HP changes to `secret/monsters.json`.
```

Insert the following block **after** step 2:

```markdown
**Custom monster fallback (Foundry imports):** If a `campaign/encounters.json` monster entry has a `foundry_stats` field, first attempt an oracle lookup by the `monster` name as normal. If the oracle returns no results (empty list), use `foundry_stats` directly to populate `state/secret/monsters.json` for that creature — set `hp` from `foundry_stats` (roll max HP via `dice.py` if a die expression, otherwise use the value directly), `ac` from the encounter entry's `ac` field, `speed` and `abilities` from `foundry_stats`. For attacks, use `foundry_stats.attacks` entries directly. Do not error or skip a monster simply because the oracle finds no match; the fallback is the correct path for homebrew content.
```

- [ ] **Step 3: Verify the edit looks correct**

```bash
grep -n "foundry_stats\|Custom monster" /Users/curtis/dev/claude_projects/rpg/.claude/agents/world-engine.md
```

Expected: two matches showing the new instruction is present

- [ ] **Step 4: Run a quick session with the imported campaign to confirm combat resolves**

Start a session (per `run.md`) and step through one combat encounter. Confirm the world-engine produces a populated `state/secret/monsters.json` without erroring on custom Foundry monsters.

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/world-engine.md
git commit -m "feat(world-engine): add foundry_stats fallback for custom monsters"
```
