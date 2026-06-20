#!/usr/bin/env python3
"""
Thin wrapper over the Open5e v2 API, pinned to one ruleset source.
All responses are cached under cache/ keyed by the full query URL.

Usage:
  python scripts/oracle.py creatures --where name__icontains=goblin --fields name,armor_class,hit_points,actions
  python scripts/oracle.py spells --where name__icontains=fireball --fields name,level,damage
  python scripts/oracle.py equipment --where name__icontains=shortsword --fields name,cost,damage
  python scripts/oracle.py search --where text=goblin --fields name,document__key
  python scripts/oracle.py conditions --where name=Poisoned --fields name,description

Supported endpoints: creatures, spells, equipment, magicitems, classes, conditions, search
Default source: srd-2024 (CC-BY 4.0)
"""

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://api.open5e.com/v2"
CACHE_DIR = Path(__file__).parent.parent / "cache"
DEFAULT_SOURCE = "srd-2024"

# v2 API endpoints (note: v1 had "equipment"; v2 splits it into weapons/armor/items)
# Known API quirks:
#   - conditions: ignores document__key__in and name filters; always returns all 21 conditions
#   - weapons/armor: name__icontains filter is silently ignored; fetch all and filter client-side
#   - creatures/spells: full filter support including name__icontains, document__key__in
SUPPORTED_ENDPOINTS = {
    "creatures", "spells", "weapons", "armor", "items", "magicitems",
    "classes", "conditions", "backgrounds", "feats",
}

# Convenience aliases → canonical v2 endpoint names
ENDPOINT_ALIASES: dict[str, str] = {
    "equipment": "items",   # backward-compat alias
    "monsters": "creatures",
}


def cache_path(url: str) -> Path:
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{key}.json"


def fetch(url: str, force: bool = False) -> dict:
    path = cache_path(url)
    if not force and path.exists():
        with path.open() as f:
            return json.load(f)

    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "rpg-sim/0.1 (open5e-client; +https://open5e.com)",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} fetching {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Network error fetching {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(data, f, indent=2)
    return data


def build_url(endpoint: str, where: list[str], source: str, fields: str | None) -> str:
    params: dict[str, str] = {}

    # Pin the source document — non-negotiable.
    if endpoint != "search":
        params["document__key__in"] = source

    # Parse --where filters (key=value pairs).
    for clause in where:
        if "=" not in clause:
            print(f"Error: --where filter must be key=value, got: {clause!r}", file=sys.stderr)
            sys.exit(1)
        k, v = clause.split("=", 1)
        params[k.strip()] = v.strip()

    # Always request a reasonable page size.
    params.setdefault("limit", "20")

    query = urllib.parse.urlencode(params)

    # The Open5e API requires literal commas in `fields` — append it unencoded.
    if fields:
        query += "&fields=" + fields

    return f"{BASE_URL}/{endpoint}/?{query}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Open5e API wrapper (pinned to one source)")
    all_choices = sorted(SUPPORTED_ENDPOINTS | set(ENDPOINT_ALIASES.keys()))
    parser.add_argument("endpoint", choices=all_choices, help="API endpoint (use 'weapons', 'armor', or 'items' for gear)")
    parser.add_argument(
        "--where", action="append", default=[], metavar="KEY=VALUE",
        help="Filter parameter (repeatable), e.g. --where name__icontains=goblin",
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE, help=f"Source document key (default: {DEFAULT_SOURCE})")
    parser.add_argument("--fields", default=None, help="Comma-separated fields to return")
    parser.add_argument("--limit", type=int, default=None, help="Max results (default 20)")
    parser.add_argument("--force", action="store_true", help="Bypass cache and re-fetch")
    args = parser.parse_args()

    if args.limit:
        args.where.append(f"limit={args.limit}")

    endpoint = ENDPOINT_ALIASES.get(args.endpoint, args.endpoint)
    url = build_url(endpoint, args.where, args.source, args.fields)
    data = fetch(url, force=args.force)
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
