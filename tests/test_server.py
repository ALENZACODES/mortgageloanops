import json, threading, urllib.request
from http.server import ThreadingHTTPServer
from mortgageloanops.server import make_handler
from mortgageloanops.messaging import Messenger
from mortgageloanops.samples import SAMPLES


def _srv(tmp_path):
    s = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: Messenger(live=False, outbox_dir=str(tmp_path))))
    threading.Thread(target=s.serve_forever, daemon=True).start(); return s


def test_health_process_and_bad_input(tmp_path):
    s = _srv(tmp_path); base = f"http://127.0.0.1:{s.server_address[1]}"
    try:
        h = json.load(urllib.request.urlopen(base + "/api/health")); assert h["ok"] and h["mode"] == "dry-run" and h["lenders_in_registry"] == 34
        req = urllib.request.Request(base + "/api/process", data=json.dumps(SAMPLES["purchase_fthb"]).encode(), method="POST")
        out = json.load(urllib.request.urlopen(req)); assert out["qualification"]["passes"] and out["borrower_message"]["delivered_via"] == "sms"
        bad = urllib.request.Request(base + "/api/process", data=b'{"borrower": {"name": "x"}, "type": "PURCHASE"}', method="POST")
        try: urllib.request.urlopen(bad); assert False
        except urllib.error.HTTPError as e: assert e.code == 400
        assert b"MortgageLoanOps" in urllib.request.urlopen(base + "/").read()
    finally:
        s.shutdown()
