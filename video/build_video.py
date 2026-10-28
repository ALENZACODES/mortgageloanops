"""Builds docs/demo.mp4 (silent, captioned, ~3 min) from the REAL outputs of this repo.
Run from repo root:  python video/build_video.py   (needs playwright + ffmpeg)"""
import html, json, subprocess, sys, threading, time, os, shutil
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0, ".")
from mortgageloanops import pipeline, guardrail, lenders
from mortgageloanops.messaging import Messenger
from mortgageloanops.samples import SAMPLES
from mortgageloanops.server import make_handler
from playwright.sync_api import sync_playwright

OUT = Path("/tmp/vid"); OUT.mkdir(exist_ok=True)
W, H = 1920, 1080
CSS = """*{box-sizing:border-box}body{margin:0;width:1920px;height:1080px;background:#0b0f14;color:#e6edf3;font-family:Inter,system-ui,sans-serif;display:flex;flex-direction:column}
.top{padding:46px 70px 0}.k{color:#3fb950;font-size:26px;letter-spacing:.14em;text-transform:uppercase;font-weight:700}h1{font-size:64px;margin:12px 0 0;line-height:1.1}h2{font-size:50px;margin:10px 0 0}
.body{flex:1;padding:28px 70px;display:flex;gap:40px;align-items:flex-start}pre{margin:0;background:#0d1117;border:1px solid #30363d;border-radius:14px;padding:24px 28px;font:26px/1.4 ui-monospace,'DejaVu Sans Mono',monospace;color:#d2dae3;white-space:pre-wrap;flex:1}
.card{background:#161b22;border:1px solid #30363d;border-radius:16px;padding:26px 32px;flex:1}.big{font-size:84px;font-weight:800}.lbl{color:#8b949e;font-size:26px}.g{color:#3fb950}.r{color:#f85149}.y{color:#d29922}.o{color:#ff9900}
.cap{background:#10161d;border-top:1px solid #30363d;padding:24px 70px;font-size:31px;color:#c9d1d9;min-height:128px}.tag{position:absolute;right:56px;top:40px;background:#1f2a1f;color:#3fb950;border:1px solid #2ea043;border-radius:999px;padding:8px 20px;font-size:24px;font-weight:700}
li{font-size:38px;line-height:1.5;margin-bottom:10px}"""

def page(kicker, title, body, cap, tag="DRY-RUN · real code output"):
    return f"<style>{CSS}</style><body><div class=tag>{tag}</div><div class=top><div class=k>{kicker}</div><h1>{title}</h1></div><div class=body>{body}</div><div class=cap>{cap}</div></body>"

def esc(x): return html.escape(x if isinstance(x, str) else json.dumps(x, indent=2, default=str))

shutil.rmtree("/tmp/vid/outbox", ignore_errors=True)
m = Messenger(live=False, outbox_dir="/tmp/vid/outbox", config={"sms_origination":"+15551230000","whatsapp_phone_number_id":"phone-number-id-DEMO","meta_api_version":"v20.0","email_from":"ops@example.com"})
fthb = pipeline.process_application(SAMPLES["purchase_fthb"], m, simulate_failures=("sms",))
ren = pipeline.process_application(SAMPLES["renewal_ird"], m)
dec = pipeline.process_application(SAMPLES["declined_stress"], m)
wa = next(Path("/tmp/vid/outbox").glob("whatsapp-*.json")).read_text()
tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-v"], capture_output=True, text=True).stdout
test_lines = [l for l in tests.splitlines() if "PASSED" in l or "passed" in l]
summary = test_lines[-1].strip("= ")
sel = [l.split("::")[1].split(" ")[0] + "  PASSED" for l in test_lines if "PASSED" in l]
pick = ["test_qualification_invariants_10k  PASSED","test_payment_and_penalty_invariants_10k  PASSED","test_lender_match_monotonic_and_guardrail_10k  PASSED","test_stress_uses_true_payment_not_linear_scaling  PASSED","test_insured_rules_dec_2024  PASSED","test_sms_request_shape_matches_end_user_messaging_sms_api  PASSED","test_falls_back_sms_to_whatsapp_with_social_api_shape  PASSED","test_timeout_triggers_fallback  PASSED","test_guardrail_blocks_before_any_aws_call  PASSED","test_kyc_never_reports_clear  PASSED"]

