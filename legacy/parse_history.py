"""Parse data/history-raw.json into per-kid stage sign-off CSVs."""
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "data" / "history-raw.json"
OUT = HERE / "data" / "stage_signoffs.csv"

BADGE_KEY_LABELS = {
    "runner": "Runner",
    "tracker": "Tracker",
    "howler": "Howler",
    "seeoneeaward": "Seeonee Award",
    "campingskills1": "Camping Skills 1",
    "campingskills2": "Camping Skills 2",
    "campingskills3": "Camping Skills 3",
    "aquaticskills1": "Aquatic Skills 1",
    "aquaticskills2": "Aquatic Skills 2",
    "aquaticskills3": "Aquatic Skills 3",
    "paddlingskills1": "Paddling Skills 1",
    "paddlingskills2": "Paddling Skills 2",
    "paddlingskills3": "Paddling Skills 3",
    "winterskills1": "Winter Skills 1",
    "winterskills2": "Winter Skills 2",
    "winterskills3": "Winter Skills 3",
    "emergencyskills1": "Emergency Skills 1",
    "emergencyskills2": "Emergency Skills 2",
    "emergencyskills3": "Emergency Skills 3",
    "verticalskills1": "Vertical Skills 1",
    "verticalskills2": "Vertical Skills 2",
    "verticalskills3": "Vertical Skills 3",
    "trailskills1": "Trail Skills 1",
    "trailskills2": "Trail Skills 2",
    "trailskills3": "Trail Skills 3",
    "scoutcraftskills1": "Scoutcraft Skills 1",
    "scoutcraftskills2": "Scoutcraft Skills 2",
    "scoutcraftskills3": "Scoutcraft Skills 3",
    "sailingskills1": "Sailing Skills 1",
    "sailingskills2": "Sailing Skills 2",
    "sailingskills3": "Sailing Skills 3",
}


AWARD_RE = re.compile(
    r"^(?P<badge>.+?)\s+(?P<member>[A-Z][\w'\- ]+?)\s+"
    r"(?:(?P<scope>Colony|Troop|Pack):\s*)?"
    r"(?P<verb>Awarded|Unawarded)\s+by\s+(?P<scouter>.+)$"
)


ROSTER_PATH = HERE / "data" / "roster.json"


def _load_roster() -> list[str]:
    return json.loads(ROSTER_PATH.read_text())


def parse_text(text: str, roster: list[str]):
    """Extract badge label, member, verb, scope, and scouter from an entry.

    Format is: "<Badge Name> <Cub Name> [<Scope>: ]<Verb> by <Scouter>".
    The badge name boundary is found by locating a known roster member name
    inside the string — that's the cub being awarded.
    """
    if not text:
        return None
    tail = re.search(
        r"\s+(?:(?P<scope>Colony|Troop|Pack):\s*)?"
        r"(?P<verb>Awarded|Unawarded)\s+by\s+(?P<scouter>.+)$",
        text,
    )
    if not tail:
        return None
    head = text[: tail.start()].strip()
    # head looks like "<Badge Name> <Cub Name>"
    member = None
    badge = None
    # Sort roster by length desc so longer matches win (e.g. a three-part name
    # before a first name alone).
    for name in sorted(roster, key=len, reverse=True):
        if head.endswith(name):
            member = name
            badge = head[: len(head) - len(name)].strip()
            break
    if member is None:
        return None
    return {
        "badge": badge,
        "member": member,
        "verb": tail.group("verb"),
        "scope": tail.group("scope") or "",
        "scouter": tail.group("scouter").strip(),
    }


def main():
    raw = json.loads(RAW.read_text())
    roster = _load_roster()
    rows = []
    for entry in raw["entries"]:
        badge_key = entry.get("badgeKey")
        parsed = parse_text(entry["text"], roster)
        if not parsed:
            continue
        rows.append({
            "date": entry["date"],
            "member": parsed["member"],
            "badge_key": badge_key,
            "badge": parsed["badge"] or BADGE_KEY_LABELS.get(badge_key, badge_key or ""),
            "verb": parsed["verb"],
            "scope": parsed["scope"],
            "scouter": parsed["scouter"],
            "member_id": entry["memberId"],
        })

    # Resolve "unawarded" by removing pairs (we only want net "awarded" status)
    # Group by (member, badge_key) and take latest entry; keep if its verb == Awarded
    by_kb = defaultdict(list)
    for r in rows:
        by_kb[(r["member"], r["badge_key"])].append(r)

    final = []
    for key, lst in by_kb.items():
        lst.sort(key=lambda x: x["date"])
        last = lst[-1]
        if last["verb"] == "Awarded":
            final.append(last)

    final.sort(key=lambda r: (r["member"], r["date"]))

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["member", "badge", "badge_key", "date", "scouter", "scope"])
        w.writeheader()
        for r in final:
            w.writerow({k: r[k] for k in w.fieldnames})

    # Summary per kid
    per_kid = defaultdict(int)
    for r in final:
        per_kid[r["member"]] += 1

    print(f"Wrote {OUT} ({len(final)} stage awards)")
    print()
    print("Per-kid stage award counts:")
    for name in sorted(per_kid):
        print(f"  {per_kid[name]:3d}  {name}")


if __name__ == "__main__":
    main()
