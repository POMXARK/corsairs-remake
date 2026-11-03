#!/usr/bin/env python3
"""Web GUI for fixing a head: pick a region (click a part or drag a box on the views), write what you want, run the
agent or one tool, watch every pass (before | after | view, the score, the tool weights), undo, save.

head_gui.py in.glb --views f l b r [--parts parts.npy] [--work dir] [--port 8770]   then open http://127.0.0.1:8770
Only the loopback address is served. The parts are made by head_parts.py when not given. Python stdlib server, no
dependencies beyond the head tools.
"""
import io
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import head_agent as ha  # noqa: E402
import head_parts as hp  # noqa: E402
import head_tools as ht  # noqa: E402

TILE = 384  # pixels of one view in the GUI picture


class App:
    def __init__(self, path, views, parts, work, policy):
        self.work, self.policy = work, policy
        os.makedirs(work, exist_ok=True)
        if parts is None:
            hp.run(path, views, os.path.join(work, 'parts'))
            parts = os.path.join(work, 'parts', 'parts.npy')
        self.h = ht.Head(path, views, parts)
        self.undo = []
        self.sel_parts, self.sel_faces = set(), np.zeros(len(self.h.tris), bool)
        self.intents, self.prompt = [], ''
        self.lock = threading.Lock()
        self.agent, self.thread, self.log = None, None, []
        self.refresh()

    def say(self, s):
        self.log = (self.log + [time.strftime('%H:%M:%S ') + s])[-200:]
        print(s, flush=True)

    def mask(self):
        m = self.sel_faces.copy()
        if self.sel_parts:
            m |= ht.region(self.h, ','.join(sorted(self.sel_parts)))
        return m

    def refresh(self):
        self.pics = ht.render(self.h)

    def picture(self, mode):
        m = self.mask()
        tiles = []
        for n in ht.pv.NAMES:
            col, ids = self.pics[n]
            if mode == 'parts':
                col = hp.COLOURS[self.h.parts][np.maximum(ids, 0)].astype(np.float32)
                col[ids < 0] = 30
            else:
                col = col.copy()
            sel = (ids >= 0) & m[np.maximum(ids, 0)]
            col[sel] = col[sel] * 0.55 + np.array([255, 40, 200]) * 0.45
            tiles.append(np.asarray(Image.fromarray(col.clip(0, 255).astype(np.uint8)).resize((TILE, TILE))))
        buf = io.BytesIO()
        Image.fromarray(np.concatenate(tiles, 1)).save(buf, 'PNG')
        return buf.getvalue()

    def faces_at(self, view, x0, y0, x1, y1):
        ids = self.pics[ht.pv.NAMES[view]][1]
        r = ids.shape[0]
        X0, X1 = sorted((int(x0 * r), int(x1 * r) + 1))
        Y0, Y1 = sorted((int(y0 * r), int(y1 * r) + 1))
        f = ids[max(Y0, 0):min(Y1, r), max(X0, 0):min(X1, r)].ravel()
        return np.unique(f[f >= 0])

    def select(self, q):
        op = q.get('op', 'add')
        if op == 'clear':
            self.sel_parts.clear()
            self.sel_faces[:] = False
            return
        v = int(q['view'])
        f = self.faces_at(v, q['x'], q['y'], q.get('x2', q['x']), q.get('y2', q['y']))
        if q.get('kind') == 'part' and len(f):
            p = hp.EN[int(np.bincount(self.h.parts[f]).argmax())]
            (self.sel_parts.discard if op == 'remove' else self.sel_parts.add)(p)
        else:
            if q.get('kind') == 'rect' and len(f):  # the faces of the box and the hidden ones behind them in the box too
                lo, hi = self.h.P.min(0), self.h.P.max(0)
                vw = self.h.views[ht.pv.NAMES[v]]
                x, y = ht.pv.project(self.h.P[self.h.tris].mean(1), ht.pv.NAMES[v], vw, lo, hi)
                W, H = vw[0].shape[1], vw[0].shape[0]
                bx = sorted((q['x'], q.get('x2', q['x'])))
                by = sorted((q['y'], q.get('y2', q['y'])))
                inside = (x / W >= bx[0]) & (x / W <= bx[1]) & (y / H >= by[0]) & (y / H <= by[1])
                if q.get('through'):
                    f = np.where(inside)[0]
            self.sel_faces[f] = op != 'remove'

    def status(self):
        st = {}
        if self.agent:
            try:
                st = json.load(open(os.path.join(self.work, 'state.json')))
            except (OSError, ValueError):
                pass
        m = self.mask()
        est = ha.estimates(ha.load_policy(self.policy), sorted(self.sel_parts), self.intents)
        return {**st, 'running': bool(self.thread and self.thread.is_alive()), 'sel_parts': sorted(self.sel_parts),
                'sel_faces': int(m.sum()), 'intents': self.intents, 'prompt': self.prompt, 'log': self.log[-40:],
                'undo': len(self.undo), 'model': self.h.path,
                'weights_now': [{'arm': k, 'estimate': round(v[0], 2), 'tries': v[1]} for k, v in
                                sorted(est.items(), key=lambda kv: -kv[1][0])],
                'tools': {k: {'params': d, 'ru': ru, 'kind': kind} for k, (_, d, ru, kind) in ht.TOOLS.items()},
                'parts_legend': [{'en': e, 'ru': r, 'colour': c.tolist()} for e, r, c in zip(hp.EN, hp.PARTS, hp.COLOURS)]}

    def set_prompt(self, text):
        parts, intents = ha.parse_prompt(text)
        self.prompt, self.intents = text, intents
        if parts:
            self.sel_parts = set(parts)
        self.say(f'промпт: части {parts or "(выделение)"}, намерения {intents or "(все инструменты)"}')

    def new_agent(self):
        m = self.mask()
        if not m.any():
            raise ValueError('нет области: кликните часть или выделите рамкой')
        parts = sorted(self.sel_parts) or ['custom']
        self.agent = ha.Agent(self.h, m, parts, self.intents, self.work, self.policy, self.say)
        if self.sel_faces.any() and not self.sel_parts:
            self.agent.parts = []  # a box only: the context is 'custom'
        return self.agent

    def run_agent(self, passes):
        ag = self.new_agent()
        self.undo.append(self.h.copy())

        def go():
            try:
                h = ag.run(passes)
                with self.lock:
                    self.h = h
                    self.refresh()
                self.say(f'агент: {ag.history[0]} → {ag.history[-1]}')
            except Exception as e:  # noqa: BLE001 - shown in the GUI log
                self.say(f'ошибка агента: {e!r}')
        self.thread = threading.Thread(target=go, daemon=True)
        self.thread.start()

    def apply(self, tool, params):
        ag = self.new_agent()
        self.undo.append(self.h.copy())
        rec = ag.step((tool, params), learn=True)
        self.h = ag.trial[0]  # a hand-applied tool stays even when the score fell: the user asked for it
        if not rec['kept']:
            self.h.save(os.path.join(self.work, 'current.glb'))
        self.refresh()
        return rec

    def do_undo(self):
        if self.undo:
            self.h = self.undo.pop()
            self.refresh()


