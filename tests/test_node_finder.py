"""N1 · find the node: this computer, the local network, saved, typed — and one
sentence. The network is replaced by fakes; one test probes a real HTTP server."""
import http.server
import json
import subprocess
import threading

from s3dgraphy.tools import node_finder as N

DNS_SD_B = """Browsing for _stratigraph._tcp.local.
DATE: ---Sun 04 Oct 2026---
11:02:03.123  ...STARTING...
Timestamp     A/R    Flags  if Domain               Service Type         Instance Name
11:02:03.456  Add        2  14 local.               _stratigraph._tcp.   StratiGraph lab (fcn)
"""
DNS_SD_L = """Lookup StratiGraph lab (fcn)._stratigraph._tcp.local.
11:02:04.001  StratiGraph\\032lab\\032(fcn)._stratigraph._tcp.local. can be reached at fcn.local.:8777 (interface 14)
"""


def test_parse_dns_sd_and_avahi():
    assert N.parse_dns_sd(DNS_SD_B) == [{"domain": "local", "name": "StratiGraph lab (fcn)"}]
    avahi = "=;eth0;IPv4;StratiGraph lab;_stratigraph._tcp;local;fcn.local;192.168.1.9;8777;\n"
    assert N.parse_avahi(avahi) == [{"name": "StratiGraph lab", "host": "fcn.local",
                                     "address": "192.168.1.9", "port": "8777", "txt": ""}]


#: measured 4 Oct 2026 on this Mac: `dns-sd -R probe-fcn-test _stratigraph._tcp
#: local. 8443 path=/em scheme=https`, then `dns-sd -L` — the TXT is the next line
DNS_SD_L_FCN = """Lookup probe-fcn-test._stratigraph._tcp.local.
DATE: ---Sun 04 Oct 2026---
13:14:54.518  ...STARTING...
13:14:54.519  probe-fcn-test._stratigraph._tcp.local. can be reached at MacBook-Pro-di-Emanuel.local.:8443 (interface 14) Flags: 1
 path=/em scheme=https
13:14:54.519  probe-fcn-test._stratigraph._tcp.local. can be reached at MacBook-Pro-di-Emanuel.local.:8443 (interface 14)
 path=/em scheme=https
"""


def test_the_dev_stack_announced_by_fcn_up_resolves_to_its_https_door():
    def runner(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1, output=DNS_SD_L_FCN)
    assert N.resolve_dns_sd("probe-fcn-test", runner=runner) == \
        "https://MacBook-Pro-di-Emanuel.local:8443/em"
    avahi = ('=;eth0;IPv4;StratiGraph fcn;_stratigraph._tcp;local;fcn.local;192.168.1.9;8443;'
             '"scheme=https" "path=/em"\n')
    got = N.browse_lan(1, tool="avahi-browse",
                       runner=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, avahi, ""))
    assert got["found"] == [{"name": "StratiGraph fcn", "url": "https://fcn.local:8443/em"}]


def test_the_personal_node_path_slash_stays_a_bare_address():
    assert N.url_of("fcn.local.", "8777", "path=/") == "http://fcn.local:8777"
    assert N.url_of("fcn.local", "8777", "") == "http://fcn.local:8777"
    assert N.url_of("h.local", "1", "scheme=gopher path=em") == "http://h.local:1/em"


def test_browse_lan_with_dns_sd_resolves_the_url():
    def runner(cmd, **kw):
        out = DNS_SD_B if "-B" in cmd else DNS_SD_L
        raise subprocess.TimeoutExpired(cmd, 1, output=out)     # dns-sd browses until killed
    got = N.browse_lan(1, tool="dns-sd", runner=runner)
    assert got["how"] == "dns-sd"
    assert got["found"] == [{"name": "StratiGraph lab (fcn)", "url": "http://fcn.local:8777"}]


def test_no_browser_is_said_not_pretended():
    got = N.browse_lan(1, tool=None, runner=None) if False else None
    import shutil
    real = shutil.which
    try:
        shutil.which = lambda name: None
        got = N.browse_lan(1)
    finally:
        shutil.which = real
    assert got["how"] == "none" and "cannot be browsed" in got["note"]


def test_the_suggestion_follows_what_was_found():
    off = lambda u: {"url": u, "reachable": False}                       # noqa: E731
    none = N.find_nodes(prober=off, browser=lambda: {"how": "dns-sd", "found": [], "note": ""})
    assert none["suggestion_key"] == "none" and "lavora sul computer" in none["suggestion"]
    personal = lambda u: ({"url": u, "reachable": True, "profile": "personal"}  # noqa: E731
                          if u.endswith(":8777") else {"url": u, "reachable": False})
    got = N.find_nodes(prober=personal, browser=lambda: {"how": "dns-sd", "found": [], "note": ""})
    assert got["suggestion_key"] == "personal" and "disco salvato" in got["suggestion"]
    assert [p["url"] for p in got["local"]] == ["http://127.0.0.1:8777"]
    lan = N.find_nodes(prober=lambda u: {"url": u, "reachable": "fcn" in u},
                       browser=lambda: {"how": "dns-sd", "note": "",
                                        "found": [{"name": "lab", "url": "http://fcn.local:8777"}]},
                       lang="en")
    assert lan["suggestion_key"] == "lan" and lan["lan"][0]["name"] == "lab"
    assert "mini-PC" in lan["real_node"]


def test_probe_reads_health_and_the_ways_in_of_a_real_server():
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            body = {"/health": {"ok": True, "version": "1.6.0.dev1", "profile": "personal",
                                "s3dgraphy": "1.6.0.dev35", "rooms": 2},
                    "/v1/auth-config": {"enforcing": False}}.get(self.path)
            self.send_response(200 if body else 404)
            self.end_headers()
            if body:
                self.wfile.write(json.dumps(body).encode())
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        got = N.probe(f"http://127.0.0.1:{srv.server_port}")
    finally:
        srv.shutdown()
    assert got["reachable"] and got["profile"] == "personal" and got["ways_in"] == ["open"]
    assert N.probe("http://127.0.0.1:9")["reachable"] is False
