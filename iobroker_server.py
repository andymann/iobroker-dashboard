#!/usr/bin/env python3
"""
ioBroker dashboard web server
Fetches live values from ioBroker simple-api on every request and serves HTML.
Configure via environment variables:
  IOBROKER_HOST   - e.g. http://192.168.178.53:8087
  IOBROKER_STATES - comma-separated state IDs
  LISTEN_PORT     - default 8080
  FETCH_TIMEOUT   - default 5
"""

import urllib.request
import urllib.parse
import json
import datetime
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Config (env vars override defaults) ──────────────────────────────────────

IOBROKER_HOST = os.environ.get("IOBROKER_HOST", "http://192.168.178.53:8087").rstrip("/")

_default_states = [
    "zigbee.0.44e2f8fffe61d5d9.state",
    "zigbee.0.44e2f8fffe61d5d9.colortemp",
    "zigbee.0.8c65a3fffef115e2.state",
]
_states_env = os.environ.get("IOBROKER_STATES", "")
STATES = [s.strip() for s in _states_env.split(",") if s.strip()] or _default_states

LISTEN_PORT   = int(os.environ.get("LISTEN_PORT", "8080"))
FETCH_TIMEOUT = int(os.environ.get("FETCH_TIMEOUT", "5"))

# ── ioBroker helpers ──────────────────────────────────────────────────────────

def iob_fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as r:
            body = r.read().decode()
            ct = r.headers.get("Content-Type", "")
            return json.loads(body) if "json" in ct else body.strip()
    except Exception:
        return None

def extract_val(data):
    if data is None:              return None, None
    if isinstance(data, (bool, int, float)): return data, None
    if isinstance(data, str):
        t = data.strip()
        if t == "true":  return True,  None
        if t == "false": return False, None
        try: return (float(t) if "." in t else int(t)), None
        except: return t or None, None
    if isinstance(data, dict):
        if "val" not in data and "value" not in data and len(data) == 1:
            data = next(iter(data.values()))
        if "val"   in data: return data["val"],   data.get("ts") or data.get("lc")
        if "value" in data: return data["value"], data.get("ts") or data.get("lc")
    return None, None

def resolve_name(data):
    if not isinstance(data, dict): return None
    if "common" not in data and len(data) == 1:
        data = next(iter(data.values()))
    n = (data.get("common") or {}).get("name")
    if not n: return None
    if isinstance(n, str):  return n.strip() or None
    if isinstance(n, dict): return n.get("en") or n.get("de") or next(iter(n.values()), None)
    return None

def resolve_unit(data):
    if not isinstance(data, dict): return ""
    if "common" not in data and len(data) == 1:
        data = next(iter(data.values()))
    return (data.get("common") or {}).get("unit", "") or ""

def parent_id(sid):
    parts = sid.split(".")
    return ".".join(parts[:-1]) if len(parts) > 1 else sid

def fetch_all():
    tiles, dev_cache = [], {}
    for state_id in STATES:
        enc = urllib.parse.quote(state_id, safe="")
        raw = None
        for url in [f"{IOBROKER_HOST}/v1/state/{enc}",
                    f"{IOBROKER_HOST}/get/{enc}",
                    f"{IOBROKER_HOST}/getPlainValue/{enc}"]:
            raw = iob_fetch(url)
            if raw is not None:
                break

        val, _  = extract_val(raw)
        label   = (resolve_name(raw) if isinstance(raw, dict) else None) or state_id.split(".")[-1]
        unit    =  resolve_unit(raw) if isinstance(raw, dict) else ""
        dev_id  = parent_id(state_id)

        if dev_id not in dev_cache:
            enc_dev = urllib.parse.quote(dev_id, safe="")
            dev_raw = iob_fetch(f"{IOBROKER_HOST}/get/{enc_dev}") \
                   or iob_fetch(f"{IOBROKER_HOST}/v1/object/{enc_dev}")
            dev_cache[dev_id] = resolve_name(dev_raw) or dev_id

        tiles.append({"id": state_id, "dev_id": dev_id, "dev_name": dev_cache[dev_id],
                      "label": label, "val": val, "unit": unit})
    return tiles

