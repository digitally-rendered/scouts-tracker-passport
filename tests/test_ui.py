"""ui.py: the local point-and-click page."""
import http.client
import json
import threading
import time

import pytest

import ui


@pytest.fixture(scope="module")
def server(data_dir):
    srv, url, token, job = ui.make_server()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], token, job
    srv.shutdown()
    srv.server_close()


def request(port, method, path, token=None, body=None, host="127.0.0.1"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    headers = {"Host": f"{host}:{port}", "Content-Type": "application/json"}
    if token:
        headers["X-Token"] = token
    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    r = conn.getresponse()
    data = r.read().decode("utf-8")
    conn.close()
    try:
        return r.status, json.loads(data)
    except json.JSONDecodeError:
        return r.status, data


def test_page_needs_the_secret_key(server):
    port, token, _ = server
    assert request(port, "GET", "/")[0] == 403
    assert request(port, "GET", "/?t=wrong")[0] == 403
    code, page = request(port, "GET", f"/?t={token}")
    assert code == 200 and "Make passports" in page and token in page


def test_api_rejects_missing_token_and_foreign_host(server):
    port, token, _ = server
    assert request(port, "GET", "/api/status")[0] == 403
    assert request(port, "POST", "/api/run", body={"stage": 4})[0] == 403
    assert request(port, "GET", "/api/status", token, host="evil.example")[0] == 403


def test_status_and_doctor(server):
    port, token, _ = server
    code, s = request(port, "GET", "/api/status", token)
    assert code == 200 and s["data_date"] == "2026-01-01" and "help_url" in s
    code, checks = request(port, "GET", "/api/doctor", token)
    assert code == 200 and any(c["check"] == "Passport template" for c in checks)


def test_rejects_bad_stage(server):
    port, token, _ = server
    assert request(port, "POST", "/api/run", token, {"stage": 12})[0] == 400


def test_make_passports_from_the_page(server, monkeypatch):
    port, token, job = server
    code, r = request(port, "POST", "/api/run", token, {"stage": 4, "fetch": False})
    assert code == 200 and r["ok"]
    assert request(port, "POST", "/api/run", token, {"stage": 4, "fetch": False})[0] == 409  # busy
    deadline = time.time() + 240
    while time.time() < deadline:
        _, j = request(port, "GET", "/api/job?since=0", token)
        if not j["running"]:
            break
        time.sleep(0.5)
    assert j["exit_code"] == 0, "\n".join(j["lines"][-40:])
    assert any("4/4" in line for line in j["lines"])
    _, s = request(port, "GET", "/api/status", token)
    assert s["result"]["cubs"] == 3 and s["result"]["counts"]["ERROR"] == 0
    assert s["result"]["has_print"] and s["result"]["has_audit"]

    opened = []
    monkeypatch.setattr(ui, "open_path", opened.append)
    assert request(port, "POST", "/api/open", token, {"what": "print"})[0] == 200
    assert request(port, "POST", "/api/open", token, {"what": "nope"})[0] == 404
    assert opened and opened[0].name == "ALL CUBS - print 4-up.pdf"


def test_printers_listed_and_unknown_printer_rejected(server, monkeypatch):
    import print_passports
    port, token, _ = server
    monkeypatch.setattr(print_passports, "list_printers", lambda: (["Test Printer"], "Test Printer"))
    code, r = request(port, "GET", "/api/printers", token)
    assert code == 200 and r["printers"] == ["Test Printer"] and r["default"] == "Test Printer"
    assert request(port, "POST", "/api/print", token, {"printer": "Not A Printer"})[0] == 400
    assert request(port, "POST", "/api/print", token, {})[0] == 400


def test_print_from_page_runs_print_script(server, monkeypatch):
    import print_passports
    port, token, job = server
    monkeypatch.setattr(print_passports, "list_printers", lambda: (["Test Printer"], "Test Printer"))
    started = []
    monkeypatch.setattr(job, "start", lambda name, args: started.append((name, args)) or True)
    assert request(port, "POST", "/api/print", token, {"printer": "Test Printer", "test": True})[0] == 200
    name, args = started[0]
    assert name == "Printing" and args[:3] == ["print_passports.py", "--printer", "Test Printer"]
    assert "--yes" in args and "--test-sheet" in args
