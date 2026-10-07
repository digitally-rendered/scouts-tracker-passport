"""Parse data/cub-stats.json into per-kid stats CSV."""
import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "data" / "cub-stats.json"
OUT = HERE / "data" / "cub_stats.csv"

# Stable column order
EVENT_LABELS = [
    "Camps", "Service", "Env Projects", "Hikes", "Hikes (by km)",
    "Linking Events", "Paddle Expeditions", "Planning", "Howlers' Councils",
    "Seasonal Assessments", "Parent Participation", "Other",
]

ROW_RE = re.compile(r"^(?P<label>.+?)\s+×\s+(?P<count>[\d.]+)(?P<unit>[a-zA-Z]*)$")


def parse_events(text: str) -> dict[str, str]:
    out = {}
    if not text:
        return out
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        out[m.group("label")] = f"{m.group('count')}{m.group('unit')}"
    return out


def main():
    raw = json.loads(RAW.read_text())
    rows = []
    for k in raw:
        seeonee_pct = ""
        seeonee_text = (k.get("seeonee") or "").replace("Seeonee Award", "").strip()
        m = re.search(r"(\d+)%", seeonee_text)
        if m:
            seeonee_pct = m.group(1)
        oas_stages = ""
        oas_text = (k.get("oas") or "").replace("OAS Stages", "").strip()
        m = re.search(r"(\d+)", oas_text)
        if m:
            oas_stages = m.group(1)
        events = parse_events(k.get("events") or "")
        row = {
            "name": k["name"],
            "id": k["id"],
            "seeonee_pct": seeonee_pct,
            "oas_stages": oas_stages,
        }
        for label in EVENT_LABELS:
            row[label] = events.get(label, "")
        rows.append(row)

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["name", "id", "seeonee_pct", "oas_stages", *EVENT_LABELS]
        )
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {OUT} ({len(rows)} kids)")
    print()
    # Quick summary table
    headers = ["name", "Seeonee%", "OAS", "Camps", "Service", "Hikes", "PaddleExp", "Howlers"]
    print("  ".join(f"{h:22s}" if h == "name" else f"{h:>10s}" for h in headers))
    howlers_key = "Howlers' Councils"
    for r in rows:
        print(
            f"{r['name']:22s}  "
            f"{r['seeonee_pct']:>10s}  "
            f"{r['oas_stages']:>10s}  "
            f"{r['Camps']:>10s}  "
            f"{r['Service']:>10s}  "
            f"{r['Hikes']:>10s}  "
            f"{r['Paddle Expeditions']:>10s}  "
            f"{r[howlers_key]:>10s}"
        )


if __name__ == "__main__":
    main()
