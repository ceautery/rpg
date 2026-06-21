import json
import zipfile
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from import_foundry import load_module, strip_html, classify_actors, infer_room_type, build_rooms, build_config


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


# --- Shared fixtures for classify_actors, infer_room_type, build_rooms, build_config ---

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


# --- build_encounters ---

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


# --- classify_journals ---

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
