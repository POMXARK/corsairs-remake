#!/usr/bin/env python3
"""diskview — просмотр занятого места в стиле WizTree (дерево, карта, «старое»).

Запуск:  python diskview.py [--port 8770] [--no-browser]
Открывает страницу в браузере. Ничего не удаляет: только сканирует и показывает.
Даты берутся из NTFS: создание (ctime), изменение (mtime), последний доступ (atime).
Доступ пишется, если `fsutil behavior query disablelastaccess` = 0 или 2 (2 = система
сама включает); антивирус и индексатор могут его обновлять, поэтому изменению доверяют больше.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.setrecursionlimit(10000)
REPARSE = 0x400  # junction / symlink / облачный placeholder — не заходим


class Dir:
    __slots__ = ("name", "size", "files", "t", "dirs", "fl", "err")

    def __init__(self, name, ctime):
        self.name = name
        self.size = 0
        self.files = 0
        self.t = [ctime, 0.0, 0.0]  # создана, новейшее изменение внутри, новейший доступ внутри
        self.dirs = {}
        self.fl = []  # крупные файлы: (name, size, ctime, mtime, atime)
        self.err = False


class Scan:
    def __init__(self):
        self.state = "idle"
        self.root = None
        self.root_path = ""
        self.files = 0
        self.bytes = 0
        self.cur = ""
        self.t0 = 0.0
        self.elapsed = 0.0
        self.cancel = False
        self.errors = 0
        self.keep = 1 << 20

    def run(self, path, keep_mb):
        self.state = "scanning"
        self.cancel = False
        self.files = self.bytes = self.errors = 0
        self.keep = int(keep_mb * (1 << 20))
        self.root_path = path
        self.t0 = time.time()
        try:
            st = os.stat(path)
            self.root = self._dir(path, path, st.st_ctime)
            self.state = "cancelled" if self.cancel else "done"
        except OSError as e:
            self.state = "error: %s" % e
        self.elapsed = time.time() - self.t0

    def _dir(self, path, name, ctime):
        d = Dir(name, ctime)
        self.cur = path
        try:
            it = os.scandir(path)
        except OSError:
            d.err = True
            self.errors += 1
            return d
        with it:
            for e in it:
                if self.cancel:
                    break
                try:
                    s = e.stat(follow_symlinks=False)
                    if getattr(s, "st_file_attributes", 0) & REPARSE or e.is_symlink():
                        continue
                    if e.is_dir(follow_symlinks=False):
                        sub = self._dir(e.path, e.name, s.st_ctime)
                        d.dirs[e.name] = sub
                        d.size += sub.size
                        d.files += sub.files
                        d.t[1] = max(d.t[1], sub.t[1])
                        d.t[2] = max(d.t[2], sub.t[2])
                    else:
                        d.size += s.st_size
                        d.files += 1
                        self.files += 1
                        self.bytes += s.st_size
                        d.t[1] = max(d.t[1], s.st_mtime)
                        d.t[2] = max(d.t[2], s.st_atime)
                        if s.st_size >= self.keep:
                            d.fl.append((e.name, s.st_size, s.st_ctime, s.st_mtime, s.st_atime))
                except OSError:
                    self.errors += 1
        return d

    def find(self, path):
        if self.root is None:
            return None
        if path == self.root_path:
            return self.root
        pre = self.root_path.rstrip("\\/") + os.sep
        if not path.startswith(pre):
            return None
        d = self.root
        for part in path[len(pre):].split(os.sep):
            if part == "":
                continue
            d = d.dirs.get(part)
            if d is None:
                return None
        return d


SC = Scan()


def jdir(d, path):
    return {"name": d.name if path != SC.root_path else path, "path": path, "dir": True,
            "size": d.size, "files": d.files, "t": d.t, "err": d.err}


def jfile(f, parent):
    return {"name": f[0], "path": os.path.join(parent, f[0]), "dir": False,
            "size": f[1], "files": 1, "t": [f[2], f[3], f[4]]}


def children(path, limit):
    d = SC.find(path)
    if d is None:
        return None
    items = [jdir(c, os.path.join(path, n)) for n, c in d.dirs.items()]
    items += [jfile(f, path) for f in d.fl]
    items.sort(key=lambda x: -x["size"])
    rest = d.size - sum(i["size"] for i in items)
    out = items[:limit]
    hidden = sum(i["size"] for i in items[limit:])
    if rest + hidden > 0:
        out.append({"name": "(мелкие файлы и остальное)", "path": "", "dir": False, "misc": True,
                    "size": rest + hidden, "files": 0, "t": [0, 0, 0]})
    return {"node": jdir(d, path), "children": out}


def stale(field, years, min_size, limit):
    """Самые внешние папки/файлы, к которым не прикасались дольше срока."""
    idx = {"c": 0, "m": 1, "a": 2}[field]
    cutoff = time.time() - years * 365.25 * 86400
    res = []

    def walk(d, path):
        for n, c in d.dirs.items():
            p = os.path.join(path, n)
            if c.size >= min_size and c.files > 0 and 0 < c.t[idx] < cutoff:
                res.append(jdir(c, p))
            else:
                walk(c, p)
        for f in d.fl:
            if f[1] >= min_size and f[2 + idx] < cutoff:
                res.append(jfile(f, path))

    if SC.root:
        walk(SC.root, SC.root_path)
    res.sort(key=lambda x: -x["size"])
    return {"total": sum(r["size"] for r in res), "count": len(res), "items": res[:limit]}


def drives():
    if os.name != "nt":
        return ["/"]
    return ["%s:\\" % c for c in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists("%s:\\" % c)]


def reveal(path):
    d = SC.find(os.path.dirname(path)) if path else None
    if d is None and SC.find(path) is None:
        return False
    if os.name == "nt":
        subprocess.Popen(["explorer", "/select,", path])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) or path])
    return True


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, code=200, ctype="application/json"):
        b = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/":
            return self.send(PAGE.encode(), ctype="text/html")
        if u.path == "/api/drives":
            return self.send({"drives": drives(), "sep": os.sep})
        if u.path == "/api/status":
            el = time.time() - SC.t0 if SC.state == "scanning" else SC.elapsed
            return self.send({"state": SC.state, "files": SC.files, "bytes": SC.bytes, "cur": SC.cur,
                              "elapsed": el, "errors": SC.errors, "root": SC.root_path})
        if u.path == "/api/children":
            r = children(q.get("path", SC.root_path), int(q.get("limit", 400)))
            return self.send(r if r else {"error": "нет такой папки"}, 200 if r else 404)
        if u.path == "/api/stale":
            return self.send(stale(q.get("field", "m"), float(q.get("years", 1)),
                                   float(q.get("min", 100)) * (1 << 20), int(q.get("limit", 500))))
        self.send({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        b = self.body()
        if u.path == "/api/scan":
            if SC.state == "scanning":
                return self.send({"error": "уже идёт"}, 409)
            p = b.get("path", "")
            if not os.path.isdir(p):
                return self.send({"error": "нет такой папки"}, 400)
            threading.Thread(target=SC.run, args=(p, float(b.get("keep", 1))), daemon=True).start()
            return self.send({"ok": True})
        if u.path == "/api/cancel":
            SC.cancel = True
            return self.send({"ok": True})
        if u.path == "/api/reveal":
            return self.send({"ok": reveal(b.get("path", ""))})
        self.send({"error": "not found"}, 404)


PAGE = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>DiskView</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#fff;--fg:#1d2330;--mut:#667;--line:#dde1ea;--pan:#f4f6fa;--acc:#2563eb;--sel:#dbe7ff}
@media (prefers-color-scheme:dark){:root{--bg:#14171d;--fg:#e4e8f0;--mut:#8a93a6;--line:#2a303b;--pan:#1b2029;--acc:#6ea0ff;--sel:#26365a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.4 system-ui,Segoe UI,sans-serif;display:flex;flex-direction:column;height:100vh}
header{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:8px 12px;background:var(--pan);border-bottom:1px solid var(--line)}
input,select,button{font:inherit;color:inherit;background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:4px 8px}
button{cursor:pointer}button.p{background:var(--acc);color:#fff;border-color:var(--acc)}button:disabled{opacity:.5}
#path{width:320px}#st{color:var(--mut);padding:4px 12px;border-bottom:1px solid var(--line);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav{display:flex;gap:2px;padding:6px 12px 0}nav button{border-bottom:none;border-radius:5px 5px 0 0}nav button.on{background:var(--acc);color:#fff;border-color:var(--acc)}
main{flex:1;overflow:auto;position:relative;border-top:1px solid var(--line)}
table{border-collapse:collapse;width:100%}th,td{padding:2px 8px;white-space:nowrap;text-align:right}th:first-child,td:first-child{text-align:left}
th{position:sticky;top:0;background:var(--pan);border-bottom:1px solid var(--line);font-weight:600}
tr.r:hover{background:var(--pan)}tr.sel{background:var(--sel)!important}
td.nm{max-width:520px;overflow:hidden;text-overflow:ellipsis}.tg{display:inline-block;width:16px;color:var(--mut);cursor:pointer}
.bar{display:inline-block;height:9px;background:var(--acc);opacity:.6;vertical-align:middle;border-radius:2px}
.old{color:#d33}.new{color:#2a9d4a}
#tm{display:block;width:100%;height:100%}#crumb{position:absolute;left:8px;top:6px;background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:2px 8px;z-index:2}
#tip{position:fixed;pointer-events:none;background:#000d;color:#fff;padding:5px 8px;border-radius:5px;font-size:12px;display:none;z-index:9;white-space:pre}
footer{display:flex;gap:8px;align-items:center;padding:6px 12px;background:var(--pan);border-top:1px solid var(--line)}
footer span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.legend{display:flex;align-items:center;gap:4px;color:var(--mut)}.legend i{width:90px;height:8px;background:linear-gradient(90deg,hsl(130,55%,45%),hsl(65,55%,45%),hsl(0,55%,45%))}
</style></head><body>
<header>
 <span id="drv"></span>
 <input id="path" placeholder="Что сканировать: C:\ или любая папка">
 <label>файлы от <input id="keep" type="number" value="1" min="0" step="0.5" style="width:60px"> МБ</label>
 <button class="p" id="go">Сканировать</button><button id="stop" disabled>Стоп</button>
 <label>Возраст по <select id="field"><option value="m">изменению</option><option value="a">доступу</option><option value="c">созданию</option></select></label>
 <span class="legend">свежее<i></i>старше 3 лет</span>
</header>
<div id="st">Выберите диск или папку и нажмите «Сканировать».</div>
<nav><button data-v="tree" class="on">Папки</button><button data-v="map">Карта</button><button data-v="old">Старое</button></nav>
<main id="main"></main>
<div id="tip"></div>
<footer><span id="sel">—</span><button id="rev" disabled>Показать в Проводнике</button><button id="cp" disabled>Копировать путь</button><button id="tomap" disabled>Открыть на карте</button></footer>
<script>
const $=s=>document.querySelector(s);let sep="\\",view="tree",sel=null,mapPath=null,poll=null,rootPath="";
const fmt=b=>{const u=["Б","КБ","МБ","ГБ","ТБ"];let i=0;while(b>=1024&&i<4){b/=1024;i++}return (i?b.toFixed(b<10?2:1):b)+" "+u[i]};
const dt=t=>t?new Date(t*1000).toISOString().slice(0,10):"";
const fi=()=>({c:0,m:1,a:2}[$("#field").value]);
const age=t=>t?(Date.now()/1000-t)/31557600:0;
const col=t=>{const h=130*(1-Math.min(age(t)/3,1));return `hsl(${h},55%,45%)`};
const esc=s=>s.replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
async function api(u,b){const r=await fetch(u,b?{method:"POST",body:JSON.stringify(b)}:{});return r.json()}
(async()=>{const d=await api("/api/drives");sep=d.sep;$("#drv").innerHTML=d.drives.map(x=>`<button data-d="${esc(x)}">${esc(x)}</button>`).join("");
 $("#path").value=d.drives[0];$("#drv").onclick=e=>{if(e.target.dataset.d)$("#path").value=e.target.dataset.d};
 const s=await api("/api/status");if(s.state=="done"){rootPath=s.root;$("#path").value=s.root;show(s)}})();
$("#go").onclick=async()=>{const r=await api("/api/scan",{path:$("#path").value.trim(),keep:+$("#keep").value});if(r.error)return alert(r.error);
 $("#go").disabled=true;$("#stop").disabled=false;poll=setInterval(tick,500)};
$("#stop").onclick=()=>api("/api/cancel",{});
async function tick(){const s=await api("/api/status");
 $("#st").textContent=s.state=="scanning"?`Сканирую… ${s.files.toLocaleString()} файлов, ${fmt(s.bytes)}, ${s.elapsed.toFixed(0)} с — ${s.cur}`:`${s.state}: ${s.files.toLocaleString()} файлов, ${fmt(s.bytes)}, ${s.elapsed.toFixed(1)} с, недоступных папок: ${s.errors}`;
 if(s.state!="scanning"){clearInterval(poll);$("#go").disabled=false;$("#stop").disabled=true;if(s.state=="done"||s.state=="cancelled")show(s)}}
function show(s){rootPath=s.root;mapPath=s.root;$("#st").textContent=`${s.root}: ${s.files.toLocaleString()} файлов, ${fmt(s.bytes)}, ${s.elapsed.toFixed(1)} с, недоступных папок: ${s.errors}`;render()}
document.querySelector("nav").onclick=e=>{if(!e.target.dataset.v)return;view=e.target.dataset.v;document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("on",b==e.target));render()};
$("#field").onchange=render;
function render(){if(!rootPath)return;({tree:rTree,map:rMap,old:rOld})[view]()}
function pick(n){sel=n;$("#sel").textContent=n?`${n.path||n.name} — ${fmt(n.size)}`:"—";const ok=n&&n.path;$("#rev").disabled=$("#cp").disabled=!ok;$("#tomap").disabled=!(n&&n.dir)}
$("#rev").onclick=()=>sel&&api("/api/reveal",{path:sel.path});
$("#cp").onclick=()=>sel&&navigator.clipboard.writeText(sel.path);
$("#tomap").onclick=()=>{if(sel&&sel.dir){mapPath=sel.path;document.querySelector('nav [data-v=map]').click()}};
// ---- дерево
async function rTree(){const m=$("#main");m.innerHTML=`<table><thead><tr><th>Имя<th>Размер<th>% от родителя<th>Файлов<th>Создан<th>Изменён<th>Доступ</thead><tbody id="tb"></tbody></table>`;
 const d=await api("/api/children?path="+encodeURIComponent(rootPath));addRows($("#tb"),d.children,0,d.node.size,null)}
function addRows(tb,items,lvl,psize,after){let prev=after;for(const n of items){const tr=document.createElement("tr");tr.className="r";tr.n=n;tr.lvl=lvl;
 const pct=psize?n.size/psize*100:0,f=fi();
 tr.innerHTML=`<td class="nm" style="padding-left:${8+lvl*16}px" title="${esc(n.path)}"><span class="tg">${n.dir&&n.files?"▸":""}</span>${n.dir?"📁":n.misc?"…":"📄"} ${esc(n.name)}<td>${fmt(n.size)}<td><span class="bar" style="width:${Math.round(pct*0.8)}px"></span> ${pct.toFixed(1)}%<td>${n.misc?"":n.files.toLocaleString()}<td>${dt(n.t[0])}<td style="color:${col(n.t[1])}">${dt(n.t[1])}<td style="color:${col(n.t[2])}">${dt(n.t[2])}`;
 tr.onclick=e=>{document.querySelectorAll("tr.sel").forEach(x=>x.classList.remove("sel"));tr.classList.add("sel");pick(n);if(e.target.classList.contains("tg"))toggle(tr)};
 tr.ondblclick=()=>n.dir&&toggle(tr);
 if(prev)prev.after(tr);else tb.appendChild(tr);prev=tr}}
async function toggle(tr){const n=tr.n;if(!n.dir||!n.files)return;const tg=tr.querySelector(".tg");
 if(tr.open){let nx=tr.nextSibling;while(nx&&nx.lvl>tr.lvl){const x=nx;nx=nx.nextSibling;x.remove()}tr.open=false;tg.textContent="▸";return}
 const d=await api("/api/children?path="+encodeURIComponent(n.path)+"&limit=200");addRows(tr.parentNode,d.children,tr.lvl+1,n.size,tr);tr.open=true;tg.textContent="▾"}
// ---- карта
async function rMap(){const m=$("#main");m.innerHTML=`<div id="crumb"></div><canvas id="tm"></canvas>`;const cv=$("#tm");cv.width=m.clientWidth;cv.height=m.clientHeight;
 const d=await api("/api/children?path="+encodeURIComponent(mapPath)+"&limit=300");const ctx=cv.getContext("2d");
 const parts=mapPath.slice(rootPath.length).split(sep).filter(Boolean);let acc=rootPath.replace(/[\\\/]$/,"");
 $("#crumb").innerHTML=`<a href="#" data-p="${esc(rootPath)}">${esc(rootPath)}</a>`+parts.map(p=>{acc+=sep+p;return ` ${sep} <a href="#" data-p="${esc(acc)}">${esc(p)}</a>`}).join("");
 $("#crumb").onclick=e=>{e.preventDefault();if(e.target.dataset.p){mapPath=e.target.dataset.p;rMap()}};
 const items=d.children.filter(x=>x.size>0).map(x=>({...x,v:x.size}));const rects=items.length?squarify(items,0,30,cv.width,cv.height-30):[];const f=fi();
 for(const r of rects){const n=r.it;ctx.fillStyle=n.misc?"#778":col(n.t[f]);ctx.fillRect(r.x,r.y,r.w,r.h);ctx.strokeStyle="#0006";ctx.strokeRect(r.x+.5,r.y+.5,r.w-1,r.h-1);
  if(r.w>60&&r.h>28){ctx.fillStyle="#fff";ctx.font="12px system-ui";ctx.save();ctx.beginPath();ctx.rect(r.x,r.y,r.w,r.h);ctx.clip();ctx.fillText(n.name,r.x+4,r.y+14);ctx.fillText(fmt(n.size),r.x+4,r.y+28);ctx.restore()}}
 const at=e=>{const b=cv.getBoundingClientRect(),x=e.clientX-b.left,y=e.clientY-b.top;return rects.find(r=>x>=r.x&&x<r.x+r.w&&y>=r.y&&y<r.y+r.h)};
 const tip=$("#tip");cv.onmousemove=e=>{const r=at(e);if(!r){tip.style.display="none";return}const n=r.it;tip.style.display="block";tip.style.left=e.clientX+12+"px";tip.style.top=e.clientY+12+"px";
  tip.textContent=`${n.path||n.name}\n${fmt(n.size)}${n.files>1?"  ·  файлов: "+n.files:""}\nсоздан ${dt(n.t[0])}  изм. ${dt(n.t[1])}  доступ ${dt(n.t[2])}`};
 cv.onmouseleave=()=>tip.style.display="none";cv.onclick=e=>{const r=at(e);if(r)pick(r.it)};
 cv.ondblclick=e=>{const r=at(e);if(r&&r.it.dir&&r.it.files){mapPath=r.it.path;rMap()}}}
function squarify(items,x,y,w,h){const tot=items.reduce((a,b)=>a+b.v,0),sc=w*h/tot,out=[];items.forEach(i=>i.a=i.v*sc);
 const worst=(row,side)=>{const s=row.reduce((a,b)=>a+b.a,0),mx=Math.max(...row.map(r=>r.a)),mn=Math.min(...row.map(r=>r.a));return Math.max(side*side*mx/(s*s),s*s/(side*side*mn))};
 let rc={x,y,w,h},i=0;while(i<items.length){const side=Math.min(rc.w,rc.h);let row=[items[i++]];
  while(i<items.length){const c=row.concat(items[i]);if(worst(c,side)<=worst(row,side)){row=c;i++}else break}
  const s=row.reduce((a,b)=>a+b.a,0);
  if(rc.w>=rc.h){const cw=s/rc.h;let yy=rc.y;for(const r of row){const hh=r.a/cw;out.push({it:r,x:rc.x,y:yy,w:cw,h:hh});yy+=hh}rc={x:rc.x+cw,y:rc.y,w:rc.w-cw,h:rc.h}}
  else{const rh=s/rc.w;let xx=rc.x;for(const r of row){const ww=r.a/rh;out.push({it:r,x:xx,y:rc.y,w:ww,h:rh});xx+=ww}rc={x:rc.x,y:rc.y+rh,w:rc.w,h:rc.h-rh}}}
 return out}
// ---- старое
async function rOld(){const m=$("#main");m.innerHTML=`<div style="padding:8px 12px">Не трогали дольше <input id="yrs" type="number" value="1" step="0.5" min="0" style="width:60px"> лет (по полю «Возраст по» сверху), размер от <input id="mn" type="number" value="100" style="width:70px"> МБ <button id="ap" class="p">Показать</button> <b id="sum"></b></div><div id="ot"></div>`;
 const run=async()=>{const d=await api(`/api/stale?field=${$("#field").value}&years=${$("#yrs").value}&min=${$("#mn").value}`);
  $("#sum").textContent=`найдено ${d.count}, всего ${fmt(d.total)}`;
  $("#ot").innerHTML=`<table><thead><tr><th>Путь<th>Размер<th>Файлов<th>Создан<th>Изменён<th>Доступ</thead><tbody>`+d.items.map((n,i)=>`<tr class="r" data-i="${i}"><td class="nm" title="${esc(n.path)}">${n.dir?"📁":"📄"} ${esc(n.path)}<td>${fmt(n.size)}<td>${n.files.toLocaleString()}<td>${dt(n.t[0])}<td>${dt(n.t[1])}<td>${dt(n.t[2])}`).join("")+`</tbody></table>`;
  $("#ot").onclick=e=>{const tr=e.target.closest("tr.r");if(!tr)return;document.querySelectorAll("tr.sel").forEach(x=>x.classList.remove("sel"));tr.classList.add("sel");pick(d.items[tr.dataset.i])}};
 $("#ap").onclick=run;run()}
addEventListener("resize",()=>view=="map"&&rMap());
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--scan", help="сразу сканировать папку (для проверки)")
    a = ap.parse_args()
    if a.scan:
        SC.run(a.scan, 1)
        print(SC.state, SC.files, SC.bytes, "%.1fs" % SC.elapsed, "errors", SC.errors)
        return
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    url = "http://127.0.0.1:%d/" % a.port
    print("DiskView:", url, "(Ctrl+C — выход)")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