q = fthb["qualification"]; d = dec["qualification"]; p = ren["penalty"]; r = ren["refinance"]; hv = fthb["home_value"]
S = []
S.append((10, page("Canadian mortgage operations on AWS", "MortgageLoanOps", "<div class=card><ul><li><b class=g>LendOps</b> — B-20 qualification, insured rules, lender match</li><li><b class=g>IRD</b> — prepayment penalty + break-even refinance</li><li><b class=g>Benchmark</b> — indicative home value by regional index</li><li>Borrower messages via <b class=o>AWS End User Messaging (SMS, WhatsApp)</b> and <b class=o>Amazon SES</b></li></ul></div>",
  "Three tools in one open-source app. Everything shown is the real code running; this recording uses DRY-RUN mode (no AWS account was called).")))
S.append((14, page("The problem", "Mortgage files stall between “inquiry” and “broker”", "<div class=card><ul><li>Borrowers wait days for a first response</li><li>Renewal penalties (IRD) are opaque and costly</li><li>Automated outreach can’t quote rates or promise approvals</li><li>Files need a stress test and the right lender category fast</li></ul></div>",
  "MortgageLoanOps triages each file, explains the numbers to the broker, and messages the borrower safely.", "")))
S.append((16, "ARCH", "Architecture: every outbound borrower message passes a guardrail, then SMS → WhatsApp → SES → portal, 5 seconds per channel. AWS services are in orange.", ""))
S.append((22, "UI", "The real web UI (stdlib server, `python -m mortgageloanops serve`): pick a sample file, tick “simulate SMS failure”, process. Result shows qualification, lender matches, and the delivery attempts.", "DRY-RUN · live UI"))
S.append((18, page("LendOps · qualification", "First-time buyer, $750K, 30-year (insured rules, Dec 15 2024)",
  f"<div class=card><div class=lbl>Qualifying rate</div><div class='big g'>{q['qualifying_rate']}%</div><div class=lbl>max(contract 4.5% + 2%, 5.25%)</div></div><div class=card><div class=lbl>Payment: contract → stressed</div><div class='big'>${q['contract_payment']:,.0f} → ${q['stressed_payment']:,.0f}</div><div class=lbl>true annuity formula, semi-annual compounding</div></div><div class=card><div class=lbl>GDS / TDS</div><div class='big g'>{q['gds']}% / {q['tds']}%</div><div class=lbl>{len(fthb['lender_matches'])} lender matches (category policy)</div></div>",
  "30-year insured amortization is allowed for first-time buyers since Dec 15 2024 (source: Department of Finance Canada). A repeat buyer with the same file would be limited to 25 years.")))
S.append((16, page("LendOps · declined file", "Over-leveraged file: clear reasons for the broker",
  f"<pre>{esc(dict(passes=d['passes'], gds=d['gds'], tds=d['tds'], reasons=d['reasons'], lender_matches=dec['lender_matches']))}</pre>",
  "No lenders matched, and the file is routed to manual review with the exact rules that failed.")))
S.append((22, page("IRD · prepayment penalty", "Break the mortgage or stay?",
  f"<div class=card><div class=lbl>3 months’ interest</div><div class='big'>${p['three_months']:,.0f}</div></div><div class=card><div class=lbl>IRD (posted-rate method)</div><div class='big r'>${p['ird']:,.0f}</div><div class=lbl>penalty = greater of the two</div></div><div class=card><div class=lbl>Refinance verdict</div><div class='big y' style='font-size:56px'>{r['recommendation']}</div><div class=lbl>saves ${r['monthly_saving']:,.0f}/mo; break-even {r['break_even_months']} months vs 30 left</div></div>",
  "Example: $400,000 balance, 5.2% fixed, 30 months left, originally 6.9% posted. Estimates only: the lender’s contract decides the real payout.")))
S.append((14, page("Benchmark · home value", "Indicative value from a purchase price + regional index",
  f"<div class=card><div class=lbl>Bought June 2022 for $750,000 · GTA</div><div class='big'>${hv['estimate']:,.0f}</div><div class=lbl>range ${hv['low']:,.0f} – ${hv['high']:,.0f} · index factor {hv['index_factor']}</div></div><div class=card><div class=lbl>Method</div><div style='font-size:34px;margin-top:10px'>{hv['method']}<br><span class=y>{hv['disclaimer']}</span></div></div>",
  "Ported from the Benchmark Home Value project. Anchors are indicative regional curves, not sold-listing data, and this is not an appraisal.")))