PAGE = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Head Fixer</title><style>
:root{--bg:#16181c;--fg:#e8e8e8;--mut:#9aa0a8;--card:#20242a;--acc:#ff4fc8;--ok:#5fd38d;--bad:#ef6b6b}
body{background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif;margin:0;padding:12px 16px}
h1{font-size:18px;margin:0 0 8px} .row{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start}
.card{background:var(--card);border-radius:8px;padding:10px;margin-bottom:12px}
#views{position:relative;max-width:100%;overflow:auto} #views img{display:block;max-width:100%;cursor:crosshair;user-select:none}
#box{position:absolute;border:1px dashed var(--acc);pointer-events:none;display:none}
button,select,input{background:#2c323a;color:var(--fg);border:1px solid #3a414b;border-radius:5px;padding:5px 9px;font:inherit}
button:hover{border-color:var(--acc)} input[type=text]{width:min(520px,90vw)}
.mut{color:var(--mut)} .ok{color:var(--ok)} .bad{color:var(--bad)} table{border-collapse:collapse} td,th{padding:2px 8px;text-align:left}
.pass{display:inline-block;margin:4px;vertical-align:top;width:390px;max-width:95vw} .pass img{width:100%}
.bar{height:8px;background:var(--acc);border-radius:4px} #log{white-space:pre-wrap;font:12px monospace;max-height:180px;overflow:auto}
.leg span{display:inline-block;margin:2px 6px 2px 0} .leg i{display:inline-block;width:10px;height:10px;margin-right:3px}
</style></head><body>
<h1>Head Fixer <span class="mut" id="model"></span></h1>
<div class="card">
 <div class="row">
  <label>Режим: <select id="mode"><option value="colour">модель</option><option value="parts">части</option></select></label>
  <label>Клик: <select id="kind"><option value="part">часть целиком</option><option value="rect">рамка/грани</option></select></label>
  <label><input type="checkbox" id="through"> рамка насквозь</label>
  <label><input type="checkbox" id="remove"> убрать из выделения</label>
  <button onclick="post('/select',{op:'clear'})">сбросить выделение</button>
  <span id="sel" class="mut"></span>
 </div>
 <div id="views"><img id="img" draggable="false"><div id="box"></div></div>
 <div class="leg" id="leg"></div>
</div>
<div class="card row">
 <div><input type="text" id="prompt" placeholder="что сделать: «сгладить глаза», «убрать волосы с шеи», «перекрасить уши»">
 <button onclick="post('/prompt',{text:val('prompt')})">разобрать</button>
 <label>проходов <input id="passes" value="8" size="3"></label>
 <button onclick="post('/run',{passes:+val('passes')})">▶ агент</button>
 <button onclick="post('/stop',{})">■ стоп</button></div>
 <div><select id="tool"></select> <input id="params" size="28" placeholder='{"steps":15}'>
 <button onclick="post('/apply',{tool:val('tool'),params:JSON.parse(val('params')||'{}')})">применить</button>
 <button onclick="post('/undo',{})">↶ отменить</button>
 <button onclick="post('/save',{})">сохранить glb</button></div>
 <div id="intents" class="mut"></div>
</div>
<div class="row">
 <div class="card"><b>Оценка области</b> <span id="score"></span><svg id="chart" width="360" height="120"></svg></div>
 <div class="card"><b>Веса инструментов</b> <span class="mut" id="ctx"></span><table id="weights"></table></div>
 <div class="card" style="flex:1;min-width:280px"><b>Журнал</b><div id="log"></div></div>
</div>
<div class="card"><b>Проходы</b><div id="passes_list"></div></div>
<script>
const $=id=>document.getElementById(id), val=id=>$(id).value;
let tools={}, stamp=0, drag=null;
async function post(u,b){const r=await fetch(u,{method:'POST',body:JSON.stringify(b)});const j=await r.json();if(j.error)alert(j.error);load(true)}
function pic(){$('img').src='/view.png?mode='+val('mode')+'&t='+(stamp++)}
$('mode').onchange=pic;
function rel(e){const r=$('img').getBoundingClientRect(),w=r.width/4;const v=Math.min(3,Math.floor((e.clientX-r.left)/w));
 return {view:v,x:(e.clientX-r.left-v*w)/w,y:(e.clientY-r.top)/r.height,px:e.clientX-r.left,py:e.clientY-r.top}}
$('img').onmousedown=e=>{drag=rel(e)};
$('img').onmousemove=e=>{if(!drag||val('kind')!='rect')return;const p=rel(e),b=$('box');b.style.display='block';
 b.style.left=Math.min(p.px,drag.px)+'px';b.style.top=Math.min(p.py,drag.py)+'px';b.style.width=Math.abs(p.px-drag.px)+'px';b.style.height=Math.abs(p.py-drag.py)+'px'};
$('img').onmouseup=e=>{const p=rel(e);$('box').style.display='none';if(!drag)return;
 post('/select',{view:drag.view,x:drag.x,y:drag.y,x2:p.view==drag.view?p.x:drag.x,y2:p.view==drag.view?p.y:drag.y,kind:val('kind'),
  op:$('remove').checked?'remove':'add',through:$('through').checked});drag=null};
function chart(h){if(!h||!h.length)return'';const W=360,H=120,lo=Math.min(...h)-1,hi=Math.max(...h)+1;
 const pts=h.map((v,i)=>[(h.length<2?0:i/(h.length-1))*(W-30)+25,H-15-(v-lo)/(hi-lo)*(H-25)]);
 return `<text x="0" y="12" fill="#9aa0a8" font-size="10">${hi.toFixed(0)}</text><text x="0" y="${H-12}" fill="#9aa0a8" font-size="10">${lo.toFixed(0)}</text>`+
 `<polyline fill="none" stroke="#ff4fc8" stroke-width="2" points="${pts.map(p=>p.join(',')).join(' ')}"/>`+pts.map(p=>`<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="#ff4fc8"/>`).join('')}
let last='';
async function load(force){const s=await (await fetch('/state')).json();
 $('model').textContent=s.model; $('sel').textContent=`выделено: ${s.sel_parts.join(', ')||'—'} (${s.sel_faces} граней)`;
 $('intents').textContent=`намерения: ${s.intents.join(', ')||'все инструменты'}${s.running?' · агент работает…':''} · отмен: ${s.undo}`;
 if(!Object.keys(tools).length){tools=s.tools;$('tool').innerHTML=Object.entries(tools).map(([k,v])=>`<option value="${k}" title="${v.ru}">${k} — ${v.ru}</option>`).join('');
  $('tool').onchange=()=>{$('params').value=JSON.stringify(tools[val('tool')].params)};$('tool').onchange();
  $('leg').innerHTML=s.parts_legend.map(p=>`<span><i style="background:rgb(${p.colour})"></i>${p.ru}</span>`).join('')}
 if(s.score){$('score').innerHTML=`<b>${s.score.score}</b> <span class="mut">цвет ${s.score.colour}, кожа→волосы ${(s.score.skin_as_hair*100).toFixed(1)} %, угол ${s.score.angle}°, складки ${(s.score.folds*100).toFixed(1)} %, сдвиг ${s.score.drift}</span>`;$('chart').innerHTML=chart(s.history)}
 const w=s.running&&s.weights?s.weights:s.weights_now, mx=Math.max(1,...w.map(x=>Math.abs(x.estimate)));
 $('ctx').textContent=s.context||''; $('weights').innerHTML='<tr><th>инструмент</th><th>оценка</th><th>проб</th><th></th></tr>'+
  w.map(x=>`<tr><td>${x.arm}</td><td class="${x.estimate>0?'ok':'bad'}">${x.estimate}</td><td>${x.tries}</td><td><div class="bar" style="width:${Math.max(2,60*Math.abs(x.estimate)/mx)}px;background:${x.estimate>0?'#5fd38d':'#ef6b6b'}"></div></td></tr>`).join('');
 $('log').textContent=s.log.join('\n'); $('log').scrollTop=1e9;
 const key=JSON.stringify([s.passes&&s.passes.length,s.sel_faces,s.sel_parts,s.undo,s.running]);
 if(s.passes)$('passes_list').innerHTML=s.passes.slice().reverse().map(p=>`<div class="pass"><img src="/work/${p.picture}?${p.n}"><div><b>${p.n}</b> ${p.arm} <span class="${p.kept?'ok':'bad'}">${p.before.score} → ${p.after.score} (${p.reward>0?'+':''}${p.reward}) ${p.kept?'принят':'откат'}</span> <span class="mut">${p.seconds} с</span></div></div>`).join('');
 if(force||key!=last){last=key;pic()}}
load(true); setInterval(load,2000);
</script></body></html>'''


def handler(app):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, body, ctype='application/json', code=200):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False, default=str).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == '/':
                return self.send(PAGE, 'text/html; charset=utf-8')
            if u.path == '/state':
                return self.send(app.status())
            if u.path == '/view.png':
                with app.lock:
                    return self.send(app.picture(q.get('mode', 'colour')), 'image/png')
            if u.path.startswith('/work/'):
                p = os.path.realpath(os.path.join(app.work, u.path[6:]))
                if p.startswith(os.path.realpath(app.work) + os.sep) and os.path.isfile(p) and p.endswith('.png'):
                    return self.send(open(p, 'rb').read(), 'image/png')
            self.send({'error': 'not found'}, code=404)

        def do_POST(self):
            u = urlparse(self.path).path
            b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            busy = app.thread and app.thread.is_alive()
            try:
                if u == '/stop':
                    if app.agent:
                        app.agent.stop = True
                    return self.send({'ok': 1})
                if busy:
                    return self.send({'error': 'агент работает: дождитесь или нажмите стоп'})
                with app.lock:
                    if u == '/select':
                        app.select(b)
                    elif u == '/prompt':
                        app.set_prompt(b.get('text', ''))
                    elif u == '/run':
                        app.run_agent(int(b.get('passes', 8)))
                    elif u == '/apply':
                        r = app.apply(b['tool'], b.get('params', {}))
                        app.say(f"{r['arm']}: {r['before']['score']} → {r['after']['score']}")
                    elif u == '/undo':
                        app.do_undo()
                    elif u == '/save':
                        p = os.path.join(app.work, 'saved.glb')
                        app.h.save(p)
                        app.say('сохранено ' + p)
                    else:
                        return self.send({'error': 'unknown'}, code=404)
                return self.send({'ok': 1})
            except Exception as e:  # noqa: BLE001 - the GUI shows it
                return self.send({'error': repr(e)})
    return H


def main():
    a = sys.argv[1:]

    def opt(name, n=1, default=None):
        if name not in a:
            return default
        i = a.index(name)
        v = a[i + 1:i + 1 + n]
        del a[i:i + 1 + n]
        return v if n > 1 else v[0]
    vp = opt('--views', 4)
    parts = opt('--parts')
    port = int(opt('--port', default=8770))
    work = opt('--work', default=os.path.splitext(a[0])[0] + '_gui')
    policy = opt('--policy', default=ha.POLICY)
    views = {n: ht.pv.load_view(p) for n, p in zip(ht.pv.NAMES, vp)}
    app = App(a[0], views, parts, work, policy)
    srv = ThreadingHTTPServer(('127.0.0.1', port), handler(app))
    print(f'http://127.0.0.1:{port}  (work {work})', flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()
