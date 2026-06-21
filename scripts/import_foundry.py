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
        # First sentence (including the terminating punctuation)
        match = re.match(r'^([^.!?]*[.!?])', bio_text)
        goal = match.group(1).strip() if match else (bio_text.split()[0] if bio_text else '')

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


# ---------------------------------------------------------------------------
# Placeholder main (expanded in Task 6)
# ---------------------------------------------------------------------------

def main():
    pass


if __name__ == '__main__':
    main()
