"""Lay a passport out 4 pages per letter sheet for single-sided printing + a
paper cutter ("cut and stack").

Page order is arranged so you can cut the whole stack of one Cub's sheets at
once along the guides, then stack the four piles in order:

    1. top-left pile   2. top-right pile   3. bottom-left pile   4. bottom-right pile

(each pile on top of the next) and the passport comes out in page order.

Usage:
    python print_layout.py "<passport>.pdf"   # writes "<passport> - print 4-up.pdf"
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf as fitz

SHEET_W, SHEET_H = 612, 792          # US letter, portrait
CELL_W, CELL_H = SHEET_W / 2, SHEET_H / 2
MARGIN = 12                          # keeps content clear of the cut line
FOOTER_H = 12                        # room under each page for "Name - page n of N"
GUIDE = (0.6, 0.6, 0.6)
PAGES_PER_SHEET = 4


def pad_to_multiple(doc: fitz.Document, n: int = PAGES_PER_SHEET) -> int:
    """Add blank pages at the end so the page count is a multiple of n."""
    added = 0
    w, h = doc[0].rect.width, doc[0].rect.height
    while len(doc) % n:
        doc.new_page(width=w, height=h)
        added += 1
    return added


def _cells():
    """Top-left, top-right, bottom-left, bottom-right cell rects."""
    for row in range(2):
        for col in range(2):
            x0, y0 = col * CELL_W, row * CELL_H
            yield fitz.Rect(x0 + MARGIN, y0 + MARGIN, x0 + CELL_W - MARGIN,
                            y0 + CELL_H - MARGIN - FOOTER_H)


def _guides(page: fitz.Page, label: str) -> None:
    # Dashed cut lines through the middle, plus small labels in the margin.
    page.draw_line((CELL_W, 0), (CELL_W, SHEET_H), color=GUIDE, width=0.4, dashes="[3 3] 0")
    page.draw_line((0, CELL_H), (SHEET_W, CELL_H), color=GUIDE, width=0.4, dashes="[3 3] 0")
    page.insert_text((MARGIN, SHEET_H - 3), label, fontsize=6, color=GUIDE)


def _footer(page: fitz.Page, cell: fitz.Rect, text: str) -> None:
    """Small centred label under a page so cut pieces stay identifiable."""
    size = 7
    w = fitz.get_text_length(text, fontname="helv", fontsize=size)
    cx = (cell.x0 + cell.x1) / 2
    page.insert_text((cx - w / 2, cell.y1 + FOOTER_H - 2), text, fontsize=size,
                     fontname="helv", color=(0.35, 0.35, 0.35))


def make_4up(src: Path, out: Path, title: str = "", name: str = "") -> int:
    """Write the cut-and-stack 4-up PDF. Returns the number of sheets."""
    doc = fitz.open(src)
    pad_to_multiple(doc)
    sheets = len(doc) // PAGES_PER_SHEET
    out_doc = fitz.open()
    for s in range(sheets):
        sheet = out_doc.new_page(width=SHEET_W, height=SHEET_H)
        # Pile k (cell k) holds pages k*sheets .. (k+1)*sheets-1, one per sheet.
        for k, cell in enumerate(_cells()):
            src_index = k * sheets + s
            # Passport pages are tall, so they always fill the cell's height.
            sheet.show_pdf_page(cell, doc, src_index, keep_proportion=True)
            if name:
                _footer(sheet, cell, f"{name}  -  page {src_index + 1} of {len(doc)}")
        _guides(sheet, f"{title}  sheet {s + 1}/{sheets}  - cut on the dashed lines, "
                       "stack piles TL, TR, BL, BR")
    out_doc.save(out, garbage=3, deflate=True)
    out_doc.close()
    doc.close()
    return sheets


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        p = Path(arg)
        o = p.with_name(p.stem + " - print 4-up.pdf")
        n = make_4up(p, o, p.stem, p.stem.split(" - ")[0])
        print(f"{o} ({n} sheets)")


# ------------------------------------------------------------------------
# Folded booklet (saddle stitch): two full-size passport pages per side of a
# landscape letter sheet. Print double-sided, flip on the SHORT edge, fold the
# stack in half and staple on the fold. Passport pages are exactly half a
# letter sheet, so nothing is scaled.
# ------------------------------------------------------------------------
LANDSCAPE_W, LANDSCAPE_H = SHEET_H, SHEET_W   # 792 x 612


def booklet_order(n: int) -> list[tuple[int, int]]:
    """(left, right) page indexes for each side, in print order:
    sheet 1 front, sheet 1 back, sheet 2 front, ... (n must be a multiple of 4)."""
    sides = []
    for i in range(n // 4):
        sides.append((n - 1 - 2 * i, 2 * i))          # front
        sides.append((2 * i + 1, n - 2 - 2 * i))      # back
    return sides


def make_booklet(src: Path, out: Path, name: str = "") -> int:
    """Write the booklet PDF (fronts and backs alternate). Returns sheets of paper."""
    doc = fitz.open(src)
    pad_to_multiple(doc)
    out_doc = fitz.open()
    half = LANDSCAPE_W / 2
    for k, (left, right) in enumerate(booklet_order(len(doc))):
        side = out_doc.new_page(width=LANDSCAPE_W, height=LANDSCAPE_H)
        side.show_pdf_page(fitz.Rect(0, 0, half, LANDSCAPE_H), doc, left)
        side.show_pdf_page(fitz.Rect(half, 0, LANDSCAPE_W, LANDSCAPE_H), doc, right)
        if name and k % 2 == 0:   # tiny label on the fold, fronts only, to keep stacks sorted
            label = f"{name} - sheet {k // 2 + 1}/{len(doc) // 4}"
            w = fitz.get_text_length(label, fontname="helv", fontsize=5)
            side.insert_text((half - w / 2, LANDSCAPE_H - 2), label, fontsize=5,
                             fontname="helv", color=(0.55, 0.55, 0.55))
    out_doc.save(out, garbage=3, deflate=True)
    sheets = len(out_doc) // 2
    out_doc.close()
    doc.close()
    return sheets


# ------------------------------------------------------------------------
# Full size: one passport page per letter sheet, centred, actual size, with
# the Cub's name and page number underneath. Double-sided printers flip on
# the LONG edge.
# ------------------------------------------------------------------------
def make_fullsize(src: Path, out: Path, name: str = "") -> int:
    """Write the full-size PDF. Returns the number of printed sides."""
    doc = fitz.open(src)
    if len(doc) % 2:               # even count so double-sided pages pair up
        pad_to_multiple(doc, 2)
    out_doc = fitz.open()
    w, h = doc[0].rect.width, doc[0].rect.height
    x0, y0 = (SHEET_W - w) / 2, (SHEET_H - h) / 2
    for i in range(len(doc)):
        page = out_doc.new_page(width=SHEET_W, height=SHEET_H)
        page.show_pdf_page(fitz.Rect(x0, y0, x0 + w, y0 + h), doc, i)
        if name:
            _footer(page, fitz.Rect(x0, y0, x0 + w, y0 + h + 8),
                    f"{name}  -  page {i + 1} of {len(doc)}")
    out_doc.save(out, garbage=3, deflate=True)
    sides = len(out_doc)
    out_doc.close()
    doc.close()
    return sides


LAYOUTS = {
    # key: (folder name, maker, double-sided flip edge or None if single-sided only)
    "4up": ("print 4-up", make_4up, None),
    "booklet": ("print booklet", make_booklet, "short"),
    "fullsize": ("print full size", make_fullsize, "long"),
}
