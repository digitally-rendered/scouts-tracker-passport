"""Extend the Cub passport template with extra OAS stages (4+) in the same style.

The original PDF only has stages 1-3 per skill. For each stage beyond that,
this draws new pages that copy the template's look: the big green stage
numeral, a checkbox per requirement, a right-hand sign-off column, and a
boxed "Complete: ___ by ___" row. Pages are inserted right after the skill's
last original page. The OAS overview grid on page 3 is redrawn with one
column per stage.

Requirement text comes from data/oas_requirements.json:
    {"Camping Skills": {"4": ["I can ...", ...]}, ...}

Usage:
    python template_ext.py --stages 1-4            # blank extended template
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz  # PyMuPDF

from paths import FONTS_DIR, OUT_DIR, TEMPLATE_PDF

HERE = Path(__file__).parent
REQS_JSON = None  # pass a data/<date>/oas_requirements.json path

# --- Template geometry (measured from Passport 2026 Printable Generic.pdf) ---
PAGE_W, PAGE_H = 396, 612
TOP = 36.0
BOTTOM_LIMIT = 576.0
X_LEFT, X_NUM_R, X_BOX_R, X_TEXT_R, X_RIGHT = 36.0, 73.7, 104.7, 310.2, 359.6
TEXT_X = 110.1
TEXT_W = X_TEXT_R - TEXT_X - 4
TEXT_SIZE = 12.0
LINE_H = 14.66
FIRST_BASELINE = 11.76     # row top -> first text baseline
NUM_X, NUM_BASELINE, NUM_SIZE = 42.6, 45.5, 48.0
MIN_ROW_H = 24.9
ROW_PAD = 5.0
SIGNOFF_H = 31.1
SIGNOFF_X, SIGNOFF_BASELINE, SIGNOFF_SIZE = 58.9, 24.5, 14.0
SIGNOFF_TEXT = "Complete: ________________ by __________________"
RULE_W = 0.48
GREEN = (0x92 / 255, 0xD0 / 255, 0x50 / 255)
BLACK = (0, 0, 0)

# Box glyph (Wingdings ❑) rebuilt as vectors so no Wingdings font is needed.
BOX_DX, BOX_DY, BOX_SIZE, BOX_BORDER, BOX_SHADOW = 1.85, 4.4, 13.75, 1.05, 2.15
BOX_GLYPH_X = 79.1

# First page index (0-based) of each skill in the original template; the skill
# ends on the page before the next skill starts (Winter ends before PABs).
SKILL_FIRST_PAGE = {
    "Aquatic Skills": 3, "Camping Skills": 5, "Emergency Skills": 8,
    "Paddling Skills": 12, "Sailing Skills": 16, "Scoutcraft Skills": 20,
    "Trail Skills": 23, "Vertical Skills": 26, "Winter Skills": 28,
}
PAB_FIRST_PAGE = 32
TEMPLATE_MAX_STAGE = 3

# Overview grid (page 3)
OVERVIEW_PAGE = 2
GRID_TOP, GRID_HEADER_BOTTOM, GRID_ROW_H = 138.9, 151.6, 36.52
GRID_LABEL_R = 130.4

FONT_DIRS = [
    FONTS_DIR,
    Path("/Applications/Microsoft Word.app/Contents/Resources/DFonts"),
    Path("/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts"),
    Path("/Applications/Microsoft Excel.app/Contents/Resources/DFonts"),
    Path("/Library/Fonts"), Path.home() / "Library/Fonts",
    Path("C:/Windows/Fonts"),
    Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
]
# Office 365 on Windows downloads Aptos as a "cloud font" into this cache.
CLOUD_FONTS = Path.home() / "AppData/Local/Microsoft/FontCache/4/CloudFonts"


def _find_font(filename: str) -> str | None:
    for d in FONT_DIRS:
        p = d / filename
        if p.exists():
            return str(p)
    if CLOUD_FONTS.is_dir():
        want = filename.rsplit(".", 1)[0].replace("-", " ").lower()  # "aptos narrow bold"
        for p in CLOUD_FONTS.rglob("*.ttf"):
            try:
                if fitz.Font(fontfile=str(p)).name.replace("-", " ").lower() == want:
                    return str(p)
            except Exception:
                continue
    return None


@dataclass
class Fonts:
    """Aptos if installed (comes with Microsoft Office), else Helvetica."""
    body: tuple[str, str | None]
    bold: tuple[str, str | None]
    narrow: tuple[str, str | None]
    narrow_bold: tuple[str, str | None]

    @classmethod
    def detect(cls) -> "Fonts":
        def pick(alias, file, fallback):
            path = _find_font(file)
            return (alias, path) if path else (fallback, None)
        return cls(
            body=pick("aptos", "Aptos.ttf", "helv"),
            bold=pick("aptosb", "Aptos-Bold.ttf", "hebo"),
            narrow=pick("aptosn", "Aptos-Narrow.ttf", "helv"),
            narrow_bold=pick("aptosnb", "Aptos-Narrow-Bold.ttf", "hebo"),
        )

    @property
    def is_fallback(self) -> bool:
        return self.body[1] is None

    def measure(self, which, text: str, size: float) -> float:
        name, path = which
        font = fitz.Font(fontfile=path) if path else fitz.Font(name)
        return font.text_length(text, size)


def _text(page: fitz.Page, xy, text, which, size, color=BLACK):
    name, path = which
    kw = {"fontname": name, "fontsize": size, "color": color}
    if path:
        kw["fontfile"] = path
    page.insert_text(xy, text, **kw)


def _hline(page, x0, x1, y):
    page.draw_rect(fitz.Rect(x0, y, x1, y + RULE_W), color=None, fill=BLACK)


def _vline(page, x, y0, y1):
    page.draw_rect(fitz.Rect(x, y0, x + RULE_W, y1), color=None, fill=BLACK)


def draw_box(page: fitz.Page, row_top: float) -> fitz.Rect:
    """Draw the ❑ checkbox; returns a bbox shaped like the template glyph's."""
    x0 = BOX_GLYPH_X + BOX_DX
    y0 = row_top + BOX_DY
    x1, y1, o = x0 + BOX_SIZE, y0 + BOX_SIZE, BOX_SHADOW
    shadow = [(x1, y0 + o), (x1 + o, y0 + 2 * o), (x1 + o, y1 + o),
              (x0 + 2 * o, y1 + o), (x0 + o, y1), (x1, y1)]
    page.draw_polyline(shadow, color=None, fill=BLACK, closePath=True)
    hb = BOX_BORDER / 2
    page.draw_rect(fitz.Rect(x0 + hb, y0 + hb, x1 - hb, y1 - hb),
                   color=BLACK, width=BOX_BORDER)
    # Same footprint as the Wingdings glyph span so draw_check() lands the same.
    return fitz.Rect(BOX_GLYPH_X, row_top + 0.5, BOX_GLYPH_X + 19.6, row_top + 24.8)


