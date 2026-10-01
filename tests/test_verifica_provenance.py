"""scripts/verifica-provenance.sh waits for PyPI, and says which of three reds it is.

Measured on 1 Oct 2026 (the dev25 run): the upload finished at 05:19:53, the
check started at 05:19:57, retried for ~7 s, got 404 from the JSON index
because the CDN did not show the version yet, and turned a successful publish
red. Run by hand an hour later it said «2 file su 2 con provenance».

These tests put a fake index in front of the script (PYPI_URL) that answers 404
for the first N requests and then 200, and shrink the wait to a few seconds:

* 404 a few times, then 200        → it waits, and ends green (0);
* 404 until the wait runs out      → «non ancora visibile» (75);
* a provenance naming another repo → a real error (3);
* a visible version, no provenance → a real error (1).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verifica-provenance.sh"
VERSION = "9.9.9.dev1"
FILES = ("s3dgraphy-9.9.9.dev1-py3-none-any.whl", "s3dgraphy-9.9.9.dev1.tar.gz")
REPO = "ExtendedMatrix/s3Dgraphy"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("curl") is None,
    reason="the script needs bash and curl")


def _index_body():
    return {"info": {"version": VERSION}, "urls": [{"filename": f} for f in FILES]}


def _provenance_body(repo):
    return {"attestation_bundles": [{
        "publisher": {"kind": "GitHub", "repository": repo, "workflow": "publish.yml"},
        "attestations": []}]}


class FakeIndex:
    """404 for the first `late` hits of each URL, then the canned answer."""

    def __init__(self, late=0, index=True, provenance_repo=REPO, provenance=True):
        self.late, self.index, self.repo, self.provenance = late, index, provenance_repo, provenance
        self.hits = {}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def do_GET(self):
                n = owner.hits[self.path] = owner.hits.get(self.path, 0) + 1
                body = None
                if n > owner.late:
                    if self.path == f"/pypi/s3dgraphy/{VERSION}/json" and owner.index:
                        body = _index_body()
                    elif self.path.endswith("/provenance") and owner.provenance:
                        body = _provenance_body(owner.repo)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b'{"message": "Not Found"}')
                    return
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def run():
    servers = []

    def _run(total=6, **kw):
        idx = FakeIndex(**kw)
        servers.append(idx)
        env = dict(os.environ, PYPI_URL=idx.url, GITHUB_REPOSITORY=REPO,
                   ATTESA_TOTALE=str(total), ATTESA_INIZIALE="1", ATTESA_TETTO="2")
        p = subprocess.run(["bash", str(SCRIPT), VERSION], env=env,
                           capture_output=True, text=True, errors="replace", timeout=120)
        return p, p.stdout + p.stderr, idx

    yield _run
    for s in servers:
        s.close()


def test_a_version_late_on_the_index_is_waited_for_and_ends_green(run):
    p, out, idx = run(late=2, total=10)
    assert p.returncode == 0, out
    assert "2 file su 2 con provenance" in out
    assert idx.hits[f"/pypi/s3dgraphy/{VERSION}/json"] == 3
    # one line per attempt, so a workflow log shows it is waiting
    assert "tentativo 1/" in out and "prossimo fra 1 s" in out
    assert "tentativo 2/" in out and "prossimo fra 2 s" in out


def test_a_version_never_visible_is_not_yet_visible_not_an_error(run):
    p, out, _ = run(index=False, total=4)
    assert p.returncode == 75, out
    assert "pubblicata? non ancora visibile" in out
    assert "ATTESA_TOTALE=600" in out
    assert "attesa finita" in out


def test_a_provenance_from_another_repository_is_a_real_error(run):
    p, out, _ = run(provenance_repo="somebody/else")
    assert p.returncode == 3, out
    assert "nomina «somebody/else», non «ExtendedMatrix/s3Dgraphy»" in out


def test_a_visible_version_without_provenance_is_a_real_error(run):
    p, out, _ = run(provenance=False, total=4)
    assert p.returncode == 1, out
    assert "MANCA l'attestazione" in out
    assert "non ancora visibile" not in out


def test_no_version_is_a_usage_error():
    p = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
    assert p.returncode == 2
