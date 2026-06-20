#!/usr/bin/env python3
"""
Authoritative RNG for the RPG simulator.
All randomness in the simulation must flow through this script.
Appends every roll to state/rng_log.jsonl.

Usage:
  python scripts/dice.py "2d6+3" --reason "goblin damage" --actor world-engine
  python scripts/dice.py "1d20+5" --adv --reason "attack with advantage" --actor world-engine
  python scripts/dice.py "4d6kh3" --reason "stat gen STR" --actor world-engine
  python scripts/dice.py "1d20+4" --ac 15 --reason "goblin shortbow vs Lyra" --actor world-engine
  python scripts/dice.py "1d20+2" --dc 13 --reason "DEX save" --actor world-engine
"""

import argparse
import datetime
import json
import os
import random
import re
import sys
from pathlib import Path

RNG_LOG = Path(__file__).parent.parent / "state" / "rng_log.jsonl"


def seeded_rng() -> random.Random:
    seed = os.environ.get("RPG_SEED")
    if seed is not None:
        return random.Random(int(seed))
    return random.Random()


def roll_one(sides: int, rng: random.Random) -> int:
    return rng.randint(1, sides)


def parse_formula(formula: str) -> tuple[int, int, int, str | None, int | None]:
    """
    Returns (num_dice, sides, modifier, keep_mode, keep_count).
    keep_mode is 'kh' or 'kl' or None.
    modifier can be negative.
    """
    formula = formula.strip().replace(" ", "")
    # Match: NdM[kh|klK][+/-mod]
    pattern = re.compile(
        r"^(\d+)d(\d+)"
        r"(?:(kh|kl)(\d+))?"
        r"([+-]\d+)?$",
        re.IGNORECASE,
    )
    m = pattern.match(formula)
    if not m:
        raise ValueError(f"Unrecognised dice formula: {formula!r}")
    num_dice = int(m.group(1))
    sides = int(m.group(2))
    keep_mode = m.group(3).lower() if m.group(3) else None
    keep_count = int(m.group(4)) if m.group(4) else None
    modifier = int(m.group(5)) if m.group(5) else 0
    return num_dice, sides, modifier, keep_mode, keep_count


def resolve(
    formula: str,
    adv: bool = False,
    dis: bool = False,
    rng: random.Random | None = None,
) -> dict:
    """Roll the formula and return a result dict (without vs/success/reason/ts)."""
    if rng is None:
        rng = seeded_rng()

    num_dice, sides, modifier, keep_mode, keep_count = parse_formula(formula)

    if adv or dis:
        # Roll twice and keep high (adv) or low (dis). Only meaningful for single dice.
        roll_a = [roll_one(sides, rng) for _ in range(num_dice)]
        roll_b = [roll_one(sides, rng) for _ in range(num_dice)]
        sum_a, sum_b = sum(roll_a), sum(roll_b)
        if adv:
            chosen, discarded = (roll_a, roll_b) if sum_a >= sum_b else (roll_b, roll_a)
        else:
            chosen, discarded = (roll_a, roll_b) if sum_a <= sum_b else (roll_b, roll_a)
        raw = chosen
        all_rolls = {"kept": chosen, "discarded": discarded}
        total = sum(chosen) + modifier
    elif keep_mode:
        raw = [roll_one(sides, rng) for _ in range(num_dice)]
        sorted_rolls = sorted(raw, reverse=(keep_mode == "kh"))
        kept = sorted_rolls[:keep_count]
        dropped = sorted_rolls[keep_count:]
        all_rolls = {"kept": kept, "dropped": dropped}
        total = sum(kept) + modifier
    else:
        raw = [roll_one(sides, rng) for _ in range(num_dice)]
        all_rolls = raw
        total = sum(raw) + modifier

    return {
        "formula": formula,
        "rolls": all_rolls,
        "modifier": modifier,
        "total": total,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Authoritative dice roller")
    parser.add_argument("formula", help="Dice formula, e.g. '2d6+3' or '4d6kh3'")
    parser.add_argument("--reason", required=True, help="Why this roll is happening")
    parser.add_argument("--actor", default="world-engine", help="Who is rolling")
    parser.add_argument("--adv", action="store_true", help="Roll with advantage")
    parser.add_argument("--dis", action="store_true", help="Roll with disadvantage")
    parser.add_argument("--ac", type=int, default=None, help="Compare total against AC")
    parser.add_argument("--dc", type=int, default=None, help="Compare total against DC")
    args = parser.parse_args()

    if args.adv and args.dis:
        print("Error: --adv and --dis are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    rng = seeded_rng()
    result = resolve(args.formula, adv=args.adv, dis=args.dis, rng=rng)

    vs = None
    success = None
    if args.ac is not None:
        vs = {"ac": args.ac}
        success = result["total"] >= args.ac
    elif args.dc is not None:
        vs = {"dc": args.dc}
        success = result["total"] >= args.dc

    record = {
        "formula": result["formula"],
        "rolls": result["rolls"],
        "modifier": result["modifier"],
        "total": result["total"],
        "vs": vs,
        "success": success,
        "reason": args.reason,
        "actor": args.actor,
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    # Append to audit log (create parent dirs if needed).
    RNG_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RNG_LOG.open("a") as f:
        f.write(json.dumps(record) + "\n")

    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
