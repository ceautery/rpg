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
