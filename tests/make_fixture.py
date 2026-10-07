"""Regenerate tests/fixtures/scoutstracker.json.

Keeps ONLY the public OAS / Cub-award requirement definitions from a real
fetch (no members, no records) and adds three invented Cubs whose records are
designed to exercise specific cases. Run after ScoutsTracker changes its
requirement data:

    uv run python tests/make_fixture.py ~/ScoutsPassportData/data/<date>/raw/scoutstracker.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).parent / "fixtures" / "scoutstracker.json"
KEEP = re.compile(r"^((aquatic|camping|emergency|paddling|sailing|scoutcraft|trail|"
                  r"vertical|winter)skills[1-5]|runner|tracker|howler|seeoneeaward)$")
WHEN = 1747224000000  # 2025-05-14 12:00 UTC (same calendar date in any Canadian timezone)


def reqs_of(requirements: dict, badge: str) -> list[str]:
    return [k for k, v in requirements.items() if v["badgeid"] == badge]


def done(ids, by=9001):
    return {i: {"when": WHEN, "by": by} for i in ids}


def main(src: Path) -> None:
    raw = json.loads(src.read_text(encoding="utf-8"))
    requirements = {k: v for k, v in raw["requirements"].items() if KEEP.match(v["badgeid"])}
    R = lambda b: reqs_of(requirements, b)  # noqa: E731

    camping2 = sorted(R("campingskills2"))
    cubs = [
        {   # Two camping stages signed by a named Scouter, one requirement
            # missing (-> auto-tick), a stage 4 tick, tallies, runner by "Cub Pack".
            "memberid": 1001, "personid": 2001, "name": "Alex Tester",
            "completed": {**done(R("campingskills1")), **done(camping2[:-1]),
                          **done(["campingskills4.1"])},
            "awarded": {"campingskills1": {"when": WHEN, "by": 9001},
                        "campingskills2": {"when": WHEN, "by": 9001},
                        "runner": {"when": WHEN, "by": 9002}},
            "tallies": {"campingskills4.12": 9, "trailskills3.12a": 5},
            "rollups": {"camp": 9, "community": 6, "hikekm": 4},
        },
        {   # Aquatic 1-4 awarded by an unknown Scouter (stage 4 sign-off),
            # Camping 1 fully ticked but never awarded, a stage 5 tick.
            "memberid": 1002, "personid": 2002, "name": "Blair Example",
            "completed": {**done(R("aquaticskills4"), 9003), **done(R("campingskills1")),
                          **done(["aquaticskills5.1"], 9003)},
            "awarded": {f"aquaticskills{n}": {"when": WHEN, "by": 9003} for n in range(1, 5)},
            "tallies": {},
            "rollups": {"camp": 3},
        },
        {   # Brand new Cub: nothing recorded yet.
            "memberid": 1003, "personid": 2003, "name": "Casey Sample",
            "completed": {}, "awarded": {}, "tallies": {}, "rollups": {},
        },
    ]
    fixture = {
        "fetched_at": "2026-01-01T12:00:00",
        "requirements": requirements,
        "scouters": {"9001": "Test Scouter (inactive)", "9002": "Cub Pack",
                     "9003": "Unknown", "-1": "Unknown"},
        "cubs": cubs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixture, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT} ({len(requirements)} requirements, {len(cubs)} invented Cubs)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
