"""print_layout.py: 4 pages per sheet, cut-and-stack order, name footers."""
import pymupdf

import print_layout


def test_print_file_cut_and_stack_order(out_dir, fill_log):
    pdf = out_dir / fill_log["Alex Tester"]["pdf"]
    with pymupdf.open(pdf) as d:
        pages = len(d)
    printed = out_dir / "print 4-up" / f"{pdf.stem} - print 4-up.pdf"
    with pymupdf.open(printed) as sheets_doc:
        sheets = len(sheets_doc)
        total = sheets * 4
        assert total >= pages and total - pages < 4          # padded to a multiple of 4
        for s, sheet in enumerate(sheets_doc):
            text = sheet.get_text()
            for k in range(4):                                # pile k holds pages k*sheets+1...
                assert f"Alex Tester  -  page {k * sheets + s + 1} of {total}" in text
            assert sheet.rect.width == 612 and sheet.rect.height == 792


def test_all_cubs_file_combines_every_cub(out_dir, fill_log):
    with pymupdf.open(out_dir / "print 4-up" / "ALL CUBS - print 4-up.pdf") as d:
        assert len(d) == sum(log["print_sheets"] for log in fill_log.values())


def test_pad_to_multiple():
    doc = pymupdf.open()
    for _ in range(5):
        doc.new_page(width=396, height=612)
    assert print_layout.pad_to_multiple(doc) == 3 and len(doc) == 8
