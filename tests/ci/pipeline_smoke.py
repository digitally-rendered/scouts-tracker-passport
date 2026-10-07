"""CI smoke test for an INSTALLED copy: run the real scripts on the synthetic
fixture (build -> fill -> audit) exactly as a leader's run would, minus the
ScoutsTracker fetch. Usage: python tests/ci/pipeline_smoke.py <installed tool dir>"""
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

tool = Path(sys.argv[1]).resolve()
ws = Path(os.environ["PASSPORT_DATA"])
day = date.today().isoformat()
raw = ws / "data" / day / "raw"
raw.mkdir(parents=True, exist_ok=True)
fixture = Path(__file__).resolve().parent.parent / "fixtures" / "scoutstracker.json"
data = json.loads(fixture.read_text(encoding="utf-8"))
data["fetched_at"] = f"{day}T12:00:00"
(raw / "scoutstracker.json").write_text(json.dumps(data), encoding="utf-8")

# Same command the launchers use, minus the fetch and opening windows.
rc = subprocess.call(["uv", "run", "python", "passport.py", "run", "--stages", "1-4",
                      "--no-fetch", "--no-open"], cwd=tool)
out = ws / "out" / day
print("files:", sorted(p.name for p in out.iterdir()))
assert rc == 0, f"passport.py run exited {rc}"
assert (out / "audit.html").exists()
assert len(list((out / "print 4-up").glob("*.pdf"))) == 4   # 3 Cubs + ALL CUBS
shutil.rmtree(ws, ignore_errors=True)
print("smoke test passed")