# ── HTML rendering ────────────────────────────────────────────────────────────

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def fmt(v):
    if v is None:            return "—"
    if v is True:            return "ON"
    if v is False:           return "OFF"
    if isinstance(v, float): return f"{v:,.2f}".rstrip("0").rstrip(".")
    if isinstance(v, int):   return f"{v:,}"
    return str(v)

def render(tiles):
    order, groups = [], {}
    for t in tiles:
        if t["dev_id"] not in groups:
            groups[t["dev_id"]] = []
            order.append(t["dev_id"])
        groups[t["dev_id"]].append(t)

    cards = ""
    for dev_id in order:
        dt = groups[dev_id]
        dn = dt[0]["dev_name"]
        hdr = (f'<div class="dn">{esc(dn)}</div><div class="di">{esc(dev_id)}</div>'
               if dn != dev_id else f'<div class="dn">{esc(dev_id)}</div>')
        row = ""
        for t in dt:
            v   = t["val"]
            cls = " on" if v is True else " off" if v is False else ""
            row += (f'<div class="tile">'
                    f'<div class="tl">{esc(t["label"])}</div>'
                    f'<div class="tv{cls}">{esc(fmt(v))}</div>'
                    f'<div class="tf">{esc(t["unit"])}</div>'
                    f'</div>')
        cards += f'<div class="card"><div class="ch">{hdr}</div><div class="tr">{row}</div></div>'

    now = datetime.datetime.now().strftime("%H:%M:%S")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>ioBroker</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0efe9;color:#1a1a1a;min-height:100vh;padding:24px}}
.top{{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}}
h1{{font-size:16px;font-weight:500;color:#888}}
.ts{{font-size:11px;color:#bbb}}
.devices{{display:flex;flex-direction:column;gap:16px}}
.card{{background:#fff;border:0.5px solid rgba(0,0,0,.10);border-radius:12px;overflow:hidden}}
.ch{{padding:10px 14px;border-bottom:0.5px solid rgba(0,0,0,.08);background:#f7f6f2}}
.dn{{font-size:13px;font-weight:600}}
.di{{font-size:10px;color:#bbb;margin-top:2px}}
.tr{{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr))}}
.tile{{padding:12px 14px;border-right:0.5px solid rgba(0,0,0,.08)}}
.tile:last-child{{border-right:none}}
.tl{{font-size:10px;color:#888;text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px}}
.tv{{font-size:26px;font-weight:500;line-height:1.1}}
.tv.on{{color:#2a7a2a}}.tv.off{{color:#c0392b}}
.tf{{font-size:10px;color:#bbb;margin-top:5px}}
@media(prefers-color-scheme:dark){{
  body{{background:#111;color:#efefef}}
  .card{{background:#1c1c1c;border-color:rgba(255,255,255,.09)}}
  .ch{{background:#242424;border-color:rgba(255,255,255,.09)}}
  .dn{{color:#efefef}}.tile{{border-color:rgba(255,255,255,.09)}}
  .tv{{color:#efefef}}.tv.on{{color:#4caf50}}.tv.off{{color:#e57373}}
}}
</style>
</head>
<body>
<div class="top"><h1>ioBroker</h1><span class="ts">Updated {now} &middot; auto-refresh 30s</span></div>
<div class="devices">{cards}</div>
</body>
</html>"""

# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_response(404); self.end_headers(); return
        try:
            body = render(fetch_all()).encode()
            self.send_response(200)
            self.send_header("Content-Type",   "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500); self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, fmt, *args):
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {fmt % args}", flush=True)

if __name__ == "__main__":
    print(f"ioBroker: {IOBROKER_HOST}")
    print(f"States:   {STATES}")
    print(f"Listening on 0.0.0.0:{LISTEN_PORT}")
    HTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()
