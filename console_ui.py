"""The console's single HTML page: static markup, catalog labels injected at render."""

import json

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DevBox Console</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px; font: 14px/1.5 ui-sans-serif, system-ui, sans-serif;
         background: #0b0d10; color: #e6e8eb; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .sub { color: #8b94a3; margin-bottom: 20px; font-size: 12px; }
  .grid { display: grid; gap: 8px; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); }
  button { font: inherit; padding: 10px 12px; border-radius: 8px; cursor: pointer;
           border: 1px solid #262b33; background: #14181d; color: #e6e8eb; text-align: left; }
  button:hover { border-color: #3b82f6; }
  button:disabled { opacity: .5; cursor: progress; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; }
  th, td { text-align: left; padding: 8px; border-bottom: 1px solid #1c2128; vertical-align: top; }
  th { color: #8b94a3; font-weight: 500; font-size: 12px; }
  code { font-family: ui-monospace, monospace; font-size: 12px; }
  .tag { padding: 1px 6px; border-radius: 999px; font-size: 11px; background: #1c2128; }
  .running { background: #14361f; color: #4ade80; }
  .starting, .provisioning { background: #3a2d10; color: #fbbf24; }
  .finished, .stopped { background: #1c2128; color: #8b94a3; }
  .expired, .lost { background: #2a1f3d; color: #c4b5fd; }
  .error { background: #3b1414; color: #f87171; }
  .bar { display: flex; align-items: center; gap: 12px; margin: 0 0 14px;
         color: #8b94a3; font-size: 12px; }
  .bar button { padding: 6px 10px; font-size: 12px; }
  .bar label { display: flex; align-items: center; gap: 6px; cursor: pointer; }
  .stop { border-color: #3b1414; color: #f87171; padding: 4px 8px; font-size: 12px; }
  .msg { margin: 12px 0; padding: 8px 10px; border-radius: 8px; background: #14181d;
         border: 1px solid #262b33; color: #8b94a3; font-size: 12px; display: none; }
  h2 { font-size: 14px; margin: 28px 0 0; color: #8b94a3; font-weight: 500; }
</style>
</head>
<body>
<h1>DevBox Console</h1>
<div class="sub">Boxes publish their tunnels to a Modal Dict. Status is polled from Modal every 5 s.</div>
<div class="bar">
  <button id="refresh">Refresh</button>
  <label><input type="checkbox" id="auto" checked> auto-refresh 5 s</label>
  <span id="updated"></span>
</div>
<div class="grid" id="catalog"></div>
<div class="msg" id="msg"></div>
<h2>Boxes</h2>
<table>
  <thead><tr><th>Box</th><th>Status</th><th>Connection</th><th></th></tr></thead>
  <tbody id="rows"><tr><td colspan="4" style="color:#8b94a3">loading…</td></tr></tbody>
</table>
<script>
const CATALOG = __CATALOG__;
const msg = document.getElementById('msg');
const autoEl = document.getElementById('auto');
const updatedEl = document.getElementById('updated');
function ago(seconds) {
  if (seconds === undefined || seconds === null) return '';
  if (seconds < 90) return seconds + 's';
  if (seconds < 5400) return Math.round(seconds / 60) + 'm';
  return (seconds / 3600).toFixed(1) + 'h';
}
function say(text, ok) {
  msg.textContent = text;
  msg.style.display = text ? 'block' : 'none';
  msg.style.color = ok === false ? '#f87171' : '#8b94a3';
}
function renderCatalog() {
  const root = document.getElementById('catalog');
  root.innerHTML = '';
  for (const [id, label] of Object.entries(CATALOG)) {
    const b = document.createElement('button');
    b.textContent = label;
    b.onclick = () => launch(id, b);
    root.appendChild(b);
  }
}
async function launch(id, btn) {
  btn.disabled = true;
  say('spawning ' + id + '…');
  try {
    const r = await fetch('/api/launch', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({box_type: id})
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.status);
    say('spawned ' + id + ' (call ' + (data.call_id || '?') + '). It appears here once its tunnel opens.',
        true);
    load();
  } catch (e) {
    say('launch failed: ' + e.message, false);
  } finally {
    btn.disabled = false;
  }
}
async function stop(boxId) {
  if (!confirm('Force-stop ' + boxId + '? The exit backup will not run.')) return;
  const r = await fetch('/api/boxes/' + encodeURIComponent(boxId) + '/stop', {method: 'POST'});
  const data = await r.json();
  say(r.ok ? 'stop requested for ' + boxId : 'stop failed: ' + (data.error || r.status), r.ok);
  load();
}
function connection(rec) {
  if (rec.rdp_address) return 'RDP ' + rec.rdp_address + ' · root / ' + (rec.rdp_password || '?');
  const parts = [];
  if (rec.web_url) parts.push('<a href="' + rec.web_url + '" target="_blank">Open web UI</a>');
  if (rec.ssh_command) parts.push('<code>' + rec.ssh_command + '</code>');
  return parts.join('<br>') || '<span style="color:#8b94a3">waiting for tunnel…</span>';
}
async function load() {
  try {
    const r = await fetch('/api/boxes');
    const data = await r.json();
    const rows = document.getElementById('rows');
    if (!r.ok) throw new Error(data.error || r.status);
    updatedEl.textContent = 'updated ' + new Date().toLocaleTimeString();
    if (!data.boxes.length) {
      rows.innerHTML = '<tr><td colspan="4" style="color:#8b94a3">no boxes yet</td></tr>';
      return;
    }
    rows.innerHTML = '';
    for (const rec of data.boxes) {
      const tr = document.createElement('tr');
      const status = rec.status || 'unknown';
      tr.innerHTML = '<td>' + (rec.kind || '?') +
        ' <span style="color:#8b94a3">· ' + ago(rec.age_s) + '</span><br><code style="color:#8b94a3">' +
        (rec.box_id || '') + '</code></td>' +
        '<td><span class="tag ' + status + '">' + status + '</span></td>' +
        '<td>' + connection(rec) + '</td>' +
        '<td></td>';
      const cell = tr.lastElementChild;
      if (rec.call_id && status !== 'stopped') {
        const b = document.createElement('button');
        b.className = 'stop';
        b.textContent = 'Stop';
        b.onclick = () => stop(rec.box_id);
        cell.appendChild(b);
      }
      rows.appendChild(tr);
    }
  } catch (e) {
    say('could not load boxes: ' + e.message, false);
  }
}
renderCatalog();
load();
document.getElementById('refresh').onclick = () => load();
setInterval(() => { if (autoEl.checked) load(); }, 5000);
</script>
</body>
</html>
"""


def render_index(catalog):
    """INDEX_HTML with the launch buttons' labels filled in from `catalog`."""
    return INDEX_HTML.replace("__CATALOG__", json.dumps({k: v[0] for k, v in catalog.items()}))