def wrap(fonts: Fonts, text: str, size: float = TEXT_SIZE) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if cur and fonts.measure(fonts.body, cand, size) > TEXT_W:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines or [""]


# Stage layout: one page if it fits, otherwise split evenly across pages.
# Text always stays at the template's 12pt so every page reads at the same scale.
PAGE_AVAIL = BOTTOM_LIMIT - TOP


@dataclass
class StageLayout:
    size: float                      # text size
    line_h: float
    rows: list[tuple[str, list[str], float]]   # (requirement, wrapped lines, row height)
    pages: list[list[int]]           # row indexes per page


def _rows_at(fonts: Fonts, reqs: list[str], size: float):
    scale = size / TEXT_SIZE
    line_h, pad, min_h = LINE_H * scale, ROW_PAD * scale, MIN_ROW_H * scale
    rows = []
    for r in reqs:
        lines = wrap(fonts, r, size)
        rows.append((r, lines, max(min_h, len(lines) * line_h + pad)))
    return rows, line_h


def plan_stage(fonts: Fonts, reqs: list[str]) -> StageLayout:
    # Fewest pages that fit, with rows balanced so no page is left nearly empty.
    rows, line_h = _rows_at(fonts, reqs, TEXT_SIZE)
    heights = [h for _, _, h in rows]
    total = sum(heights) + SIGNOFF_H
    n = max(1, -(-int(total) // int(PAGE_AVAIL)))
    while True:
        target = total / n
        pages, cur, used = [], [], 0.0
        for i, h in enumerate(heights):
            remaining_pages = n - len(pages) - 1
            # Break when this row would take the page past the target (but
            # never leave the last page needing more than one page of room).
            if cur and remaining_pages > 0 and used + h / 2 > target:
                pages.append(cur)
                cur, used = [], 0.0
            cur.append(i)
            used += h
        pages.append(cur)
        fits = all(sum(heights[i] for i in pg) + (SIGNOFF_H if k == len(pages) - 1 else 0)
                   <= PAGE_AVAIL for k, pg in enumerate(pages))
        if fits and len(pages) == n:
            return StageLayout(TEXT_SIZE, line_h, rows, pages)
        n += 1


@dataclass
class GenBox:
    page_index: int
    bbox: tuple[float, float, float, float]
    text: str
    section: str
    stage: int


@dataclass
class GenSignoff:
    page_index: int
    bbox: tuple[float, float, float, float]
    text: str
    section: str
    stage: int


def _draw_stage(doc, insert_at, section, stage, reqs, fonts):
    """Draw one stage starting on a new page at insert_at. Returns
    (pages_added, boxes, signoff) with absolute page indexes."""
    layout = plan_stage(fonts, reqs)
    boxes: list[GenBox] = []
    signoff = None
    for k, page_rows in enumerate(layout.pages):
        page = doc.new_page(insert_at + k, width=PAGE_W, height=PAGE_H)
        y = col_top = TOP
        _hline(page, X_LEFT, X_RIGHT, TOP)
        _text(page, (NUM_X, y + NUM_BASELINE), str(stage), fonts.narrow_bold, NUM_SIZE, GREEN)
        if k > 0:
            _text(page, (NUM_X - 2, y + NUM_BASELINE + 13), "continued", fonts.narrow, 8, GREEN)
        last = k == len(layout.pages) - 1
        for i in page_rows:
            req, lines, row_h = layout.rows[i]
            bbox = draw_box(page, y)
            for j, line in enumerate(lines):
                _text(page, (TEXT_X, y + FIRST_BASELINE * layout.size / TEXT_SIZE + j * layout.line_h),
                      line, fonts.body, layout.size)
            y += row_h
            if not (last and i == page_rows[-1]):
                _hline(page, X_TEXT_R + 0.5, X_RIGHT, y)
            boxes.append(GenBox(insert_at + k, tuple(bbox), req, section, stage))
        _vline(page, X_TEXT_R, col_top, y)
        if not last:
            _vline(page, X_RIGHT, col_top, y)
            _hline(page, X_LEFT, X_RIGHT + RULE_W, y)   # close the table on this page
            continue
        # Sign-off row
        _vline(page, X_RIGHT, col_top, y + SIGNOFF_H)
        _hline(page, X_LEFT, X_RIGHT, y)
        _vline(page, X_LEFT - 0.24, y, y + SIGNOFF_H)
        _hline(page, X_LEFT, X_RIGHT + RULE_W, y + SIGNOFF_H)
        base = y + SIGNOFF_BASELINE
        _text(page, (SIGNOFF_X, base), SIGNOFF_TEXT, fonts.narrow, SIGNOFF_SIZE)
        w = fonts.measure(fonts.narrow, SIGNOFF_TEXT, SIGNOFF_SIZE)
        signoff = GenSignoff(
            insert_at + k,
            (SIGNOFF_X, base - SIGNOFF_SIZE * 0.94, SIGNOFF_X + w, base + SIGNOFF_SIZE * 0.28),
            SIGNOFF_TEXT, section, stage,
        )
    return len(layout.pages), boxes, signoff


def redraw_overview(doc: fitz.Document, max_stage: int, fonts: Fonts) -> list[tuple]:
    """Redraw the page-3 OAS grid with stage columns 1..max_stage.

    Returns [(section, stage, cell_rect)] so callers can tick earned stages.
    """
    page = doc[OVERVIEW_PAGE]
    sections = list(SKILL_FIRST_PAGE)
    grid_bottom = GRID_HEADER_BOTTOM + GRID_ROW_H * len(sections)
    area = fitz.Rect(X_LEFT - 2, GRID_TOP - 2, X_RIGHT + 3, grid_bottom + 2)
    page.add_redact_annot(area)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                          graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                          text=fitz.PDF_REDACT_TEXT_REMOVE)

    col_w = (X_RIGHT - GRID_LABEL_R) / max_stage
    xs = [GRID_LABEL_R + i * col_w for i in range(max_stage + 1)]
    ys = [GRID_TOP, GRID_HEADER_BOTTOM] + [GRID_HEADER_BOTTOM + GRID_ROW_H * (i + 1)
                                           for i in range(len(sections))]
    for y in ys:
        _hline(page, X_LEFT, X_RIGHT, y)
    for x in [X_LEFT] + xs:
        _vline(page, x, GRID_TOP, grid_bottom)

    size = 9.96
    for s in range(1, max_stage + 1):
        label = str(s)
        w = fonts.measure(fonts.bold, label, size)
        cx = (xs[s - 1] + xs[s]) / 2
        _text(page, (cx - w / 2, GRID_TOP + 9.6), label, fonts.bold, size)
    cells = []
    for i, sec in enumerate(sections):
        top = GRID_HEADER_BOTTOM + GRID_ROW_H * i
        w = fonts.measure(fonts.body, sec, size)
        _text(page, (GRID_LABEL_R - 3.3 - w, top + 21.5), sec, fonts.body, size)
        for s in range(1, max_stage + 1):
            cells.append((sec, s, fitz.Rect(xs[s - 1], top, xs[s], top + GRID_ROW_H)))
    return cells


def load_requirements(path: Path | None = REQS_JSON) -> dict[str, dict[int, list[str]]]:
    if path is None or not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {sec: {int(k): v for k, v in stages.items()} for sec, stages in raw.items()}


def build_template(pdf_path: Path, max_stage: int, requirements=None):
    """Open the template and add stages TEMPLATE_MAX_STAGE+1..max_stage.

    Returns (doc, gen_boxes, gen_signoffs, overview_cells, warnings).
    """
    requirements = load_requirements() if requirements is None else requirements
    fonts = Fonts.detect()
    doc = fitz.open(pdf_path)
    warnings: list[str] = []
    if fonts.is_fallback:
        warnings.append("Aptos font not found (install Microsoft Office fonts); "
                        "extra stages use Helvetica")
    gen_boxes: list[GenBox] = []
    gen_signoffs: list[GenSignoff] = []

    cells = redraw_overview(doc, max_stage, fonts) if max_stage > TEMPLATE_MAX_STAGE else []

    # Insert from the last skill backwards so earlier page indexes stay valid,
    # then shift the recorded indexes of later skills afterwards.
    sections = list(SKILL_FIRST_PAGE)
    next_first = {sec: (SKILL_FIRST_PAGE[sections[i + 1]] if i + 1 < len(sections)
                        else PAB_FIRST_PAGE) for i, sec in enumerate(sections)}
    added_after: dict[str, int] = {}
    per_section: dict[str, tuple[list, list]] = {}
    for sec in reversed(sections):
        insert_at = next_first[sec]
        boxes, signs, added = [], [], 0
        for stage in range(TEMPLATE_MAX_STAGE + 1, max_stage + 1):
            reqs = requirements.get(sec, {}).get(stage)
            if not reqs:
                warnings.append(f"No requirement text for {sec} {stage}; page skipped")
                continue
            n, b, s = _draw_stage(doc, insert_at + added, sec, stage, reqs, fonts)
            added += n
            boxes += b
            signs.append(s)
        added_after[sec] = added
        per_section[sec] = (boxes, signs)

    # Fix page indexes: pages inserted for earlier skills push later ones down.
    shift = 0
    for sec in sections:
        boxes, signs = per_section[sec]
        for item in boxes + signs:
            item.page_index += shift
        gen_boxes += boxes
        gen_signoffs += signs
        shift += added_after[sec]

    return doc, gen_boxes, gen_signoffs, cells, warnings


def pad_to_booklet(doc: fitz.Document) -> int:
    """Pad with blank pages to a multiple of 4 (booklet printing)."""
    added = 0
    while len(doc) % 4:
        doc.new_page(width=PAGE_W, height=PAGE_H)
        added += 1
    return added


def parse_stages(s: str) -> tuple[int, int]:
    a, _, b = s.partition("-")
    lo, hi = int(a), int(b or a)
    if not (1 <= lo <= hi <= 9) or hi < TEMPLATE_MAX_STAGE:
        raise SystemExit(f"bad stage range {s!r} (expected 1-3 up to 1-9, e.g. 1-4)")
    if lo != 1:
        print(f"note: the Cub template always includes stages 1-{TEMPLATE_MAX_STAGE}; "
              f"printing stages 1-{hi}")
    return 1, hi


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stages", default="1-4")
    ap.add_argument("--out", default=str(OUT_DIR / "blank-passport.pdf"))
    a = ap.parse_args()
    lo, hi = parse_stages(a.stages)
    from build_data import latest_data_dir
    doc, boxes, signs, cells, warns = build_template(
        TEMPLATE_PDF, hi, load_requirements(latest_data_dir() / "oas_requirements.json"))
    pad_to_booklet(doc)
    Path(a.out).parent.mkdir(exist_ok=True)
    doc.save(a.out, garbage=3, deflate=True)
    for w in warns:
        print("WARN:", w)
    print(f"{len(boxes)} new checkboxes, {len(signs)} new sign-off lines, "
          f"{len(doc)} pages -> {a.out}")
