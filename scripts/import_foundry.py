"""Import a Foundry VTT NeDB module into campaign/ files."""
import argparse
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------

def strip_html(html: Optional[str]) -> str:
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


def _parse_db(text: str):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _index(records):
    return {r['_id']: r for r in records}


def _load_from_dir(p: Path) -> dict:
    # data/ may be nested inside a subdirectory
    candidates = [d for d in p.rglob('data') if (d / 'actors.db').exists()]
    if not candidates:
        raise ValueError(f"No data/actors.db found under {p}")
    data_dir = candidates[0]

    world_files = list(p.rglob('world.json'))
    world = json.loads(world_files[0].read_text()) if world_files else {}

    def read(name):
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
