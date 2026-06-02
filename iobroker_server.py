#!/usr/bin/env python3
"""
ioBroker dashboard web server
Configure via environment variables:
  IOBROKER_HOST, LISTEN_PORT, FETCH_TIMEOUT
States and layout configured via /config/states.txt
"""

import urllib.request
import urllib.parse
import json
import datetime
import os
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Config ────────────────────────────────────────────────────────────────────

IOBROKER_HOST = os.environ.get("IOBROKER_HOST", "http://192.168.178.53:8087").rstrip("/")
LISTEN_PORT   = int(os.environ.get("LISTEN_PORT",   "8080"))
FETCH_TIMEOUT = int(os.environ.get("FETCH_TIMEOUT", "5"))
STATES_FILE   = os.environ.get("STATES_FILE", "/config/states.txt")

# ── states.txt parser ─────────────────────────────────────────────────────────
# Returns a list of groups: [{"label": str, "ids": [str, ...]}, ...]
# Lines starting with # or blank are ignored.
# [Group Name] starts a new group. IDs without a preceding group header
# are auto-grouped by their parent device ID.

def load_groups():
    try:
        with open(STATES_FILE) as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"WARNING: {STATES_FILE} not found, using defaults", flush=True)
        lines = [
            "[Default]\n",
            "zigbee.0.44e2f8fffe61d5d9.state\n",
            "zigbee.0.44e2f8fffe61d5d9.colortemp\n",
        ]

    groups = []
    current_label = None
    current_ids   = []

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^\[(.+)\]$', line)
        if m:
            # Save previous group
            if current_ids:
                groups.append({"label": current_label, "ids": current_ids})
            current_label = m.group(1).strip()
            current_ids   = []
        else:
            # It's a state ID
            if current_label is None:
                # No header yet — use parent device ID as label
                current_label = ".".join(line.split(".")[:-1]) or line
            current_ids.append(line)

    if current_ids:
        groups.append({"label": current_label, "ids": current_ids})

    return groups

# ── ioBroker fetch ────────────────────────────────────────────────────────────

def iob_fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as r:
            body = r.read().decode()
            ct = r.headers.get("Content-Type", "")
            return json.loads(body) if "json" in ct else body.strip()
    except Exception as e:
        print(f"  GET {url} → ERROR: {e}", flush=True)
        return None

def extract_val(data):
    if data is None:
        return None, None
    if isinstance(data, bool):
        return data, None
    if isinstance(data, (int, float)):
        return data, None
    if isinstance(data, str):
        t = data.strip()
        if t == "true":  return True,  None
        if t == "false": return False, None
        try: return (float(t) if "." in t else int(t)), None
        except: return (t if t else None), None
    if not isinstance(data, dict):
        return None, None
    if len(data) == 1 and not any(k in data for k in ("val","value","type","common","_id")):
        data = next(iter(data.values()))
        if not isinstance(data, dict):
            return None, None
    if "val"   in data: return data["val"],   data.get("ts") or data.get("lc")
    if "value" in data: return data["value"], data.get("ts") or data.get("lc")
    if "state" in data and isinstance(data["state"], dict) and "val" in data["state"]:
        return data["state"]["val"], data["state"].get("ts")
    return None, None

def resolve_name(data):
    if not isinstance(data, dict):
        return None
    if len(data) == 1 and "common" not in data:
        inner = next(iter(data.values()))
        if isinstance(inner, dict):
            data = inner
    n = (data.get("common") or {}).get("name")
    if not n: return None
    if isinstance(n, str):  return n.strip() or None
    if isinstance(n, dict): return n.get("en") or n.get("de") or next(iter(n.values()), None)
    return None

def resolve_unit(data):
    if not isinstance(data, dict):
        return ""
    if len(data) == 1 and "common" not in data:
        inner = next(iter(data.values()))
        if isinstance(inner, dict):
            data = inner
    return (data.get("common") or {}).get("unit", "") or ""

def fetch_state(state_id):
    enc = urllib.parse.quote(state_id, safe="")
    raw = None
    for url in [
        f"{IOBROKER_HOST}/get/{enc}",
        f"{IOBROKER_HOST}/v1/state/{enc}",
        f"{IOBROKER_HOST}/getPlainValue/{enc}",
    ]:
        raw = iob_fetch(url)
        if raw is not None:
            break
    val, _  = extract_val(raw)
    label   = (resolve_name(raw) if isinstance(raw, dict) else None) or state_id.split(".")[-1]
    unit    =  resolve_unit(raw) if isinstance(raw, dict) else ""
    return {"id": state_id, "val": val, "label": label, "unit": unit}

def fetch_all(groups):
    result = []
    for group in groups:
        tiles = [fetch_state(sid) for sid in group["ids"]]
        result.append({"label": group["label"], "tiles": tiles})
    return result

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

def render(groups_data):
    cards = ""
    for group in groups_data:
        row = ""
        for t in group["tiles"]:
            v   = t["val"]
            cls = " on" if v is True else " off" if v is False else ""
            row += (f'<div class="tile">'
                    f'<div class="tl">{esc(t["label"])}</div>'
                    f'<div class="tv{cls}">{esc(fmt(v))}</div>'
                    f'<div class="tf">{esc(t["unit"])}</div>'
                    f'</div>')
        cards += (f'<div class="card">'
                  f'<div class="ch">{esc(group["label"])}</div>'
                  f'<div class="tr">{row}</div>'
                  f'</div>')

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
.ch{{padding:10px 14px;border-bottom:0.5px solid rgba(0,0,0,.08);background:#f7f6f2;font-size:13px;font-weight:600}}
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
  .ch{{background:#242424;border-color:rgba(255,255,255,.09);color:#efefef}}
  .tile{{border-color:rgba(255,255,255,.09)}}
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
            groups = load_groups()
            data   = fetch_all(groups)
            body   = render(data).encode()
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
    print(f"ioBroker: {IOBROKER_HOST}", flush=True)
    print(f"States file: {STATES_FILE}", flush=True)
    print(f"Listening on 0.0.0.0:{LISTEN_PORT}", flush=True)
    HTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()