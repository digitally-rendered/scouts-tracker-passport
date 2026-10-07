"""Turn data/<date>/raw/scoutstracker.json into the files the passport filler uses.

Writes, next to raw/:
    roster.json            active Cub names
    tracking.csv           requirement grid (same layout as the old hand-pasted
                           Google Sheet: one column per Cub, "▼ Section N" rows,
                           "#N.x" requirement rows, ✓ or a tally count)
    stage_signoffs.csv     every badge awarded: member, badge, date, scouter
    cub_stats.csv          camp nights, service hours, etc. (all years)
    seeonee_status.csv     Seeonee Award requirements per Cub
    oas_requirements.json  full requirement text per OAS skill and stage (1-9)

Usage:
    python build_data.py                 # latest data/<date>/
    python build_data.py data/2026-10-07
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from paths import DATA_DIR, SCOUTER_NAMES  # noqa: E402

SKILLS = {
    "aquatic": "Aquatic Skills", "camping": "Camping Skills", "emergency": "Emergency Skills",
    "paddling": "Paddling Skills", "sailing": "Sailing Skills", "scoutcraft": "Scoutcraft Skills",
    "trail": "Trail Skills", "vertical": "Vertical Skills", "winter": "Winter Skills",
}
AWARDS = {"runner": "Runner", "tracker": "Tracker", "howler": "Howler",
          "seeoneeaward": "Seeonee Award"}
SKILL_RE = re.compile(r"^(?P<skill>[a-z]+)skills(?P<stage>\d)$")

# ScoutsTracker event-label keys -> cub_stats.csv columns (unit suffix).
ROLLUP_COLUMNS = [
    ("camp", "Camps", "n"), ("community", "Service", "h"), ("environment", "Env Projects", ""),
    ("hike", "Hikes", ""), ("hikekm", "Hikes (by km)", "km"), ("link", "Linking Events", ""),
    ("paddleexpedition", "Paddle Expeditions", ""), ("planning", "Planning", ""),
    ("sixers", "Howlers' Councils", ""), ("seasonal", "Seasonal Assessments", ""),
    ("parent", "Parent Participation", ""), ("other", "Other", ""),
]
SEEONEE_REQS = ["1", "2", "3", "4a", "4b", "4c", "5", "6"]
UNKNOWN_SCOUTERS = {"", "unknown", "cub pack"}


def badge_label(badge_id: str) -> str:
    m = SKILL_RE.match(badge_id)
    if m and m.group("skill") in SKILLS:
        return f"{SKILLS[m.group('skill')]} {m.group('stage')}"
    return AWARDS.get(badge_id, badge_id)


def clean_text(s: str) -> str:
    s = re.sub(r"<detail>.*?</detail>", "", s or "", flags=re.S)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s).replace("**", "")
    s = s.replace("()", "")
    return re.sub(r"\s+", " ", s).strip()


def clean_scouter(name: str) -> str:
    name = re.sub(r"\s*\((inactive|GC)\)\s*$", "", (name or "").strip(), flags=re.I)
    return "Unknown" if name.lower() in UNKNOWN_SCOUTERS else name


def req_sort_key(req: str):
    m = re.match(r"^([A-Za-z]*)(\d+)(.*)$", req)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (req, 0, "")


def to_date(ms) -> str:
    return datetime.fromtimestamp(ms / 1000).date().isoformat() if ms and ms > 0 else ""


def is_done(cub: dict, rid: str, reqs: dict, depth: int = 0) -> bool:
    """Completed directly, or via its auto-completion rule (tally / sub-reqs)."""
    if rid in cub["completed"]:
        return True
    rule = (reqs.get(rid) or {}).get("autocompletion", "")
    if depth > 3 or not rule:
        return False
    m = re.fullmatch(r"tally:(.+)-(\d+)", rule)
    if m:
        return (cub["tallies"].get(m.group(1)) or 0) >= int(m.group(2))
    parts = re.findall(r"requirement:([\w.]+)", rule)
    if parts and "|" not in rule:
        return all(is_done(cub, p, reqs, depth + 1) for p in parts)
    if parts:
        return any(is_done(cub, p, reqs, depth + 1) for p in parts)
    return False


def cell_value(cub: dict, rid: str, reqs: dict) -> str:
    if is_done(cub, rid, reqs):
        return "✓"
    count = cub["tallies"].get(rid)
    if not count:
        # Parent of sub-requirements (e.g. Trail 3.12 -> 3.12a/b): the passport
        # often prints one box for it, so show the best child tally there.
        rule = (reqs.get(rid) or {}).get("subreqlogic", "")
        counts = [cub["tallies"].get(c) or 0 for c in re.findall(r"requirement:([\w.]+)", rule)]
        count = max(counts, default=0)
    return str(count) if count else ""


def build(data_dir: Path) -> None:
    raw = json.loads((data_dir / "raw" / "scoutstracker.json").read_text(encoding="utf-8"))
    cubs = sorted(raw["cubs"], key=lambda c: c["name"])
    reqs = raw["requirements"]
    scouters = {k: clean_scouter(v) for k, v in raw["scouters"].items()}
    # Optional manual names for logins ScoutsTracker can't resolve (e.g. Scouters
    # from another section): scouter_names.json = {"144726": "Jane Smith"}
    overrides = SCOUTER_NAMES
    if overrides.exists():
        scouters.update(json.loads(overrides.read_text(encoding="utf-8")))
    unresolved = sorted(k for k, v in scouters.items() if v == "Unknown" and k != "-1")
    if unresolved:
        print(f"Scouter IDs with no name (add to scouter_names.json to fill them in): "
              f"{', '.join(unresolved)}")

    by_badge: dict[str, list[tuple[str, dict]]] = {}
    for rid, r in reqs.items():
        by_badge.setdefault(r["badgeid"], []).append((rid, r))
    for lst in by_badge.values():
        lst.sort(key=lambda x: req_sort_key(x[1]["requirement"]))

    names = [c["name"] for c in cubs]
    (data_dir / "roster.json").write_text(json.dumps(names, indent=2), encoding="utf-8")

    # --- tracking.csv (old Google-Sheet layout) + oas_requirements.json ---
    badge_order = list(AWARDS) + [f"{s}skills{n}" for s in SKILLS for n in range(1, 10)]
    oas_text: dict[str, dict[str, list[str]]] = {}
    with (data_dir / "tracking.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["⤨", ""] + names)
        for bid in badge_order:
            rows = by_badge.get(bid)
            if not rows:
                continue
            m = SKILL_RE.match(bid)
            stage = m.group("stage") if m else ""
            w.writerow([f"▼ {badge_label(bid)}"] + [""] * (len(names) + 1))
            for rid, r in rows:
                req = r["requirement"]
                if bid == "seeoneeaward":
                    req = re.sub(r"^[A-D]", "", req)
                    if req not in SEEONEE_REQS:
                        continue  # group headers (A, B, D, D0, D4)
                    req_id = req
                else:
                    req_id = f"{stage}.{req}" if stage else req
                text = clean_text(r["description"])
                w.writerow([f"#{req_id}", text] + [cell_value(c, rid, reqs) for c in cubs])
                if m:
                    oas_text.setdefault(SKILLS[m.group("skill")], {}).setdefault(stage, []).append(text)
    (data_dir / "oas_requirements.json").write_text(
        json.dumps(oas_text, indent=1, ensure_ascii=False), encoding="utf-8")

    # --- stage_signoffs.csv ---
    with (data_dir / "stage_signoffs.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["member", "badge", "badge_key", "date", "scouter", "scope"])
        w.writeheader()
        for c in cubs:
            for bid, v in sorted(c["awarded"].items(), key=lambda kv: kv[1]["when"]):
                w.writerow({"member": c["name"], "badge": badge_label(bid), "badge_key": bid,
                            "date": to_date(v["when"]),
                            "scouter": scouters.get(str(v["by"]), "Unknown"), "scope": ""})

    # --- cub_stats.csv ---
    extra_keys = sorted({k for c in cubs for k in c["rollups"]} - {k for k, _, _ in ROLLUP_COLUMNS})
    with (data_dir / "cub_stats.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "id", "seeonee_pct", "oas_stages"]
                   + [col for _, col, _ in ROLLUP_COLUMNS] + extra_keys)
        for c in cubs:
            oas = sum(1 for b in c["awarded"] if SKILL_RE.match(b))
            ro = c["rollups"]
            w.writerow([c["name"], c["memberid"], seeonee_percent(c, reqs), oas]
                       + [f"{ro[k]:g}{unit}" if ro.get(k) else "" for k, _, unit in ROLLUP_COLUMNS]
                       + [f"{ro[k]:g}" if ro.get(k) else "" for k in extra_keys])

    # --- seeonee_status.csv ---
    with (data_dir / "seeonee_status.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "percent", "awarded"] + [f"req_{q}" for q in SEEONEE_REQS])
        for c in cubs:
            vals = []
            for q in SEEONEE_REQS:
                rid = seeonee_rid(q, reqs)
                v = cell_value(c, rid, reqs) if rid else ""
                vals.append(f"{v}h" if q == "3" and v.isdigit() else v)
            w.writerow([c["name"], seeonee_percent(c, reqs),
                        "yes" if "seeoneeaward" in c["awarded"] else ""] + vals)

    print(f"Built {data_dir}: {len(names)} Cubs, "
          f"{sum(len(c['awarded']) for c in cubs)} awards, "
          f"OAS text for {sum(len(v) for v in oas_text.values())} skill stages")


def seeonee_rid(q: str, reqs: dict) -> str | None:
    for rid, r in reqs.items():
        if r["badgeid"] == "seeoneeaward" and re.sub(r"^[A-D]", "", r["requirement"]) == q:
            return rid
    return None


def seeonee_percent(cub: dict, reqs: dict) -> str:
    rids = [seeonee_rid(q, reqs) for q in SEEONEE_REQS]
    rids = [r for r in rids if r]
    if "seeoneeaward" in cub["awarded"]:
        return "100"
    done = sum(1 for r in rids if is_done(cub, r, reqs))
    return str(round(100 * done / len(rids))) if rids else ""


def latest_data_dir() -> Path:
    dirs = sorted(p for p in DATA_DIR.glob("20*-*-*") if (p / "raw").is_dir())
    if not dirs:
        raise SystemExit("No fetched data found. Run: python scrape/fetch.py")
    return dirs[-1]


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else latest_data_dir())
