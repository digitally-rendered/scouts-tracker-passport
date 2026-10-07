"""Simple point-and-click page for making passports.

Starts a small web server on THIS computer only (127.0.0.1) and opens it in
your browser. Every request must carry a secret key that is part of the page
address, so other websites can't trigger anything. Nothing is sent anywhere;
the page just runs the same scripts as the launchers.

    python ui.py            # or: python passport.py ui
"""
from __future__ import annotations

import csv
import json
import secrets
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from passport import open_path  # noqa: E402
from paths import DATA_DIR, OUT_DIR, REPO_URL, WORKSPACE  # noqa: E402

MAX_LOG_LINES = 5000


class Job:
    """One background task at a time (make passports, sign in, check setup)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.name = ""
        self.lines: list[str] = []
        self.running = False
        self.exit_code: int | None = None
        self.started = ""

    def start(self, name: str, args: list[str]) -> bool:
        with self.lock:
            if self.running:
                return False
            self.name, self.lines, self.running, self.exit_code = name, [], True, None
            self.started = datetime.now().strftime("%H:%M")
        threading.Thread(target=self._run, args=(args,), daemon=True).start()
        return True

    def _run(self, args: list[str]) -> None:
        try:
            proc = subprocess.Popen(
                [sys.executable, *args], cwd=HERE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                encoding="utf-8", errors="replace", env={**__import__("os").environ, "PYTHONUTF8": "1"})
            for line in proc.stdout:
                with self.lock:
                    self.lines.append(line.rstrip("\n"))
                    del self.lines[:-MAX_LOG_LINES]
            code = proc.wait()
        except Exception as e:  # noqa: BLE001
            with self.lock:
                self.lines.append(f"Couldn't start: {e}")
            code = 1
        with self.lock:
            self.running, self.exit_code = False, code

    def snapshot(self, since: int) -> dict:
        with self.lock:
            return {"name": self.name, "running": self.running, "exit_code": self.exit_code,
                    "started": self.started, "total": len(self.lines),
                    "lines": self.lines[since:]}


def latest_out() -> Path | None:
    dirs = sorted(p for p in OUT_DIR.glob("20*-*-*") if (p / "fill_log.json").exists())
    return dirs[-1] if dirs else None


def status() -> dict:
    data_dirs = sorted(p.name for p in DATA_DIR.glob("20*-*-*") if (p / "raw").is_dir())
    out = latest_out()
    result = None
    if out:
        counts = {"ERROR": 0, "WARN": 0, "INFO": 0}
        if (out / "audit.csv").exists():
            with (out / "audit.csv").open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    counts[row["level"]] = counts.get(row["level"], 0) + 1
        log = json.loads((out / "fill_log.json").read_text(encoding="utf-8")).get("cubs", {})
        result = {"date": out.name, "cubs": len(log), "counts": counts,
                  "has_audit": (out / "audit.html").exists(),
                  "has_print": (out / "print 4-up" / "ALL CUBS - print 4-up.pdf").exists()}
    profile = WORKSPACE / "browser-profile"
    return {
        "signed_in_before": profile.exists() and any(profile.iterdir()),
        "data_date": data_dirs[-1] if data_dirs else None,
        "result": result,
        "workspace": str(WORKSPACE),
        "help_url": REPO_URL + "/blob/main/docs/TROUBLESHOOTING.md",
    }


def make_handler(token: str, job: Job, stop):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the terminal quiet
            pass

        def _send(self, code: int, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else (
                json.dumps(body) if ctype == "application/json" else body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                return False                       # blocks DNS-rebinding tricks
            return secrets.compare_digest(self.headers.get("X-Token", ""), token)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                if parse_qs(url.query).get("t", [""])[0] != token:
                    return self._send(403, "Open the page from the Scouts Passports shortcut.", "text/plain")
                return self._send(200, PAGE.replace("__TOKEN__", token), "text/html")
            if not self._authorized():
                return self._send(403, {"error": "forbidden"})
            if url.path == "/api/status":
                return self._send(200, status())
            if url.path == "/api/job":
                since = int(parse_qs(url.query).get("since", ["0"])[0] or 0)
                return self._send(200, job.snapshot(since))
            if url.path == "/api/doctor":
                r = subprocess.run([sys.executable, "doctor.py", "--json"], cwd=HERE,
                                   capture_output=True, text=True, encoding="utf-8")
                try:
                    return self._send(200, json.loads(r.stdout))
                except json.JSONDecodeError:
                    return self._send(500, {"error": r.stderr[-2000:]})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._authorized():
                return self._send(403, {"error": "forbidden"})
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, {"error": "bad request"})
            path = urlparse(self.path).path
            if path == "/api/run":
                top = int(body.get("stage", 4))
                if not 3 <= top <= 9:
                    return self._send(400, {"error": "stage must be 3-9"})
                args = ["passport.py", "run", "--stages", f"1-{top}", "--no-open"]
                if not body.get("fetch", True):
                    args.append("--no-fetch")
                ok = job.start("Making passports", args)
            elif path == "/api/login":
                ok = job.start("Signing in", ["passport.py", "login"])
            elif path == "/api/check":
                ok = job.start("Checking setup", ["doctor.py", "--online"])
            elif path == "/api/open":
                out = latest_out()
                targets = {"data": WORKSPACE}
                if out:
                    targets |= {"folder": out, "audit": out / "audit.html",
                                "print": out / "print 4-up" / "ALL CUBS - print 4-up.pdf",
                                "print_folder": out / "print 4-up"}
                target = targets.get(body.get("what"))
                if not target or not target.exists():
                    return self._send(404, {"error": "not made yet"})
                open_path(target)
                return self._send(200, {"ok": True})
            elif path == "/api/quit":
                self._send(200, {"ok": True})
                threading.Thread(target=stop, daemon=True).start()
                return
            else:
                return self._send(404, {"error": "not found"})
            return self._send(200 if ok else 409, {"ok": ok, "error": None if ok else "busy"})

    return Handler


def make_server(port: int = 0):
    """Create the server (not started). Returns (server, url, token, job)."""
    token = secrets.token_urlsafe(24)
    job = Job()
    holder = {}
    handler = make_handler(token, job, lambda: holder["server"].shutdown())
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    holder["server"] = server
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={token}"
    return server, url, token, job


def main() -> int:
    server, url, _, _ = make_server()
    print("Scouts Passports is open in your browser.")
    print(f"If it didn't open, copy this into your browser:\n  {url}")
    print("\nKeep this window open while you use it. Click 'Close' on the page (or close this window) when done.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    return 0


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scouts Passports</title>
<style>
:root{--bg:#f6f7f2;--card:#fff;--ink:#1f2a1a;--muted:#5d6b55;--green:#5a8f29;--green-d:#45701e;
--line:#dfe4d6;--err:#c62828;--warn:#b26a00;--ok:#2e7d32;--code:#f1f3ec}
@media (prefers-color-scheme:dark){:root{--bg:#141811;--card:#1d2318;--ink:#e8eee1;--muted:#a3b097;
--green:#7cb342;--green-d:#689f38;--line:#323b2a;--code:#232a1d}}
*{box-sizing:border-box}body{margin:0;font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;background:var(--bg);color:var(--ink)}
main{max-width:760px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:28px;margin:0 0 4px}h2{font-size:18px;margin:0 0 12px}
.sub{color:var(--muted);margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-bottom:16px}
.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
button{font:inherit;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);padding:9px 14px;cursor:pointer}
button:hover{border-color:var(--green)}button:disabled{opacity:.5;cursor:default}
button.primary{background:var(--green);border-color:var(--green);color:#fff;font-size:18px;padding:12px 22px;font-weight:600}
button.primary:hover{background:var(--green-d)}
select{font:inherit;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.status{display:grid;grid-template-columns:auto 1fr;gap:6px 12px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
.ok{background:var(--ok)}.warn{background:var(--warn)}.err{background:var(--err)}
.counts{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 14px}
.pill{border-radius:999px;padding:4px 12px;font-weight:600;border:1px solid var(--line)}
.pill.e{color:var(--err)}.pill.w{color:var(--warn)}.pill.i{color:var(--muted)}
.msg{padding:10px 12px;border-radius:8px;margin:12px 0 0;display:none}
.msg.show{display:block}.msg.bad{background:#fdecea;color:#7f1d1d}.msg.good{background:#e8f5e9;color:#14532d}.msg.note{background:#fff4e0;color:#5c3b00}
pre{background:var(--code);border-radius:8px;padding:10px;max-height:300px;overflow:auto;font-size:12px;white-space:pre-wrap;margin:10px 0 0}
details summary{cursor:pointer;color:var(--muted)}
ul.checks{list-style:none;padding:0;margin:10px 0 0}ul.checks li{padding:4px 0;border-bottom:1px solid var(--line)}
.fix{color:var(--muted);font-size:14px;margin-left:16px}
a{color:var(--green)}footer{color:var(--muted);font-size:14px;text-align:center}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid var(--line);border-top-color:var(--green);border-radius:50%;animation:s 1s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes s{to{transform:rotate(360deg)}}
</style></head><body><main>
<h1>Scouts Passports</h1>
<p class="sub">Make every Cub's passport from ScoutsTracker, check it, and print it.</p>

<section class="card">
  <h2>Status</h2>
  <div class="status" id="status">Loading…</div>
</section>

<section class="card">
  <h2>Make passports</h2>
  <div class="row">
    <label>Include OAS stages 1 to
      <select id="stage"><option>3</option><option selected>4</option><option>5</option><option>6</option><option>7</option><option>8</option><option>9</option></select>
    </label>
    <label><input type="checkbox" id="fetch" checked> Get the latest from ScoutsTracker</label>
  </div>
  <p class="row" style="margin:16px 0 0"><button class="primary" id="go">Make passports</button>
    <span id="jobstate"></span></p>
  <div class="msg" id="msg"></div>
  <details id="logbox"><summary>Show details</summary><pre id="log"></pre></details>
</section>

<section class="card" id="results" hidden>
  <h2>Results <span id="rdate" style="color:var(--muted);font-weight:400"></span></h2>
  <div class="counts" id="counts"></div>
  <div class="row">
    <button data-open="print">Open print file</button>
    <button data-open="audit">Open check report</button>
    <button data-open="folder">Open passports folder</button>
  </div>
  <p class="fix" style="margin:12px 0 0">Print single-sided, actual size. Cut each Cub's stack on the dashed lines,
  then stack the piles top-left, top-right, bottom-left, bottom-right.</p>
</section>

<section class="card">
  <h2>Sign in &amp; setup</h2>
  <div class="row">
    <button id="login">Sign into ScoutsTracker</button>
    <button id="check">Check setup</button>
    <button data-open="data">Open private data folder</button>
  </div>
  <p class="fix" style="margin:10px 0 0">Signing in opens a separate browser window. Type your details and PIN there;
  this tool never sees your password.</p>
  <ul class="checks" id="checks"></ul>
</section>

<footer>
  <a id="help" href="#" target="_blank" rel="noopener">Troubleshooting guide</a> ·
  Help: Drew Carmichael, <a href="mailto:drew.carmichael@gmail.com">drew.carmichael@gmail.com</a> ·
  <a href="#" id="quit">Close</a>
</footer>
</main>
<script>
const T="__TOKEN__";
const api=(p,opt={})=>fetch(p,{...opt,headers:{"X-Token":T,"Content-Type":"application/json"}}).then(r=>r.json().then(j=>({ok:r.ok,j})));
const $=id=>document.getElementById(id);
let since=0,polling=false;

function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function msg(text,kind){const m=$("msg");m.className="msg show "+kind;m.innerHTML=text}

async function refresh(){
  const {j:s}=await api("/api/status");
  $("help").href=s.help_url;
  const age=s.data_date?Math.round((Date.now()-new Date(s.data_date+"T12:00"))/864e5):null;
  $("status").innerHTML=
    `<span><span class="dot ${s.signed_in_before?"ok":"err"}"></span>ScoutsTracker</span><span>${s.signed_in_before?"Signed in before (you may need your PIN again)":"Not signed in yet: click <b>Sign into ScoutsTracker</b>"}</span>`+
    `<span><span class="dot ${s.data_date&&age<=7?"ok":"warn"}"></span>Data</span><span>${s.data_date?`Fetched ${s.data_date}${age>0?` (${age} day${age>1?"s":""} ago)`:" (today)"}`:"None yet"}</span>`+
    `<span><span class="dot ${!s.result?"warn":s.result.counts.ERROR?"err":"ok"}"></span>Passports</span><span>${s.result?`${s.result.cubs} made on ${s.result.date}`:"None yet"}</span>`;
  if(s.result){
    $("results").hidden=false;$("rdate").textContent="("+s.result.date+")";
    const c=s.result.counts;
    $("counts").innerHTML=`<span class="pill e">${c.ERROR} errors</span><span class="pill w">${c.WARN} to check in ScoutsTracker</span><span class="pill i">${c.INFO} notes</span>`;
  }
}

async function poll(){
  if(polling)return;polling=true;
  while(true){
    const {j}=await api("/api/job?since="+since);
    if(j.lines.length){$("log").textContent+=j.lines.join("\n")+"\n";$("log").scrollTop=1e9;since=j.total}
    const last=j.lines.filter(l=>l.startsWith("=== ")).pop();
    if(j.running){$("jobstate").innerHTML=`<span class="spinner"></span>${esc(j.name)}… ${last?esc(last.replace(/=/g,"").trim()):""}`;busy(true)}
    else{
      busy(false);$("jobstate").textContent="";
      if(j.name){done(j)}
      break;
    }
    await new Promise(r=>setTimeout(r,800));
  }
  polling=false;refresh();
}

function done(j){
  const log=$("log").textContent;
  if(j.name==="Making passports"){
    if(j.exit_code===0) msg("Done! All passports passed the check. Use <b>Open print file</b> below.","good");
    else if(/PIN|not logged in|Not logged into/i.test(log)) msg("ScoutsTracker needs you to sign in again (your PIN expires every so often). Click <b>Sign into ScoutsTracker</b>, then <b>Make passports</b> again.","note");
    else if(/ERROR/.test(log)) msg("Passports were made, but some have errors. Open the <b>check report</b> before printing.","bad");
    else {msg("Something went wrong. Open <b>Show details</b> below, and see the troubleshooting guide.","bad");$("logbox").open=true}
  } else if(j.name==="Signing in"){
    msg(j.exit_code===0?"Signed in. You can make passports now.":"Sign-in didn't finish. Try again; the window waits 10 minutes.",j.exit_code===0?"good":"note");
  } else if(j.name==="Checking setup"){ loadChecks(); msg(j.exit_code===0?"Setup looks good.":"Some setup checks failed. See the list under <b>Sign in &amp; setup</b>.",j.exit_code===0?"good":"bad") }
}

function busy(b){for(const id of ["go","login","check"])$(id).disabled=b}

async function start(path,body){
  $("log").textContent="";since=0;$("msg").className="msg";
  const {ok,j}=await api(path,{method:"POST",body:JSON.stringify(body||{})});
  if(!ok){msg(j.error==="busy"?"Something is already running. Please wait.":esc(j.error),"note");return}
  poll();
}

async function loadChecks(){
  const {j}=await api("/api/doctor");
  const icon={ok:"ok",warn:"warn",fail:"err"};
  $("checks").innerHTML=(Array.isArray(j)?j:[]).filter(c=>c.status!=="ok").map(c=>
    `<li><span class="dot ${icon[c.status]}"></span><b>${esc(c.check)}</b>: ${esc(c.detail)}${c.fix?`<div class="fix">→ ${esc(c.fix)}</div>`:""}</li>`).join("")
    || `<li><span class="dot ok"></span>Everything is set up.</li>`;
}

$("go").onclick=()=>start("/api/run",{stage:+$("stage").value,fetch:$("fetch").checked});
$("login").onclick=()=>start("/api/login");
$("check").onclick=()=>start("/api/check");
document.querySelectorAll("[data-open]").forEach(b=>b.onclick=async()=>{
  const {ok}=await api("/api/open",{method:"POST",body:JSON.stringify({what:b.dataset.open})});
  if(!ok)msg("That hasn't been made yet.","note");
});
$("quit").onclick=async e=>{e.preventDefault();await api("/api/quit",{method:"POST"});
  document.body.innerHTML="<main><h1>Closed</h1><p class='sub'>You can close this tab.</p></main>"};

refresh();loadChecks();poll();
</script></body></html>"""


if __name__ == "__main__":
    sys.exit(main())
