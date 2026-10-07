"""build_data.py: ScoutsTracker dump -> CSVs the filler reads."""
import csv
import json

import build_data
from conftest import CUBS


def rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_roster_is_active_cubs_sorted(data_dir):
    assert json.loads((data_dir / "roster.json").read_text()) == sorted(CUBS)


def test_signoffs_have_dates_and_clean_scouter_names(data_dir):
    so = {(r["member"], r["badge"]): r for r in rows(data_dir / "stage_signoffs.csv")}
    assert so[("Alex Tester", "Camping Skills 1")]["scouter"] == "Test Scouter"  # "(inactive)" dropped
    assert so[("Alex Tester", "Runner")]["scouter"] == "Unknown"                 # "Cub Pack" isn't a person
    blair4 = so[("Blair Example", "Aquatic Skills 4")]
    assert blair4["date"] == "2025-05-14" and blair4["scouter"] == "Unknown"
    assert not any(m == "Casey Sample" for m, _ in so)


def tracking(data_dir):
    with (data_dir / "tracking.csv").open(newline="", encoding="utf-8") as f:
        grid = list(csv.reader(f))
    names = grid[0][2:]
    out, section = {}, None
    for r in grid[1:]:
        if r[0].startswith("▼"):
            section = r[0][2:]
        else:
            out[(section, r[0])] = dict(zip(names, r[2:]))
    return grid[0], out


def test_tracking_grid_layout_and_values(data_dir):
    header, t = tracking(data_dir)
    assert header[:2] == ["⤨", ""] and header[2:] == sorted(CUBS)
    assert t[("Camping Skills 4", "#4.1")]["Alex Tester"] == "✓"
    assert t[("Camping Skills 4", "#4.12")]["Alex Tester"] == "9"       # tally shown as a count
    assert t[("Trail Skills 3", "#3.12")]["Alex Tester"] == "5"         # sub-req tally rolled up to parent
    assert t[("Aquatic Skills 5", "#5.1")]["Blair Example"] == "✓"
    assert all(v == "" for k, col in t.items() for n, v in col.items() if n == "Casey Sample")


def test_oas_requirement_text_is_clean_and_complete(data_dir):
    reqs = json.loads((data_dir / "oas_requirements.json").read_text(encoding="utf-8"))
    assert len(reqs) == 9
    for skill, stages in reqs.items():
        assert {"1", "2", "3", "4"} <= set(stages), skill
        for texts in stages.values():
            for t in texts:
                assert t and "<" not in t and "**" not in t and "[[" not in t


def test_cub_stats_units(data_dir):
    s = {r["name"]: r for r in rows(data_dir / "cub_stats.csv")}
    assert s["Alex Tester"]["Camps"] == "9n"
    assert s["Alex Tester"]["Service"] == "6h"
    assert s["Alex Tester"]["Hikes (by km)"] == "4km"
    assert s["Alex Tester"]["oas_stages"] == "2"
    assert s["Blair Example"]["oas_stages"] == "4"
    assert s["Casey Sample"]["Camps"] == ""


def test_clean_text():
    raw = "I have spent **12** nights. <span>(</span>)<detail>hidden\nmore</detail> See [[https://x.org]]"
    assert build_data.clean_text(raw) == "I have spent 12 nights. See https://x.org"


def test_clean_scouter():
    assert build_data.clean_scouter("Jane Doe (GC)") == "Jane Doe"
    assert build_data.clean_scouter("Jane Doe (inactive)") == "Jane Doe"
    for unknown in ("", "Unknown", "Cub Pack"):
        assert build_data.clean_scouter(unknown) == "Unknown"


def test_requirement_sort_is_natural():
    ids = ["10", "2", "5b", "1", "5a", "5"]
    assert sorted(ids, key=build_data.req_sort_key) == ["1", "2", "5", "5a", "5b", "10"]
