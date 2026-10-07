"""template_ext.py: stage 4+ pages in the template's style."""
import json

import pytest

import template_ext as t
from paths import TEMPLATE_PDF


@pytest.fixture(scope="module")
def reqs(data_dir):
    return t.load_requirements(data_dir / "oas_requirements.json")


def test_parse_stages():
    assert t.parse_stages("1-4") == (1, 4)
    assert t.parse_stages("4") == (1, 4)
    assert t.parse_stages("3-6") == (1, 6)   # Cub template always starts at 1
    for bad in ("1-2", "1-10", "0-4", "x"):
        with pytest.raises((SystemExit, ValueError)):
            t.parse_stages(bad)


def test_stages_1_to_3_leave_template_untouched():
    doc, boxes, signs, cells, _ = t.build_template(TEMPLATE_PDF, 3, {})
    assert len(doc) == 51 and not boxes and not signs and not cells


def test_stage_4_pages_added_for_every_skill(reqs):
    doc, boxes, signs, cells, warns = t.build_template(TEMPLATE_PDF, 4, reqs)
    assert not [w for w in warns if "No requirement text" in w]
    assert sorted(s.section for s in signs) == sorted(t.SKILL_FIRST_PAGE)
    assert len(boxes) == sum(len(reqs[s][4]) for s in t.SKILL_FIRST_PAGE)
    assert len(cells) == 9 * 4
    for b in boxes:
        assert b.stage == 4 and 0 <= b.page_index < len(doc)
        assert doc[b.page_index].get_text().lstrip().startswith("4")
    # Each skill's stage 4 comes before the next skill's heading page.
    order = [s.page_index for s in sorted(signs, key=lambda s: list(t.SKILL_FIRST_PAGE).index(s.section))]
    assert order == sorted(order)


def test_missing_requirement_text_skips_page_with_warning():
    _, boxes, signs, _, warns = t.build_template(TEMPLATE_PDF, 4, {})
    assert not boxes and not signs
    assert sum("No requirement text" in w for w in warns) == 9


def test_layout_keeps_12pt_and_balances_pages(reqs):
    fonts = t.Fonts.detect()
    for skill in t.SKILL_FIRST_PAGE:
        for stage in (4, 5):
            layout = t.plan_stage(fonts, reqs[skill][stage])
            assert layout.size == t.TEXT_SIZE
            heights = []
            for k, page in enumerate(layout.pages):
                h = sum(layout.rows[i][2] for i in page)
                if k == len(layout.pages) - 1:
                    h += t.SIGNOFF_H
                assert h <= t.PAGE_AVAIL + 0.01, (skill, stage)
                heights.append(h)
            assert sum(map(len, layout.pages)) == len(reqs[skill][stage])
            if len(heights) > 1:   # no near-empty spill-over page
                assert min(heights) >= 0.4 * max(heights), (skill, stage, heights)


def test_long_stage_splits_and_marks_continued(reqs):
    fonts = t.Fonts.detect()
    many = reqs["Sailing Skills"][4] * 2
    layout = t.plan_stage(fonts, many)
    assert len(layout.pages) >= 2
    doc, *_ = t.build_template(TEMPLATE_PDF, 4, {"Sailing Skills": {4: many}})
    assert sum("continued" in p.get_text() for p in doc) == len(layout.pages) - 1


def test_works_without_aptos_font(monkeypatch, reqs):
    monkeypatch.setattr(t, "_find_font", lambda name: None)
    fonts = t.Fonts.detect()
    assert fonts.is_fallback
    doc, boxes, *_ , warns = t.build_template(TEMPLATE_PDF, 4, reqs)
    assert boxes and any("Aptos" in w for w in warns)
