"""status-03 step 4: the dashboard UI files, served with a fixture /api/state.
Run: uv run --with pytest --with pyyaml pytest -q tests/test_dash_ui.py"""
import functools
import http.server
import json
import re
import shutil
import subprocess
import threading
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "dash" / "static"
FIXTURE = ROOT / "tests" / "fixtures" / "dash_state.json"


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/state":
            body = FIXTURE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def base():
    h = functools.partial(Handler, directory=str(STATIC))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read().decode()


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts, self.styles = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("src"):
            self.scripts.append(a["src"])
        if tag == "link" and a.get("rel") == "stylesheet":
            self.styles.append(a["href"])


def test_fixture_state_is_served(base):
    st = json.loads(get(base + "/api/state"))
    assert len(st["nodes"]) == 2
    assert sorted(n["status"] for n in st["nodes"].values()) == ["ok", "stale"]
    assert len(st["prs"]) == 1
    assert any(s.get("waiting") and s.get("snippet") for n in st["nodes"].values() for s in n["report"]["sessions"])
    assert len({r["origin"] for n in st["nodes"].values() for r in n["report"]["repos"]}) == 2


def test_index_loads_app_and_both_css(base):
    p = Refs()
    p.feed(get(base + "/index.html"))
    assert p.scripts == ["/app.js"]
    assert p.styles == ["/tokens.css", "/app.css"]
    for ref in p.scripts + p.styles:
        assert get(base + ref).strip(), ref
    assert "render.mjs" in get(base + "/app.js")


@pytest.mark.parametrize("name", ["app.js", "render.mjs"])
def test_js_has_no_innerhtml_or_external_urls(name):
    src = (STATIC / name).read_text()
    assert not re.search(r"\.(inner|outer)HTML\s*(\+?=|\()|insertAdjacentHTML|document\.write", src)
    assert not re.search(r"https?://|//cdn\.|@import", src)


def test_css_has_no_external_urls():
    for name in ("app.css", "tokens.css"):
        assert not re.search(r"https?://|@import", (STATIC / name).read_text()), name


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_render_functions_on_fixture():
    r = subprocess.run(["node", "--test", "dash/static/render.test.mjs"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