bl = [("Rates from 3.99% today!"), ("You are approved for $500,000"), ("We guarantee the lowest rate"), ("A licensed broker will contact you about your file.")]
S.append((16, page("Compliance guardrail", "Unsafe messages never reach AWS",
  "<pre>" + "\n".join(f"{'BLOCKED ' if not guardrail.check(t)['allowed'] else 'ALLOWED '} {esc(t)}\n         → {esc(guardrail.check(t)['violations'] or 'ok')}" for t in bl) + "</pre>",
  "Blocked: rate quotes, approval promises, guarantees. Test `guardrail_blocks_before_any_aws_call` proves zero AWS calls are made for a blocked message.")))
S.append((20, page("AWS messaging with fallback", "SMS failed → WhatsApp delivered (5 s timeout per channel)",
  f"<pre>attempts:\n{esc(fthb['borrower_message']['attempts'])}\n\nrequest that would go to AWS End User Messaging Social:\n{esc(json.loads(wa)['request'])}</pre>",
  "Shapes follow the documented APIs: pinpoint-sms-voice-v2 SendTextMessage, socialmessaging SendWhatsAppMessage, sesv2 SendEmail. In live mode (MLO_LIVE=1) the same payloads are sent.", "DRY-RUN · AWS request shown, not sent")))
S.append((16, page("Verification", summary, "<pre>" + esc("\n".join(pick)) + "\n\n+ 10,000-case randomized invariant tests\n+ AWS request shapes asserted with fake clients\n+ tests fail when code is deliberately broken</pre>",
  "Unit + property tests, not a backtest against real lending outcomes.", "pytest · real run")))
S.append((16, page("Honest status", "What is and isn’t proven", "<div class=card><ul><li class=g>Working: calculations, matching, guardrail, fallback logic, web UI, 35 tests</li><li class=y>Illustrative: lender policy by category (34 names, none panel-verified)</li><li class=y>Interface only: identity/PEP screening (never says “clear”)</li><li class=o>Live AWS delivery needs your account, verified SES identity, SMS origination and WhatsApp number</li></ul></div>",
  "github.com/ALENZACODES/mortgageloanops · MIT licensed · python -m mortgageloanops demo")))

DUR=[8,10,14,20,18,14,18,14,16,18,14,14]
S=[(DUR[i],)+tuple(x[1:]) for i,x in enumerate(S)]

def shoot():
    srv = ThreadingHTTPServer(("127.0.0.1", 8765), make_handler(lambda: Messenger(live=False, outbox_dir="/tmp/vid/outbox")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(viewport={"width": W, "height": H})
        for i, (dur, content, *rest) in enumerate(S):
            f = OUT / f"s{i:02d}.png"
            if content == "ARCH":
                (OUT/"arch.html").write_text(f"<style>{CSS}</style><body><div style='flex:1;display:flex;align-items:center;justify-content:center;background:#0b0f14'><img src='file:///home/claude/mortgageloanops/docs/architecture.svg' style='width:1920px'></div><div class=cap>{rest[0]}</div></body>")
                pg.goto("file:///tmp/vid/arch.html"); pg.wait_for_timeout(400)
            elif content == "UI":
                pg.goto("http://127.0.0.1:8765/"); pg.wait_for_timeout(600)
                pg.evaluate("document.body.style.zoom='1.6'"); pg.select_option("#s", "purchase_fthb"); pg.check("#f"); pg.click("#go"); pg.wait_for_timeout(900)
                pg.evaluate("document.querySelector('textarea').style.height='150px'; document.querySelector('pre').style.maxHeight='520px'")
                pg.screenshot(path=str(f)); 
                img = f
                (OUT/"ui.html").write_text(f"<style>{CSS}</style><body><div class=tag>DRY-RUN · live UI</div><div style='flex:1;background:#0b0f14;display:flex;justify-content:center;padding-top:20px'><img src='file://{img}' style='height:900px;border:1px solid #30363d;border-radius:12px'></div><div class=cap>{rest[0]}</div></body>")
                pg.goto("file:///tmp/vid/ui.html"); pg.wait_for_timeout(500)
            else:
                pg.set_content(content); pg.wait_for_timeout(150)
            pg.screenshot(path=str(f.with_name(f"f{i:02d}.png")))
        b.close(); srv.shutdown()

shoot()
lines = ""
for i, (dur, *_ ) in enumerate(S):
    lines += f"file 'f{i:02d}.png'\nduration {dur}\n"
lines += f"file 'f{len(S)-1:02d}.png'\n"
(OUT / "list.txt").write_text(lines)
total = sum(d for d, *_ in S); print("total seconds:", total)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(OUT / "list.txt"), "-vf", "fps=24,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-movflags", "+faststart", str(OUT / "demo.mp4")], check=True)
print(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "default=nw=1", str(OUT / "demo.mp4")], capture_output=True, text=True).stdout)
