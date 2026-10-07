"""Audit filled passports: prove every award and tick in ScoutsTracker made it
onto the PDF, and flag anything a leader should look at.

Reads the fetched data folder (data/<date>/) and the passports + fill_log.json
written by `fill_passport.py --all` (out/<date>/). Writes audit.csv and
audit.html next to the passports. Exit code 1 if any ERROR was found.

Levels:
  ERROR  something is missing from a passport (must be fixed before printing)
  WARN   data looks inconsistent in ScoutsTracker (a leader should check)
  INFO   expected behaviour worth knowing (auto-ticks, blank Scouter names)

Usage:
    python audit_passports.py                       # newest data/ and out/ folders
    python audit_passports.py --data data/2026-10-07 --out out/2026-10-07
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pymupdf as fitz  # PyMuPDF

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from build_data import latest_data_dir  # noqa: E402
from paths import OUT_DIR  # noqa: E402
from fill_passport import SECTION_NAMES, parse_csv_for_kid  # noqa: E402

CHECK_COLOR = (0, 0.45, 0)
STALE_DAYS = 7


def load_signoffs(path: Path) -> dict[str, dict[tuple[str, int], dict]]:
    by_kid: dict[str, dict] = defaultdict(dict)
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = re.match(r"^(.+?)\s+(\d+)$", row["badge"].strip())
            if m and m.group(1) in SECTION_NAMES:
                by_kid[row["member"]][(m.group(1), int(m.group(2)))] = row
    return by_kid


def kid_buckets(tracking: Path, name: str) -> dict[tuple[str, int], tuple[int, int]]:
    """{(section, stage): (ticked, total)} from the tracking grid."""
    out: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])
    for r in parse_csv_for_kid(tracking, name):
        if r.section not in SECTION_NAMES or r.stage is None:
            continue
        out[(r.section, r.stage)][1] += 1
        if r.value.strip() == "✓":
            out[(r.section, r.stage)][0] += 1
    return {k: tuple(v) for k, v in out.items()}


def read_back(pdf: Path) -> tuple[int, int]:
    """Count green checkmarks (vector polylines) and green count numbers."""
    checks = counts = 0
    with fitz.open(pdf) as doc:
        for page in doc:
            for d in page.get_drawings():
                c = d.get("color")
                if c and all(abs(a - b) < 0.02 for a, b in zip(c, CHECK_COLOR)) \
                        and d.get("fill") is None:
                    checks += 1
            for b in page.get_text("dict")["blocks"]:
                for line in b.get("lines", []):
                    for sp in line["spans"]:
                        if sp["color"] == 0x007300 and sp["text"].strip():
                            counts += 1
    return checks, counts


def audit(data_dir: Path, out_dir: Path) -> list[dict]:
    findings: list[dict] = []

    def add(level, cub, check, detail):
        findings.append({"level": level, "cub": cub, "check": check, "detail": detail})

    log_path = out_dir / "fill_log.json"
    if not log_path.exists():
        raise SystemExit(f"missing {log_path} - run: python fill_passport.py --all")
    fill_log = json.loads(log_path.read_text(encoding="utf-8"))["cubs"]
    tracking = data_dir / "tracking.csv"
    signoffs = load_signoffs(data_dir / "stage_signoffs.csv")
    roster = json.loads((data_dir / "roster.json").read_text(encoding="utf-8"))

    # Data freshness
    raw = data_dir / "raw" / "scoutstracker.json"
    if raw.exists():
        fetched = json.loads(raw.read_text(encoding="utf-8")).get("fetched_at", "")
        if fetched:
            age = (datetime.now() - datetime.fromisoformat(fetched)).days
            if age > STALE_DAYS:
                add("WARN", "", "stale data", f"ScoutsTracker data is {age} days old "
                    "- run scrape/fetch.py again")

    # Roster: every active Cub has a passport, and nothing extra.
    for n in sorted(set(roster) - set(fill_log)):
        add("ERROR", n, "no passport", "Cub is on the roster but no passport was made")
    for n in sorted(set(fill_log) - set(roster)):
        add("WARN", n, "not on roster", "passport exists for someone not on the current roster")

    missing_rows: list[tuple[str, str, int]] = []
    for cub in sorted(fill_log):
        log = fill_log[cub]
        if "error" in log:
            add("ERROR", cub, "fill failed", log["error"])
            continue
        max_stage = log["max_stage"]
        earned = signoffs.get(cub, {})
        buckets = kid_buckets(tracking, cub)
        written = set(log["signoffs_written"])

        for (section, stage), row in sorted(earned.items()):
            label = f"{section} {stage}"
            if stage > max_stage:
                add("WARN", cub, "earned above range",
                    f"{label} earned {row['date']} but passport stops at stage {max_stage}")
                continue
            if label not in written:
                add("ERROR", cub, "sign-off missing", f"{label} earned but not written on passport")
            if row["scouter"].strip().lower() in ("", "unknown"):
                add("INFO", cub, "scouter blank",
                    f"{label}: dated {row['date']}, Scouter name left blank to sign by hand")
            ticked, total = buckets.get((section, stage), (0, 0))
            if total == 0:
                add("ERROR", cub, "no requirements", f"{label} earned but no requirement rows found")
            elif ticked < total:
                add("INFO", cub, "auto-ticked",
                    f"{label} earned with {ticked}/{total} ticked - remaining boxes ticked")

        for (section, stage), (ticked, total) in sorted(buckets.items()):
            if stage <= max_stage and total and ticked == total and (section, stage) not in earned:
                add("WARN", cub, "badge not awarded",
                    f"{section} {stage}: all {total} requirements ticked but stage not awarded")
                missing_rows.append((cub, section, stage))

        for u in log["unplaced"]:
            add("ERROR", cub, "tick not placed", u)
        for w in log.get("warnings", []):
            add("WARN", cub, "template", w)
        nights, boxes = log.get("camp_nights"), log.get("nights_boxes", 0)
        if nights and nights > boxes:
            add("INFO", cub, "camp nights", f"{nights} nights at camp; only {boxes} boxes on page 6")

        pdf = out_dir / log["pdf"]
        if not pdf.exists():
            add("ERROR", cub, "pdf missing", str(pdf))
            continue
        print_pdf = out_dir / "print 4-up" / f"{pdf.stem} - print 4-up.pdf"
        if not print_pdf.exists():
            add("ERROR", cub, "print file missing", print_pdf.name)
        else:
            with fitz.open(pdf) as d1, fitz.open(print_pdf) as d2:
                want = -(-len(d1) // 4)
                if len(d2) != want:
                    add("ERROR", cub, "print file wrong", f"{len(d2)} sheets, expected {want}")
        checks, counts = read_back(pdf)
        if checks != log["checks_drawn"] or counts != log["counts_drawn"]:
            add("ERROR", cub, "read-back mismatch",
                f"PDF has {checks} ticks/{counts} counts, expected "
                f"{log['checks_drawn']}/{log['counts_drawn']}")

    with (data_dir / "missing_badges.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["member", "section", "stage", "badge"])
        for cub, section, stage in sorted(missing_rows):
            w.writerow([cub, section, stage, f"{section} {stage}"])
    return findings


def write_reports(findings: list[dict], out_dir: Path, cubs: list[str]) -> None:
    with (out_dir / "audit.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["level", "cub", "check", "detail"])
        w.writeheader()
        w.writerows(findings)

    by_cub = defaultdict(list)
    for f_ in findings:
        by_cub[f_["cub"]].append(f_)
    colors = {"ERROR": "#c62828", "WARN": "#b26a00", "INFO": "#546e7a"}

    def status(items):
        lv = {i["level"] for i in items}
        return ("ERROR", "#fdecea") if "ERROR" in lv else \
               ("CHECK", "#fff4e0") if "WARN" in lv else ("OK", "#e8f5e9")

    rows = []
    for cub in [""] + sorted(cubs):
        items = by_cub.get(cub, [])
        if cub == "" and not items:
            continue
        st, bg = status(items)
        detail = "".join(
            f'<li><b style="color:{colors[i["level"]]}">{i["level"]}</b> '
            f'{html.escape(i["check"])}: {html.escape(i["detail"])}</li>' for i in items)
        rows.append(f'<tr style="background:{bg}"><td>{html.escape(cub or "(all)")}</td>'
                    f'<td><b>{st}</b></td><td><ul>{detail or "<li>nothing to report</li>"}'
                    f'</ul></td></tr>')
    n = {lv: sum(1 for f_ in findings if f_["level"] == lv) for lv in colors}
    (out_dir / "audit.html").write_text(f"""<!doctype html><meta charset="utf-8">
