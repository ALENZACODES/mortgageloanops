"""Tiny stdlib web server: GET / (demo UI), POST /api/process, GET /api/health, GET /api/samples."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .messaging import Messenger
from .pipeline import process_application
from .samples import SAMPLES
from . import lenders, __version__

PAGE = """<!doctype html><meta charset=utf-8><title>MortgageLoanOps</title>
<style>body{font:14px system-ui;background:#0b0f14;color:#e6edf3;max-width:980px;margin:24px auto;padding:0 16px}
select,button{font:inherit;padding:8px 12px;border-radius:8px;border:1px solid #30363d;background:#161b22;color:#e6edf3}
button{background:#238636;border-color:#238636;cursor:pointer}textarea{width:100%;height:230px;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:10px;font:12px ui-monospace,monospace}
pre{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:12px;overflow:auto;max-height:520px}</style>
<h2>MortgageLoanOps <small style="color:#8b949e">dry-run demo</small></h2>
<p>Sample file: <select id=s></select> <label><input type=checkbox id=f> simulate SMS failure (shows fallback)</label> <button id=go>Process file</button></p>
<textarea id=in spellcheck=false></textarea><h3>Result</h3><pre id=out>Click “Process file”.</pre>
<script>
let S={};fetch('/api/samples').then(r=>r.json()).then(j=>{S=j;for(const k in j){s.add(new Option(k,k))};s.onchange();});
s.onchange=()=>{in_.value=JSON.stringify(S[s.value],null,2)};const in_=document.getElementById('in');
go.onclick=async()=>{out.textContent='…';const r=await fetch('/api/process'+(f.checked?'?fail=sms':''),{method:'POST',body:in_.value});out.textContent=JSON.stringify(await r.json(),null,2)};
</script>"""


def make_handler(messenger_factory):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code); self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                return self._send(200, PAGE, "text/html; charset=utf-8")
            if self.path == "/api/health":
                return self._send(200, json.dumps({"ok": True, "version": __version__, "lenders_in_registry": lenders.registry_count(),
                                                   "mode": "live" if messenger_factory().live else "dry-run"}))
            if self.path == "/api/samples":
                return self._send(200, json.dumps(SAMPLES))
            self._send(404, json.dumps({"error": "not found"}))

        def do_POST(self):
            if not self.path.startswith("/api/process"):
                return self._send(404, json.dumps({"error": "not found"}))
            try:
                app = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                fails = ("sms",) if "fail=sms" in self.path else ()
                res = process_application(app, messenger_factory(), simulate_failures=fails)
                self._send(200, json.dumps(res, default=str))
            except (KeyError, ValueError, TypeError) as e:
                self._send(400, json.dumps({"error": f"{type(e).__name__}: {e}"}))

        def log_message(self, *a):
            pass
    return H


def serve(port: int = 8000):
    srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(lambda: Messenger()))
    print(f"MortgageLoanOps on http://localhost:{port}  (mode: {'LIVE' if Messenger().live else 'dry-run'})")
    srv.serve_forever()
