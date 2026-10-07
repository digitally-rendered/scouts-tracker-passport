"""
Fill a Scouts Canada Cub passport PDF for a given kid using a tracking CSV.

Usage:
    python fill_passport.py --all --stages 1-4        # every active Cub
    python fill_passport.py "First Last" --stages 1-4 # one Cub

Inputs:
    Passport 2026 Printable Generic.pdf      (this folder - the blank template)
    ~/ScoutsPassportData/data/<date>/         (from scrape/fetch.py + build_data.py)

Output (private, outside this folder - see paths.py):
    ~/ScoutsPassportData/out/<date>/<Cub Name> - Passport 2026.pdf
    ~/ScoutsPassportData/out/<date>/fill_log.json   (read by audit_passports.py)
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import pymupdf as fitz  # PyMuPDF

from paths import OUT_DIR, TEMPLATE_PDF, WORKSPACE
from print_layout import make_4up
from template_ext import TEMPLATE_MAX_STAGE, build_template, load_requirements


HERE = Path(__file__).parent
PDF_PATH = TEMPLATE_PDF
# Legacy inputs (April 2026 hand export); normally replaced by use_data_dir().
CSV_PATH = WORKSPACE / "legacy-2026-04" / "Untitled spreadsheet - Sheet1.csv"
SIGNOFFS_CSV = WORKSPACE / "legacy-2026-04" / "data" / "stage_signoffs.csv"
CUB_STATS_CSV = WORKSPACE / "legacy-2026-04" / "data" / "cub_stats.csv"
REQS_JSON: Path | None = None
FILL_LOG: dict[str, dict] = {}  # per-Cub record of what was drawn (read by the audit)  # set by use_data_dir(); None = template_ext default


def use_data_dir(data_dir: Path) -> None:
    """Read everything from a fetched data/<date>/ folder (see build_data.py)."""
    global CSV_PATH, SIGNOFFS_CSV, CUB_STATS_CSV, REQS_JSON
    CSV_PATH = data_dir / "tracking.csv"
    SIGNOFFS_CSV = data_dir / "stage_signoffs.csv"
    CUB_STATS_CSV = data_dir / "cub_stats.csv"
    REQS_JSON = data_dir / "oas_requirements.json"
    for f in (CSV_PATH, SIGNOFFS_CSV, CUB_STATS_CSV, REQS_JSON):
        if not f.exists():
            raise SystemExit(f"missing {f} - run: python build_data.py {data_dir}")

CHECKBOX_GLYPH = "❑"


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

@dataclass
class CsvReq:
    section: str        # e.g. "Aquatic Skills"
    stage: int          # 1, 2, 3, ...
    req_id: str         # e.g. "1.1", "2.1a"
    description: str    # truncated description from CSV (may end with "...")
    value: str          # raw value for the chosen kid (e.g. "✓", "9", "")


def _norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = re.sub(r"\s+", " ", s).strip().lower()
    s = s.rstrip(".").rstrip()
    if s.endswith("..."):
        s = s[:-3].rstrip()
    # strip trailing punctuation
    s = re.sub(r"[\.,;:]+$", "", s)
    return s


SECTION_HEADER_RE = re.compile(r"^\s*▼\s*(.+?)\s*(\d+)?\s*$")


def parse_csv_for_kid(csv_path: Path, kid_name: str) -> list[CsvReq]:
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))

    header = rows[0]
    # find kid column (header may have leading blanks)
    try:
        kid_col = header.index(kid_name)
    except ValueError:
        # try fuzzy: case-insensitive
        kid_col = next(
            (i for i, h in enumerate(header) if h.strip().lower() == kid_name.strip().lower()),
            -1,
        )
        if kid_col < 0:
            available = [h for h in header if h.strip()]
            raise SystemExit(f"Kid {kid_name!r} not in CSV header. Available: {available}")

    out: list[CsvReq] = []
    cur_section = None
    cur_stage = None

    for row in rows[1:]:
        if not row:
            continue
        first = (row[0] or "").strip()
        second = (row[1] if len(row) > 1 else "").strip()

        m = SECTION_HEADER_RE.match(first)
        if m:
            name = m.group(1).strip()
            stage = m.group(2)
            cur_section = name
            cur_stage = int(stage) if stage else None
            continue

        # requirement rows start with "#"
        if not first.startswith("#"):
            continue
        if cur_section is None:
            continue

        req_id = first.lstrip("#").strip()
        # Stage may be derivable from req_id prefix (e.g. "2.1a" -> stage 2)
        stage_from_id = None
        m2 = re.match(r"(\d+)", req_id)
        if m2:
            stage_from_id = int(m2.group(1))
        stage = cur_stage if cur_stage is not None else stage_from_id

        value = row[kid_col].strip() if kid_col < len(row) else ""
        out.append(
            CsvReq(
                section=cur_section,
                stage=stage,
                req_id=req_id,
                description=second,
                value=value,
            )
        )

    return out


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------

@dataclass
class PdfCheckbox:
    page_index: int
    bbox: tuple[float, float, float, float]  # ❑ glyph bbox
    text: str                                 # description text to the right
    section: str | None = None
    stage: int | None = None


@dataclass
class SignoffLine:
    """A "Complete: ___ by ___" / "Completed:" / "AWARDED:" line in the PDF."""
    page_index: int
    bbox: tuple[float, float, float, float]
    text: str
    section: str | None
    stage: int | None


# Section names as they appear in the PDF (must match the CSV section names)
SECTION_NAMES = {
    "Aquatic Skills",
    "Camping Skills",
    "Emergency Skills",
    "Paddling Skills",
    "Sailing Skills",
    "Scoutcraft Skills",
    "Trail Skills",
    "Vertical Skills",
    "Winter Skills",
}


def _gather_spans(page: fitz.Page) -> list[dict]:
    """Spans in reading order, with rows clustered by approximate y.

    Some pages have the stage-marker digit ("1"/"2"/"3", 48pt) on the same
    visual row as the next checkbox — but fitz puts them in separate "lines"
    with slightly different y0 floats. We bucket lines that share a row
    (within an 8pt tolerance) so within-row x-sort applies across them.
    """
    raw_lines = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            spans = [sp for sp in line["spans"] if sp.get("text")]
            if not spans:
                continue
            ys = [sp["bbox"][1] for sp in spans]
            row_y = sum(ys) / len(ys)
            raw_lines.append((row_y, spans))

    raw_lines.sort(key=lambda r: r[0])
    rows: list[tuple[float, list]] = []
    for row_y, spans in raw_lines:
        if rows and row_y - rows[-1][0] < 8:
            rows[-1][1].extend(spans)
        else:
            rows.append((row_y, list(spans)))

    out = []
    for _, spans in rows:
        spans.sort(key=lambda s: s["bbox"][0])
        for sp in spans:
            out.append({"text": sp["text"], "bbox": tuple(sp["bbox"]), "size": sp["size"]})
    return out


_STOPWORDS_PREFIX = ("complete:", "completed:", "awarded:", "awarded :")
_BADGES_HEADER = "personal achievement badges"


def extract_pdf_checkboxes(
    pdf: Path | fitz.Document,
) -> tuple[fitz.Document, list[PdfCheckbox], list[SignoffLine], list[PdfCheckbox]]:
    """Walk every page in reading order.

    Returns (doc, checkboxes, signoff_lines, nights_boxes):
        checkboxes  — every requirement ❑ with its description.
        signoff_lines — every "Complete:" / "Completed:" / "AWARDED:" line, tagged
            with the (section, stage) it closes.
        nights_boxes — the 7 ❑'s on the "Nights At Camp" tracker (page 6 only;
            they sit before any stage marker for Camping Skills).
    """
    doc = pdf if isinstance(pdf, fitz.Document) else fitz.open(pdf)
    out: list[PdfCheckbox] = []
    signoffs: list[SignoffLine] = []
    nights: list[PdfCheckbox] = []
    cur_section: str | None = None
    cur_stage: int | None = None
    in_skills = True

    open_box: PdfCheckbox | None = None
    text_buf: list[str] = []

    def _flush():
        nonlocal open_box, text_buf
        if open_box is not None:
            open_box.text = re.sub(r"\s+", " ", " ".join(text_buf)).strip()
            out.append(open_box)
        open_box = None
        text_buf = []

    for page_index, page in enumerate(doc):
        spans = _gather_spans(page)
        for sp in spans:
            t = sp["text"]
            t_strip = t.strip()
            t_lower = t_strip.lower()

            if not t_strip:
                continue

            # Hard cut once we reach the achievement-badges section
            if _BADGES_HEADER in t_lower:
                _flush()
                in_skills = False
                continue
            if not in_skills:
                continue

            # Section heading
            if t_strip in SECTION_NAMES:
                _flush()
                cur_section = t_strip
                cur_stage = None
                continue

            # Standalone stage marker (48pt numeral; generated pages add 4+)
            if re.fullmatch(r"[1-9]", t_strip) and sp["size"] >= 30 and cur_section:
                _flush()
                cur_stage = int(t_strip)
                continue

            # Stop words that close the current box. These are "Complete: ___ by ___"
            # lines (one per stage) — capture them so we can fill date + Scouter.
            if any(t_lower.startswith(p) for p in _STOPWORDS_PREFIX):
                _flush()
                if cur_section and cur_stage:
                    signoffs.append(
                        SignoffLine(
                            page_index=page_index,
                            bbox=tuple(sp["bbox"]),
                            text=t_strip,
                            section=cur_section,
                            stage=cur_stage,
                        )
                    )
                continue

            # A span may contain a single ❑ or a run of them (e.g. the
            # "Nights At Camp ❑❑❑❑❑❑❑" tracker on page 6). Treat each glyph
            # as its own checkbox; split the span's bbox horizontally.
            if set(t_strip) == {CHECKBOX_GLYPH}:
                _flush()
                n = len(t_strip)
                x0, y0, x1, y1 = sp["bbox"]
                glyph_w = (x1 - x0) / n
                for i in range(n):
                    gx0 = x0 + i * glyph_w
                    gx1 = gx0 + glyph_w
                    # Nights-At-Camp tracker: ❑'s on Camping Skills page before stage 1.
                    if cur_section == "Camping Skills" and cur_stage is None:
                        nights.append(
                            PdfCheckbox(
                                page_index=page_index,
                                bbox=(gx0, y0, gx1, y1),
                                text="nights-at-camp",
                                section=cur_section,
                                stage=None,
                            )
                        )
                        continue
                    out.append(
                        PdfCheckbox(
                            page_index=page_index,
                            bbox=(gx0, y0, gx1, y1),
                            text="",
                            section=cur_section,
                            stage=cur_stage,
                        )
                    )
                # Single ❑ behaves like a regular checkbox: re-open one if so,
                # so subsequent text becomes its description.
                if n == 1 and not (cur_section == "Camping Skills" and cur_stage is None):
                    # We already appended a placeholder above; replace the open_box
                    # so following spans accumulate into its description.
                    open_box = out.pop()
                    text_buf = []
                continue

            if open_box is not None:
                text_buf.append(t)
        # end of page: keep open_box state across pages (descriptions wrap pages rarely
        # but stage numbers don't repeat, so we leave it open)

    _flush()
    return doc, out, signoffs, nights


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    a, b = _norm_text(a), _norm_text(b)
    if not a or not b:
        return 0.0
    # CSV descriptions are truncated; if CSV is a prefix of PDF, near-perfect.
    if b.startswith(a) or a.startswith(b):
        return 1.0
    # Substring containment: handles cases where PDF text gathered some sibling
    # text on the same line — if the CSV phrase appears anywhere in PDF text,
    # treat that as strong evidence.
    if a in b:
        return 0.95
    # Fall back to longest contiguous match scaled by the shorter string.
    sm = SequenceMatcher(None, a, b)
    block = sm.find_longest_match(0, len(a), 0, len(b))
    if block.size:
        partial = block.size / max(len(a), 1)
        ratio = sm.ratio()
        return max(partial, ratio)
    return 0.0


def _align_bucket(
    csv_rows: list[CsvReq],
    pdf_local: list[tuple[int, PdfCheckbox]],
    min_score: float = 0.45,
) -> dict[int, CsvReq]:
    """In-order alignment via DP. Returns {global_pdf_idx: CsvReq}."""
    n, m = len(csv_rows), len(pdf_local)

    # Special case: counts match → trust the structural ordering.
    if n == m and n > 0:
        return {pdf_local[j][0]: csv_rows[j] for j in range(n)}

    if n == 0 or m == 0:
        return {}

    # DP: dp[i][j] = (best_score, parent_action)
    NEG = float("-inf")
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    parent = [[None] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        for j in range(m + 1):
            best_score = 0.0 if (i == 0 and j == 0) else NEG
            best_action = None
            if i > 0 and dp[i - 1][j] > best_score:
                best_score = dp[i - 1][j]
                best_action = ("skip_csv", i - 1, j)
            if j > 0 and dp[i][j - 1] > best_score:
                best_score = dp[i][j - 1]
                best_action = ("skip_pdf", i, j - 1)
            if i > 0 and j > 0:
                s = _similarity(csv_rows[i - 1].description, pdf_local[j - 1][1].text)
                if s >= min_score:
                    candidate = dp[i - 1][j - 1] + s
                    if candidate > best_score:
                        best_score = candidate
                        best_action = ("match", i - 1, j - 1)
            dp[i][j] = best_score
            parent[i][j] = best_action

    matches: dict[int, CsvReq] = {}
    i, j = n, m
    while parent[i][j] is not None:
        kind, pi, pj = parent[i][j]
        if kind == "match":
            global_idx = pdf_local[pj][0]
            matches[global_idx] = csv_rows[pi]
        i, j = pi, pj
    return matches


def match_requirements(csv_reqs: list[CsvReq], pdf_boxes: list[PdfCheckbox]):
    pdf_buckets: dict[tuple[str, int], list[tuple[int, PdfCheckbox]]] = {}
    for i, b in enumerate(pdf_boxes):
        if b.section is None or b.stage is None:
            continue
        pdf_buckets.setdefault((b.section, b.stage), []).append((i, b))

    by_bucket: dict[tuple[str, int], list[CsvReq]] = {}
    for r in csv_reqs:
        by_bucket.setdefault((r.section, r.stage), []).append(r)

    matches: dict[int, CsvReq] = {}
    unmatched: list[CsvReq] = []
    for key, reqs in by_bucket.items():
        bucket = pdf_buckets.get(key, [])
        bucket_matches = _align_bucket(reqs, bucket)
        matches.update(bucket_matches)
        matched_csv_ids = {id(r) for r in bucket_matches.values()}
        for r in reqs:
            if id(r) not in matched_csv_ids:
                unmatched.append(r)
    return matches, unmatched


# ---------------------------------------------------------------------------
# Overlay
# ---------------------------------------------------------------------------

def draw_check(page: fitz.Page, bbox):
    """Draw a checkmark inside the checkbox bbox."""
    x0, y0, x1, y1 = bbox
    # bbox is generous (full line height); draw a tight ✓ near the box
    # Use a vector check rather than a font glyph for reliable rendering.
    pad_x = 2
    cy = (y0 + y1) / 2
    h = (y1 - y0) * 0.5
    w = (x1 - x0) - 2 * pad_x
    # checkmark points
    p1 = (x0 + pad_x + 0.15 * w, cy + 0.05 * h)
    p2 = (x0 + pad_x + 0.42 * w, cy + 0.32 * h)
    p3 = (x0 + pad_x + 0.95 * w, cy - 0.45 * h)
    page.draw_polyline([p1, p2, p3], color=(0, 0.45, 0), width=1.6)


def draw_count(page: fitz.Page, bbox, count_text: str):
    """Draw a small number near the checkbox (for count-style entries)."""
    x0, y0, x1, y1 = bbox
    page.insert_text(
        (x0 + 1, y1 - 4),
        count_text,
        fontsize=9,
        color=(0, 0.45, 0),
    )


# ---------------------------------------------------------------------------
# Sign-off + stats (from ScoutsTracker exports under data/)
# ---------------------------------------------------------------------------

def _load_signoffs_for(kid_name: str) -> dict[tuple[str, int], dict]:
    """Map (section, stage) -> {date, scouter, scope} for this kid.

    Sign-offs with scouter == "Unknown" are kept (callers decide what to do).
    Badge labels in the CSV look like "Camping Skills 2"; we split those into
    (section="Camping Skills", stage=2). Non-stage badges (Runner, Seeonee,
    etc.) are returned with stage=0 keyed under their full label.
    """
    out: dict[tuple[str, int], dict] = {}
    if not SIGNOFFS_CSV.exists():
        return out
    with SIGNOFFS_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["member"] != kid_name:
                continue
            badge = row["badge"].strip()
            m = re.match(r"^(.+?)\s+(\d+)$", badge)
            if m:
                key = (m.group(1), int(m.group(2)))
            else:
                key = (badge, 0)
            out[key] = {
                "date": row["date"],
                "scouter": row["scouter"],
                "scope": row["scope"],
            }
    return out


def _load_camp_nights_for(kid_name: str) -> int | None:
    """Return integer nights at camp from cub_stats.csv, or None if not found."""
    if not CUB_STATS_CSV.exists():
        return None
    with CUB_STATS_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["name"] != kid_name:
                continue
            v = row.get("Camps", "").strip()
            m = re.match(r"^(\d+)n?$", v)
            if m:
                return int(m.group(1))
            return None
    return None


def write_signoff(page: fitz.Page, signoff: SignoffLine, date_str: str, scouter: str):
    """Write date and Scouter name on top of a "Complete: ___ by ___" line.

    The whole "Complete: ____ by ____" sits in one span. We measure the widths
    of each piece in the PDF's font to land each value correctly on its own
    underline.
    """
    x0, y0, x1, y1 = signoff.bbox
    # Detect prefix word ("Complete:" / "Completed:" / "AWARDED:")
    text = signoff.text
    m = re.match(r"^(?P<pre>\S+:?)\s*", text)
    if not m:
        return
    pre = m.group("pre")
    fontname = "helv"
    fontsize = 11
    pre_w = fitz.get_text_length(pre + " ", fontname=fontname, fontsize=14)
    by_w = fitz.get_text_length(" by ", fontname=fontname, fontsize=14)
    # Underline of "_____________" uses a wider glyph; estimate first underline
    # ~120pt long, then " by " ~25pt, then second underline ~150pt. The whole
    # span runs from x0 to x1.
    line_w = x1 - x0
    # Approximate split: first 45% of remaining width for date, last 55% for scouter
    remaining = line_w - pre_w - by_w
    date_x = x0 + pre_w
    scouter_x = x0 + pre_w + remaining * 0.45 + by_w
    text_y = y1 - 3
    page.insert_text(
        (date_x, text_y), date_str, fontsize=fontsize, color=(0, 0.3, 0.6)
    )
    page.insert_text(
        (scouter_x, text_y), scouter, fontsize=fontsize, color=(0, 0.3, 0.6)
    )


def fill_passport(kid_name: str, debug: bool = False, max_stage: int = TEMPLATE_MAX_STAGE,
                  out_dir: Path = OUT_DIR) -> Path:
    csv_reqs = parse_csv_for_kid(CSV_PATH, kid_name)
    drawn = {"checks": 0, "counts": 0}

    def _check(page, bbox):
        drawn["checks"] += 1
        draw_check(page, bbox)

    def _count(page, bbox, text):
        drawn["counts"] += 1
        draw_count(page, bbox, text)
    base_doc, gen_boxes, _gen_signoffs, overview_cells, warnings = build_template(
        PDF_PATH, max_stage, load_requirements(REQS_JSON) if REQS_JSON else None)
    for w in warnings:
        print(f"  note: {w}")
    doc, pdf_boxes, signoff_lines, nights_boxes = extract_pdf_checkboxes(base_doc)
    # Generated stage 4+ pages draw vector checkboxes, so add them explicitly.
    pdf_boxes += [PdfCheckbox(b.page_index, b.bbox, b.text, b.section, b.stage)
                  for b in gen_boxes]
    matches, unmatched = match_requirements(csv_reqs, pdf_boxes)
    signoffs = _load_signoffs_for(kid_name)
    camp_nights = _load_camp_nights_for(kid_name)

    # If a stage was earned, every lower stage in the same section is implied.
    # (You can't have Camping Skills 2 without Camping Skills 1.) Synthesize
    # the missing rows so they get ticked + signed below.
    earned_max: dict[str, int] = {}
    for (section, stage), info in signoffs.items():
        if stage > 0 and section in SECTION_NAMES:
            earned_max[section] = max(earned_max.get(section, 0), stage)
    for section, top in earned_max.items():
        for s in range(1, top + 1):
            signoffs.setdefault((section, s), {"date": "", "scouter": "", "scope": "implied"})

    earned_stages = {k for k, v in signoffs.items() if k[1] > 0 and k[0] in SECTION_NAMES}

    filled = 0
    auto_filled = 0
    for pdf_i, box in enumerate(pdf_boxes):
        req = matches.get(pdf_i)
        v = (req.value.strip() if req else "")
        page = doc[box.page_index]

        if v == "✓":
            _check(page, box.bbox)
            filled += 1
            continue
        if v and re.fullmatch(r"\d+", v):
            _count(page, box.bbox, v)
            filled += 1
            continue
        if v and not v.startswith("#"):
            _count(page, box.bbox, v)
            filled += 1
            continue

        # No (or "#ERROR!") value from the tracking sheet, but if the kid earned
        # the stage badge that implies all requirements were met — tick the box.
        if (box.section, box.stage) in earned_stages:
            _check(page, box.bbox)
            auto_filled += 1

    # Cover page: write the kid's name on the underline on page 1.
    # The underline span sits at roughly y=204.7 from x=70 to x=310; we center
    # the name above the line.
    cover = doc[0]
    fontsize = 16
    line_w = fitz.get_text_length(kid_name, fontname="helv", fontsize=fontsize)
    cx = 70 + (310 - 70) / 2
    cover.insert_text(
        (cx - line_w / 2, 200), kid_name, fontsize=fontsize, color=(0, 0, 0)
    )

    # Stage sign-offs: write date + Scouter on each "Complete: ___ by ___" line.
    # For Colony-era entries (scouter=Unknown) and implied lower stages, write
    # whatever date we have and leave "by ___" blank for hand-fill.
    signoffs_filled = signoffs_partial = 0
    signoffs_written: list[str] = []
    for line in signoff_lines:
        info = signoffs.get((line.section, line.stage))
        if not info:
            continue
        scouter = (info["scouter"] or "").strip()
        date = (info["date"] or "").strip()
        if scouter.lower() == "unknown" or not scouter:
            write_signoff(doc[line.page_index], line, date, "")
            signoffs_partial += 1
        else:
            write_signoff(doc[line.page_index], line, date, scouter)
            signoffs_filled += 1
        signoffs_written.append(f"{line.section} {line.stage}")

    # Nights at camp tracker (page 6, 7 ❑'s before stage 1 of Camping Skills).
    nights_filled = 0
    if camp_nights is not None and nights_boxes:
        # Sort by bbox x so we tick left-to-right in document order.
        nights_boxes.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
        n_to_tick = min(camp_nights, len(nights_boxes))
        for box in nights_boxes[:n_to_tick]:
            _check(doc[box.page_index], box.bbox)
            nights_filled += 1

    # OAS overview grid (page 3, redrawn when stages > 3): tick earned stages.
    for section, stage, cell in overview_cells:
        if (section, stage) in earned_stages:
            w = 14
            cx, cy = (cell.x0 + cell.x1) / 2, (cell.y0 + cell.y1) / 2
            _check(doc[2], (cx - w / 2, cy - w / 2 - 2, cx + w / 2, cy + w / 2 + 2))

    # Earned stages that have no page in this passport (beyond --stages).
    placed_signoffs = {(l.section, l.stage) for l in signoff_lines}
    not_in_passport = sorted(k for k in earned_stages if k not in placed_signoffs)
    for key in not_in_passport:
        print(f"  WARNING: {key[0]} {key[1]} earned but not in this passport "
              f"(stage range ends at {max_stage})")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{kid_name} - Passport 2026.pdf"
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    # Printable version: 4 pages per letter sheet, cut-and-stack order.
    print_dir = out_dir / "print 4-up"
    print_dir.mkdir(exist_ok=True)
    sheets = make_4up(out_path, print_dir / f"{out_path.stem} - print 4-up.pdf",
                      out_path.stem, kid_name)

    print(f"Filled {filled} checkboxes for {kid_name} "
          f"(+{auto_filled} auto-ticked from earned stage badges)")
    print(
        f"Sign-offs: {signoffs_filled} fully dated+signed, "
        f"{signoffs_partial} dated only (scouter blank for hand-fill)"
    )
    if camp_nights is not None:
        print(
            f"Nights at camp: {nights_filled} ticked "
            f"(of {camp_nights} total; {len(nights_boxes)} boxes available)"
        )
    print(f"Matched {len(matches)}/{len(csv_reqs)} CSV rows; "
          f"{len(unmatched)} unmatched CSV rows")

    # Surface only unmatched rows that the Cub has a real value for — these are the
    # potential misses the user actually cares about.
    real_misses = [r for r in unmatched if r.value and not r.value.startswith("#")]
    # Sub-requirements (e.g. "3.12a") whose parent row ("3.12") got a box are
    # covered: the passport prints them as one checkbox.
    matched_ids = {(r.section, r.req_id) for r in matches.values()}
    real_misses = [r for r in real_misses
                   if not (re.fullmatch(r"\d+\.\d+[a-z]", r.req_id)
                           and (r.section, r.req_id[:-1]) in matched_ids)]
    not_in_pdf_sections = {"Runner", "Tracker", "Howler", "Seeonee Award"}
    csv_only = [r for r in real_misses if r.section in not_in_pdf_sections]
    real_misses = [r for r in real_misses if r.section not in not_in_pdf_sections]
    beyond = [r for r in real_misses if r.stage and r.stage > max_stage]
    real_misses = [r for r in real_misses if not (r.stage and r.stage > max_stage)]
    if beyond:
        ticks = [r for r in beyond if r.value == "✓"]
        print(f"{len(beyond)} values above stage {max_stage} not shown "
              f"({len(ticks)} ticks, {len(beyond) - len(ticks)} tally counts)")

    if csv_only:
        print(f"\n{len(csv_only)} CSV ticks in sections not present in this PDF "
              "(separate badge tracking — fill manually):")
        for r in csv_only:
            print(f"  [{r.section} #{r.req_id}] value={r.value!r}")

    if real_misses:
        print(f"\n{len(real_misses)} CSV ticks the script could not place "
              "(check manually):")
        for r in real_misses:
            print(f"  [{r.section} stage {r.stage} #{r.req_id}] "
                  f"{r.description!r} value={r.value!r}")

    if debug and unmatched:
        print("\nAll unmatched CSV rows:")
        for r in unmatched:
            print(f"  [{r.section} stage {r.stage} #{r.req_id}] {r.description!r} "
                  f"value={r.value!r}")

    print(f"\nWrote {out_path}")
    FILL_LOG[kid_name] = {
        "pdf": out_path.name,
        "max_stage": max_stage,
        "checks_drawn": drawn["checks"],
        "counts_drawn": drawn["counts"],
        "auto_ticked": auto_filled,
        "signoffs_written": signoffs_written,
        "earned_not_in_passport": [f"{a} {b}" for a, b in not_in_passport],
        "unplaced": [f"{r.section} {r.req_id} = {r.value}" for r in real_misses],
        "other_awards_not_in_pdf": [f"{r.section} {r.req_id} = {r.value}" for r in csv_only],
        "above_range_values": len(beyond),
        "camp_nights": camp_nights,
        "nights_boxes": len(nights_boxes),
        "warnings": warnings,
        "print_sheets": sheets,
    }
    return out_path


def fill_all_from_roster(**kw) -> None:
    """Fill a passport for every kid in cub_stats.csv (i.e. the active Pack)."""
    if not CUB_STATS_CSV.exists():
        raise SystemExit(f"missing {CUB_STATS_CSV} — run the ScoutsTracker scrape first")
    names = []
    with CUB_STATS_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            n = row.get("name", "").strip()
            if n:
                names.append(n)
    print(f"Filling {len(names)} passports...\n")
    for n in names:
        try:
            fill_passport(n, **kw)
        except SystemExit as e:
            print(f"  skipping {n}: {e}")
            FILL_LOG[n] = {"error": str(e)}
        print()
    out_dir = Path(kw.get("out_dir", OUT_DIR))
    # One combined print file for the whole pack (each Cub's sheets are together;
    # cut and stack one Cub at a time - the Cub's name is printed on each sheet).
    combined = fitz.open()
    for n in names:
        f = out_dir / "print 4-up" / f"{n} - Passport 2026 - print 4-up.pdf"
        if f.exists():
            with fitz.open(f) as part:
                combined.insert_pdf(part)
    if len(combined):
        combined.save(out_dir / "print 4-up" / "ALL CUBS - print 4-up.pdf", garbage=3, deflate=True)
        print(f"Wrote {out_dir / 'print 4-up' / 'ALL CUBS - print 4-up.pdf'} ({len(combined)} sheets)")
    combined.close()
    log_path = out_dir / "fill_log.json"
    log_path.write_text(json.dumps({"data": str(CSV_PATH.parent), "cubs": FILL_LOG},
                                   indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {log_path}")


if __name__ == "__main__":
    import argparse
    from datetime import date

    from template_ext import parse_stages

    ap = argparse.ArgumentParser(description="Fill Cub passports.")
    ap.add_argument("name", nargs="*", help="Cub name (omit with --all)")
    ap.add_argument("--all", action="store_true", help="every Cub in cub_stats.csv")
    ap.add_argument("--stages", default="1-4", help="OAS stage range, e.g. 1-4")
    ap.add_argument("--data", help="fetched data folder (default: newest data/<date>/; "
                    "'legacy' = old spreadsheet + data/*.csv)")
    ap.add_argument("--out", default=str(OUT_DIR / date.today().isoformat()))
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    _, hi = parse_stages(a.stages)
    if a.data != "legacy":
        from build_data import latest_data_dir
        use_data_dir(Path(a.data) if a.data else latest_data_dir())
        print(f"Using data from {CSV_PATH.parent}\n")
    kw = {"max_stage": hi, "out_dir": Path(a.out)}
    if a.all:
        fill_all_from_roster(**kw)
    else:
        if not a.name:
            ap.error("give a Cub's name, or use --all")
        fill_passport(" ".join(a.name), debug=a.debug, **kw)