<title>Passport audit</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;color:#222}}
table{{border-collapse:collapse;width:100%}}td{{border:1px solid #ccc;padding:6px 10px;vertical-align:top}}
ul{{margin:0;padding-left:18px}}</style>
<h1>Passport audit</h1>
<p>{len(cubs)} passports &middot; <b style="color:{colors['ERROR']}">{n['ERROR']} errors</b>
 &middot; <b style="color:{colors['WARN']}">{n['WARN']} warnings</b> &middot; {n['INFO']} notes
 &middot; generated {datetime.now():%Y-%m-%d %H:%M}</p>
<p><b>ERROR</b> = something is missing from a passport. <b>WARN</b> = check this in
ScoutsTracker. <b>INFO</b> = expected, just so you know.</p>
<table><tr><th>Cub</th><th>Status</th><th>Details</th></tr>{''.join(rows)}</table>
""", encoding="utf-8")


def latest_out_dir() -> Path:
    dirs = sorted(p for p in OUT_DIR.glob("20*-*-*") if (p / "fill_log.json").exists())
    if not dirs:
        raise SystemExit("No filled passports found. Run: python fill_passport.py --all")
    return dirs[-1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit filled passports")
    ap.add_argument("--data")
    ap.add_argument("--out")
    a = ap.parse_args()
    data_dir = Path(a.data) if a.data else latest_data_dir()
    out_dir = Path(a.out) if a.out else latest_out_dir()

    findings = audit(data_dir, out_dir)
    cubs = sorted(json.loads((out_dir / "fill_log.json").read_text(encoding="utf-8"))["cubs"])
    write_reports(findings, out_dir, cubs)

    for lv in ("ERROR", "WARN", "INFO"):
        items = [f for f in findings if f["level"] == lv]
        print(f"\n{lv}: {len(items)}")
        for f in items[:200 if lv != "INFO" else 15]:
            print(f"  {f['cub'] or '(all)':<24} {f['check']:<20} {f['detail']}")
        if lv == "INFO" and len(items) > 15:
            print(f"  ... {len(items) - 15} more in audit.html")
    print(f"\nReport: {out_dir / 'audit.html'}")
    return 1 if any(f["level"] == "ERROR" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
