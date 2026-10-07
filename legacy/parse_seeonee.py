"""Parse data/seeonee-table-cells.json into a per-kid Seeonee CSV."""
import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "data" / "seeonee-table-cells.json"
OUT = HERE / "data" / "seeonee_status.csv"

REQS = ["1", "2", "3", "4a", "4b", "4c", "5", "6"]


def main():
    rows = json.loads(RAW.read_text())
    out_rows = []
    for r in rows:
        if len(r) < 3:
            continue
        # Skip header / divider / spacer rows
        first_cls = r[0].get("cls", "")
        if "divider" in first_cls or "caption" in first_cls:
            continue
        # Need a name in column 0 with class containing 'sticky-col'
        if "sticky-col" not in first_cls:
            continue
        name = r[0]["text"].strip()
        if not name or name == "⤨":
            continue
        # Skip Scouters (status cells are all '–')
        cells = r[2:]
        if all(c["text"].strip() in ("–", "") for c in cells):
            # adult/scouter row, skip
            continue
        pct = r[1]["text"].strip().rstrip("%")
        status = {}
        for i, req in enumerate(REQS):
            cell = r[2 + i] if 2 + i < len(r) else {"text": ""}
            t = cell["text"].strip()
            if t in ("✓",):
                status[req] = "✓"
            elif t.startswith("="):
                # community service hours, e.g. "=9h"
                status[req] = t.lstrip("=")
            elif t == "■":
                status[req] = "started"
            else:
                status[req] = ""
        # Special case: a member could have 'Awarded' status (Abigail)
        joined = " ".join(c["text"] for c in cells)
        awarded = "Awarded" in joined

        out_rows.append({
            "name": name,
            "percent": pct,
            "awarded": "yes" if awarded else "",
            **{f"req_{q}": status[q] for q in REQS},
        })

    OUT.parent.mkdir(exist_ok=True)
    fields = ["name", "percent", "awarded"] + [f"req_{q}" for q in REQS]
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    print(f"Wrote {OUT} ({len(out_rows)} kids)")
    print()
    print(f"{'name':22s}  {'%':>4s}  awarded   1   2   3      4a  4b  4c   5   6")
    for r in out_rows:
        print(
            f"{r['name']:22s}  "
            f"{r['percent']:>3s}%  "
            f"{r['awarded']:7s}  "
            f"{r['req_1']:>3s} {r['req_2']:>3s} {r['req_3']:>5s}  "
            f"{r['req_4a']:>3s} {r['req_4b']:>3s} {r['req_4c']:>3s} "
            f"{r['req_5']:>3s} {r['req_6']:>3s}"
        )


if __name__ == "__main__":
    main()
