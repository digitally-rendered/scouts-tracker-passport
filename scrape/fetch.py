"""Fetch current Cub data from ScoutsTracker into data/<date>/raw/scoutstracker.json.

Uses the session saved by scrape/login.py. ScoutsTracker keeps a full offline
copy of the pack's records in the browser (IndexedDB "ScoutsTracker"); once
the app has connected and synced we read that directly, plus a couple of the
app's own helpers (Scouter names, event rollups). No report pages are scraped.

Usage:
    python scrape/fetch.py              # writes data/<today>/raw/scoutstracker.json
    python scrape/fetch.py --show       # same, with the browser visible
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from paths import DATA_DIR  # noqa: E402
from scrape.session import is_logged_in, open_tracker  # noqa: E402

# Badges we keep requirement detail for: OAS skills + Cub awards in the passport.
BADGE_PATTERN = (r"^(aquatic|camping|emergency|paddling|sailing|scoutcraft|trail|"
                 r"vertical|winter)skills\d$|^(runner|tracker|howler|seeoneeaward)$")

EXTRACT_JS = """
async (badgePattern) => {
  const badgeRe = new RegExp(badgePattern);
  const db = await new Promise((res, rej) => {
    const r = indexedDB.open("ScoutsTracker");
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  });
  const getAll = (s) => new Promise(r => {
    const q = db.transaction(s, "readonly").objectStore(s).getAll();
    q.onsuccess = () => r(q.result);
  });
  const acct = (rows) => (rows.find(x => x.accountkey) || {data: {}}).data;

  const members = acct(await getAll("db-members"));
  const reqsAll = acct(await getAll("db-requirements"));
  const comp = acct(await getAll("db-completedrequirements"));
  const awarded = acct(await getAll("db-awarded"));
  const tallies = acct(await getAll("db-tallies"));

  // Active Cubs only (role 10 = youth, status 1 = active, no exit date).
  const cubs = Object.values(members)
    .filter(m => m.role === 10 && m.status === 1 && !(m.exitdate > 0))
    .map(m => ({memberid: m.memberid, personid: m.personid,
                name: `${m.firstname || ""} ${m.lastname || ""}`.trim()}));

  const requirements = {};
  for (const [id, r] of Object.entries(reqsAll)) {
    if (!badgeRe.test(r.badgeid || "")) continue;
    requirements[id] = {badgeid: r.badgeid, requirement: r.requirement || id.split(".").slice(1).join("."),
                        description: r.description || "", subreqlogic: r.subreqlogic || "",
                        autocompletion: r.autocompletion || ""};
  }

  const byIds = new Set();
  const out = {cubs: [], requirements, scouters: {}};
  for (const c of cubs) {
    const p = String(c.personid);
    const completed = {};
    for (const [rid, v] of Object.entries(comp[p] || {}))
      if (requirements[rid]) { completed[rid] = {when: v.when, by: v.by}; byIds.add(v.by); }
    const aw = {};
    for (const [bid, v] of Object.entries(awarded[p] || {})) { aw[bid] = {when: v.when, by: v.by}; byIds.add(v.by); }
    const tal = {};
    for (const rid of Object.keys(tallies[p] || {})) {
      if (!requirements[rid]) continue;
      try { tal[rid] = getTallyCount_person(c.personid, rid); } catch (e) { tal[rid] = null; }
    }
    let rollups = {};
    try {
      for (const [k, v] of Object.entries(getEventRollups(c.memberid, false, false, -1)))
        if (!k.includes(".")) rollups[k] = Number(v);
    } catch (e) { rollups = {error: String(e)}; }
    out.cubs.push({...c, completed, awarded: aw, tallies: tal, rollups});
  }
  for (const id of byIds) {
    try { out.scouters[id] = getLoginName(Number(id)); } catch (e) { out.scouters[id] = "Unknown"; }
  }
  return out;
}
"""


def choose_cub_scouter_account(page) -> None:
    """In the 'Welcome back - Connect to' picker, pick the Cubs Scouter account
    (people with several accounts may default to Group or Parent)."""
    picked = page.evaluate("""() => {
        for (const sel of document.querySelectorAll("select")) {
            const opt = [...sel.options].find(o => /cubs/i.test(o.text) && /scouter/i.test(o.text));
            if (opt && sel.offsetParent !== null) {
                sel.value = opt.value;
                sel.dispatchEvent(new Event("change", {bubbles: true}));
                return opt.text;
            }
        }
        return null;
    }""")
    if picked:
        print(f"Connecting as: {picked}")


def connect(page, timeout_s: int = 60) -> None:
    """Get past the 'Welcome back' account picker (keeps the preselected
    Scouter account) and wait for the app to finish loading."""
    for _ in range(timeout_s):
        if is_logged_in(page):
            break
        btn = page.get_by_text("Connect", exact=True)
        if btn.count() and btn.first.is_visible():
            choose_cub_scouter_account(page)
            btn.first.click()
        pin = page.get_by_text("PIN", exact=False)
        if pin.count() and pin.first.is_visible():
            raise SystemExit("ScoutsTracker is asking for your security PIN. "
                             "Run: python scrape/login.py  and sign in again.")
        page.wait_for_timeout(1000)
    else:
        raise SystemExit("Not logged into ScoutsTracker. Run: python scrape/login.py")
    page.wait_for_timeout(8000)  # let the background sync pull the latest records


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch Cub data from ScoutsTracker")
    ap.add_argument("--show", action="store_true", help="show the browser window")
    ap.add_argument("--out", default=str(DATA_DIR / date.today().isoformat()))
    a = ap.parse_args()

    with open_tracker(headless=not a.show) as page:
        connect(page)
        data = page.evaluate(EXTRACT_JS, BADGE_PATTERN)

    data["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    raw_dir = Path(a.out) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = raw_dir / "scoutstracker.json"
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Fetched {len(data['cubs'])} active Cubs, "
          f"{len(data['requirements'])} requirements -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
