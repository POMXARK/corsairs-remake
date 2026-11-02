#!/usr/bin/env python3
"""diskview — просмотр занятого места в стиле WizTree (дерево, карта, «старое»).

Запуск:  python diskview.py [--port 8770] [--no-browser]
Открывает страницу в браузере. Ничего не удаляет: только сканирует и показывает.
Даты берутся из NTFS: создание (ctime), изменение (mtime), последний доступ (atime).
Доступ пишется, если `fsutil behavior query disablelastaccess` = 0 или 2 (2 = система
сама включает); антивирус и индексатор могут его обновлять, поэтому изменению доверяют больше.
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import urllib.request
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.setrecursionlimit(10000)
REPARSE = 0x400  # junction / symlink / облачный placeholder — не заходим


CATS = ["звуки и сэмплы", "библиотеки сэмплеров", "проекты музыки", "видео", "изображения", "документы",
        "архивы и образы", "программы и dll", "игровые данные", "3D и проекты", "прочее"]
_E = {}
for i, exts in enumerate((
        "wav aif aiff mp3 flac ogg m4a wma mid midi",
        "nkx nxs ncw nkc nki nkm nks nkr stw exs sf2 sfz",
        "flp als logic cpr ptx rpp song reapeaks",
        "mkv mp4 avi mov wmv webm flv m4v",
        "jpg jpeg png gif bmp tga tif tiff psd webp raw dds",
        "pdf doc docx xls xlsx ppt pptx txt rtf odt md epub djvu",
        "zip rar 7z iso gz tar bz2 img cab",
        "exe dll msi sys lib ocx vst vst3 bin",
        "big pak bsa gm an tx wad pck vpk",
        "blend fbx obj max 3ds ma mb stl glb gltf unitypackage")):
    for e in exts.split():
        _E["." + e] = i
NCAT = len(CATS)
PROTECTED_TOP = {"windows", "program files", "program files (x86)", "programdata", "users", "$recycle.bin",
                 "system volume information", "recovery", "boot", "perflogs", "documents and settings"}
USER_STD = {"documents", "desktop", "pictures", "music", "videos", "downloads", "appdata", "saved games"}


class Dir:
    __slots__ = ("name", "size", "files", "t", "dirs", "fl", "err", "cat")

    def __init__(self, name, ctime):
        self.name = name
        self.size = 0
        self.files = 0
        self.t = [ctime, 0.0, 0.0]  # создана, новейшее изменение внутри, новейший доступ внутри
        self.dirs = {}
        self.fl = []  # крупные файлы: (name, size, ctime, mtime, atime)
        self.err = False
        self.cat = None


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
            if self.state == "done":
                save_cards()
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
                        if sub.cat:
                            if d.cat is None:
                                d.cat = [0] * NCAT
                            for i, v in enumerate(sub.cat):
                                d.cat[i] += v
                    else:
                        d.size += s.st_size
                        d.files += 1
                        self.files += 1
                        self.bytes += s.st_size
                        if d.cat is None:
                            d.cat = [0] * NCAT
                        d.cat[_E.get(os.path.splitext(e.name)[1].lower(), NCAT - 1)] += s.st_size
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


_PROGS = None
_PROGX = []


def programs():
    """Установленные программы из реестра Windows: (имя, папка в нижнем регистре)."""
    global _PROGS
    if _PROGS is not None:
        return _PROGS
    _PROGS = []
    if os.name != "nt":
        return _PROGS
    import winreg
    sub = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, sub), (winreg.HKEY_LOCAL_MACHINE, sub.replace("SOFTWARE", "SOFTWARE\\WOW6432Node")),
                      (winreg.HKEY_CURRENT_USER, sub)):
        try:
            k = winreg.OpenKey(hive, key)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                with winreg.OpenKey(k, winreg.EnumKey(k, i)) as a:
                    name = winreg.QueryValueEx(a, "DisplayName")[0]
                    loc = winreg.QueryValueEx(a, "InstallLocation")[0].strip().strip('"').rstrip("\\/")
                    if name and len(loc) > 5:
                        _PROGS.append((name, loc.lower()))
                    exe, pub, kb = "", "", 0
                    for fld in ("DisplayIcon", "Publisher", "EstimatedSize"):
                        try:
                            v = winreg.QueryValueEx(a, fld)[0]
                        except OSError:
                            continue
                        if fld == "DisplayIcon":
                            v = str(v).strip().strip('"')
                            v = v.rsplit(",", 1)[0].strip().strip('"') if "," in v else v
                            exe = v if v.lower().endswith(".exe") and os.path.isfile(v) else ""
                        elif fld == "Publisher":
                            pub = str(v)
                        else:
                            kb = int(v)
                    if name and (exe or len(loc) > 5):
                        _PROGX.append({"name": name, "publisher": pub, "path": exe or loc, "dir": not exe, "size": kb * 1024})
            except OSError:
                pass
    return _PROGS


def program_list():
    programs()
    seen, out = set(), []
    for p in sorted(_PROGX, key=lambda x: x["name"].lower()):
        if p["name"] not in seen and not p["name"].startswith(("Microsoft Visual C++", "Update for", "Security Update", "${{")):
            seen.add(p["name"])
            out.append(p)
    return out


def program_of(path):
    p = path.lower().rstrip("\\/")
    for name, loc in programs():
        if p == loc or p.startswith(loc + os.sep):
            return name
        if loc.startswith(p + os.sep):
            return name + " (внутри)"
    return ""


def protected(path):
    """Системные места: целиком не предлагаются к удалению."""
    p = os.path.normpath(path)
    drive, rest = os.path.splitdrive(p)
    parts = [x for x in rest.replace("\\", "/").split("/") if x]
    if not parts or p == os.path.normpath(SC.root_path):
        return True
    if len(parts) == 1 and parts[0].lower() in PROTECTED_TOP:
        return True
    low = [x.lower() for x in parts]
    if len(parts) >= 2 and low[0] == "users" and (len(parts) == 2 or (len(parts) == 3 and low[2] in USER_STD)):
        return True
    return False


def cats_of(d, n=3):
    if not d.cat:
        return []
    top = sorted(((CATS[i], v) for i, v in enumerate(d.cat) if v), key=lambda x: -x[1])
    return [[k, v] for k, v in top[:n]]


def risk_of(d, path, prog):
    if protected(path):
        return 2
    if prog:
        return 1
    if d.cat and d.size and d.cat[7] / d.size > 0.5:
        return 1
    return 0


def jdir(d, path):
    prog = program_of(path) if os.name == "nt" else ""
    return {"name": d.name if path != SC.root_path else path, "path": path, "dir": True,
            "size": d.size, "files": d.files, "t": d.t, "err": d.err, "cats": cats_of(d),
            "prog": prog, "risk": risk_of(d, path, prog),
            "tags": LIB["tags"].get(path, {}).get("tags", []), "note": LIB["tags"].get(path, {}).get("note", ""),
            "colls": _PCOLL.get(path, [])}


def jfile(f, parent):
    return {"name": f[0], "path": os.path.join(parent, f[0]), "dir": False,
            "size": f[1], "files": 1, "t": [f[2], f[3], f[4]], "cats": [], "prog": "", "risk": 0,
            "tags": LIB["tags"].get(os.path.join(parent, f[0]), {}).get("tags", []), "note": "", "colls": []}


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


def detach(path):
    """Убрать узел из дерева и вычесть его размер у предков."""
    pre = SC.root_path.rstrip("\\/") + os.sep
    if SC.root is None or not path.startswith(pre):
        return
    chain, d = [SC.root], SC.root
    parts = [x for x in path[len(pre):].split(os.sep) if x]
    for part in parts[:-1]:
        d = d.dirs.get(part)
        if d is None:
            return
        chain.append(d)
    node = chain[-1].dirs.pop(parts[-1], None) if parts else None
    if node is None:
        chain[-1].fl = [f for f in chain[-1].fl if f[0] != parts[-1]]
        return
    for a in chain:
        a.size -= node.size
        a.files -= node.files
        if node.cat and a.cat:
            for i, v in enumerate(node.cat):
                a.cat[i] -= v


def check_target(path):
    d = SC.find(path)
    if d is None or protected(path):
        return "это место защищено или не из сканирования"
    if SC.state == "scanning":
        return "идёт сканирование"
    return ""


def to_trash(path):
    err = check_target(path)
    if err:
        return {"ok": False, "error": err}
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class OP(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                        ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("abort", wintypes.BOOL),
                        ("map", ctypes.c_void_p), ("title", wintypes.LPCWSTR)]
        # FOF_ALLOWUNDO | FOF_WANT_NUKE_WARNING: Windows сам спросит, если корзина не вместит и файлы пропадут насовсем
        op = OP(None, 3, path + "\0", None, 0x40 | 0x4000, False, None, None)
        r = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if r != 0 or op.abort:
            return {"ok": False, "error": "корзина отказала (код %d)" % r}
    elif shutil.which("gio"):
        if subprocess.run(["gio", "trash", path]).returncode != 0:
            return {"ok": False, "error": "gio trash не сработал"}
    else:
        return {"ok": False, "error": "нет корзины на этой системе"}
    if os.path.exists(path):
        return {"ok": False, "error": "объект остался на месте"}
    detach(path)
    return {"ok": True}


def hard_delete(path, confirm):
    err = check_target(path)
    if err:
        return {"ok": False, "error": err}
    if confirm != os.path.basename(path.rstrip("\\/")):
        return {"ok": False, "error": "имя для подтверждения не совпало"}
    errs = []

    def onerr(fn, p, exc):
        try:
            os.chmod(p, 0o700)
            fn(p)
        except OSError as e:
            errs.append(str(e))
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, onerror=onerr)
    else:
        try:
            os.remove(path)
        except OSError as e:
            errs.append(str(e))
    if os.path.exists(path):
        return {"ok": False, "error": "не всё удалено: %s" % (errs[0] if errs else "?")}
    detach(path)
    return {"ok": True}


DATA = os.environ.get("DISKVIEW_DATA") or os.path.join(os.path.expanduser("~"), ".diskview")


def _jload(name, default):
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _jsave(name, obj):
    os.makedirs(DATA, exist_ok=True)
    p = os.path.join(DATA, name)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(p + ".tmp", p)


CFG = _jload("config.json", {"profiles": [{"id": "ollama", "name": "Ollama (локально)", "type": "ollama",
                                              "url": "http://127.0.0.1:11434", "key": "", "model": ""}], "active": "ollama"})


def profile(pid=None):
    for p in CFG["profiles"]:
        if p["id"] == (pid or CFG["active"]):
            return p
    return CFG["profiles"][0]


def http_json(url, body=None, key="", timeout=300):
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def llm(prompt, model="", max_tokens=300, temp=0.2, prof=None, timeout=300):
    """Один вызов модели через активный профиль: Ollama или любой OpenAI-совместимый сервер."""
    p = prof or profile()
    model = model or p.get("model", "")
    url = p["url"].rstrip("/")
    if p["type"] == "ollama":
        r = http_json(url + "/api/generate", {"model": model, "prompt": prompt, "stream": False, "think": False,
                                              "options": {"temperature": temp, "num_predict": max_tokens}}, p.get("key", ""), timeout)
        text = r.get("response", "")
    else:
        r = http_json(url + "/chat/completions", {"model": model, "messages": [{"role": "user", "content": prompt}],
                                                  "temperature": temp, "max_tokens": max_tokens}, p.get("key", ""), timeout)
        text = r["choices"][0]["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def list_models(p):
    url = p["url"].rstrip("/")
    try:
        if p["type"] == "ollama":
            return [m["name"] for m in http_json(url + "/api/tags", None, p.get("key", ""), 5)["models"]]
        return sorted(m["id"] for m in http_json(url + "/models", None, p.get("key", ""), 8)["data"])
    except Exception:
        return []


_PREF = [r"^qwen3:8b", r"^qwen3:4b", r"^qwen3:14b", r"^qwen3\.5", r"^qwen2\.5:(7|14)b", r"^llama3\.[123]:8b", r"^gemma\d*:(4|9|12)b", r"^mistral", r"^qwen3"]


def recommend(ms):
    """Для классификации папок и ответов по карточкам нужна небольшая инструкционная модель
    (русский, JSON, быстро): qwen3 8b/4b; coder/vl/embed-модели не годятся."""
    ok = [m for m in ms if not re.search(r"coder|vl|embed|bge|nomic|rerank|whisper|image", m, re.I)]
    for pat in _PREF:
        for m in ok:
            if re.search(pat, m):
                return m
    return ok[0] if ok else ""


def models():
    return list_models(profile())


def cfg_public():
    return {"active": CFG["active"], "profiles": [dict(p, key="***" if p.get("key") else "") for p in CFG["profiles"]]}


def cfg_action(b):
    a = b.get("action")
    if a == "save":
        n = b.get("profile", {})
        if n.get("type") not in ("ollama", "openai") or not n.get("url", "").startswith(("http://", "https://")):
            return {"ok": False, "error": "нужен тип и адрес http(s)://…"}
        old = next((p for p in CFG["profiles"] if p["id"] == n.get("id")), None)
        n = {"id": n.get("id") or "p%d" % int(time.time() * 1000), "name": n.get("name") or n["url"], "type": n["type"],
             "url": n["url"].strip(), "key": (old or {}).get("key", "") if n.get("key") == "***" else n.get("key", ""),
             "model": n.get("model", "").strip()}
        if old:
            CFG["profiles"][CFG["profiles"].index(old)] = n
        else:
            CFG["profiles"].append(n)
        CFG["active"] = CFG["active"] if old else n["id"]
        res = {"ok": True, "id": n["id"]}
    elif a == "delete":
        if len(CFG["profiles"]) > 1:
            CFG["profiles"] = [p for p in CFG["profiles"] if p["id"] != b.get("id")]
            if CFG["active"] == b.get("id"):
                CFG["active"] = CFG["profiles"][0]["id"]
        res = {"ok": True}
    elif a == "activate":
        if any(p["id"] == b.get("id") for p in CFG["profiles"]):
            CFG["active"] = b["id"]
        res = {"ok": True}
    else:
        return {"ok": False, "error": "неизвестное действие"}
    _jsave("config.json", CFG)
    return res


def cfg_test(b):
    """Проверка профиля из формы (без сохранения). Ключ '***' берётся из сохранённого."""
    n = dict(b.get("profile", {}))
    old = next((p for p in CFG["profiles"] if p["id"] == n.get("id")), None)
    if n.get("key") == "***":
        n["key"] = (old or {}).get("key", "")
    out = {"models": list_models(n)}
    try:
        out["text"] = llm("Ответь одним словом: ок", n.get("model", ""), 20, 0, n, 60)
        out["ok"] = True
    except Exception as e:
        out["ok"], out["error"] = False, str(e)
    return out


def _txt(h):
    import html
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or ""))).strip()


def web_name(path):
    """Запрос для поиска: для exe/папки с программой — имя без расширения плюс метаданные Windows, если есть."""
    base = re.split(r"[\\/]", path.rstrip("/\\"))[-1]
    return re.sub(r"\.(exe|msi|bat|lnk)$", "", base, flags=re.I).replace("_", " ").strip()


def web_get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "diskview/1.0 (local tool)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def web_lookup(q):
    """Описание и картинка из открытых источников: Википедия (ru, en) и DuckDuckGo. Наружу уходит только запрос q."""
    from urllib.parse import quote
    out = {"query": q, "title": "", "text": "", "image": "", "url": "", "results": []}
    for lang in ("ru", "en"):
        try:
            sr = json.loads(web_get("https://%s.wikipedia.org/w/api.php?action=query&list=search&srlimit=1&format=json&srsearch=%s"
                                    % (lang, quote(q + " software"))))["query"]["search"]
            if not sr:
                continue
            sm = json.loads(web_get("https://%s.wikipedia.org/api/rest_v1/page/summary/%s" % (lang, quote(sr[0]["title"].replace(" ", "_")))))
            if sm.get("extract") and q.lower().split()[0] in (sm.get("title", "") + sm["extract"]).lower():
                out.update(title=sm.get("title", ""), text=sm["extract"], url=sm.get("content_urls", {}).get("desktop", {}).get("page", ""),
                           image=(sm.get("thumbnail") or {}).get("source", ""))
                break
        except Exception:
            pass
    try:
        h = web_get("https://html.duckduckgo.com/html/?q=" + quote(q + " что это за программа"))
        for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>', h, re.S):
            u = m.group(1)
            mu = re.search(r"uddg=([^&]+)", u)
            if mu:
                from urllib.parse import unquote
                u = unquote(mu.group(1))
            out["results"].append({"title": _txt(m.group(2)), "url": u, "snippet": _txt(m.group(3))})
            if len(out["results"]) >= 5:
                break
    except Exception:
        pass
    if not out["text"] and out["results"]:
        out["text"] = out["results"][0]["snippet"]
        out["title"] = out["results"][0]["title"]
        out["url"] = out["results"][0]["url"]
    return out


def web_info(path, model="", save=True):
    """Неизвестный exe/папка: найти в интернете, при наличии модели — пересказать и дать подсказки по действиям;
    описание и картинка сохраняются в библиотеку (теги пути)."""
    q = web_name(path)
    if not q:
        return {"error": "нет имени для поиска"}
    try:
        w = web_lookup(q)
    except Exception as e:
        return {"error": "интернет недоступен: %s" % e}
    if not w["text"] and not w["results"]:
        return {"error": "ничего не найдено по запросу «%s»" % q}
    facts = (w["text"] + "\n" + "\n".join("- %s: %s" % (r["title"], r["snippet"]) for r in w["results"]))[:2500]
    tips = ""
    try:
        tips = llm("Пользователь нашёл на диске «%s» (%s). Ниже выдержки из интернета. Кратко по-русски: 1) что это; 2) для чего нужно; "
                   "3) что можно сделать: оставить, запустить, удалить (безопасно ли, нужна ли для других программ). "
                   "Только по выдержкам, без выдумок; если неясно — так и скажи.\n%s" % (q, path, facts), model, 350)
    except Exception:
        pass
    w["tips"] = tips
    if save and path:
        t = LIB["tags"].setdefault(path, {"tags": [], "note": "", "size": 0, "dir": os.path.isdir(path)})
        t["web"] = {k: w[k] for k in ("query", "title", "text", "image", "url", "tips")}
        if not t.get("note"):
            t["note"] = (tips or w["text"])[:300]
        lib_touch()
    return w



def describe(path, model):
    d = SC.find(path)
    if d is None:
        return {"error": "нет такой папки"}
    f = lambda t: time.strftime("%Y-%m-%d", time.localtime(t)) if t else "?"
    subs = sorted(d.dirs.items(), key=lambda x: -x[1].size)[:10]
    big = sorted(d.fl, key=lambda x: -x[1])[:10]
    prompt = (
        "Ты помогаешь чистить диск. По метаданным папки (содержимое файлов не читается) в 2-3 предложениях "
        "по-русски скажи: что это, какой программе принадлежит, можно ли удалить, чем рискуем. "
        "Если не уверен — так и скажи.\n"
        "Путь: %s\nРазмер: %.1f ГБ, файлов: %d\nСоздана: %s, последнее изменение внутри: %s\n"
        "Типы: %s\nПодпапки: %s\nКрупные файлы: %s\nУстановленная программа: %s\n"
    ) % (path, d.size / 2**30, d.files, f(d.t[0]), f(d.t[1]),
         ", ".join("%s %.1f ГБ" % (k, v / 2**30) for k, v in cats_of(d, 5)),
         "; ".join("%s (%.1f ГБ)" % (n, c.size / 2**30) for n, c in subs) or "нет",
         "; ".join("%s (%.0f МБ)" % (x[0], x[1] / 2**20) for x in big) or "нет",
         program_of(path) or "не найдена")
    try:
        return {"text": llm(prompt, model, 300)}
    except Exception as e:
        return {"error": "модель недоступна: %s" % e}


# ---------- библиотека: коллекции, теги, карточки, помощник ----------
LIB = _jload("library.json", {"collections": [], "tags": {}})  # tags: путь -> {tags, note, size, dir}
CARDS = _jload("cards.json", [])  # сводки по папкам из последних сканирований (помощник работает без пересканирования)
_IDX = None
_PCOLL = {}


def lib_touch(save=True):
    global _IDX, _PCOLL
    _IDX = None
    _PCOLL = {}
    for c in LIB["collections"]:
        for it in c["items"]:
            _PCOLL.setdefault(it["path"], []).append(c["name"])
    if save:
        _jsave("library.json", LIB)


lib_touch(False)


def under(path, root):
    a, b = os.path.normcase(path), os.path.normcase(root.rstrip("\\/"))
    return a == b or a.startswith(b + os.sep)


def build_cards(minsize=50 << 20):
    out = []

    def walk(d, path, depth):
        subs = sorted(d.dirs.items(), key=lambda x: -x[1].size)[:8]
        top = sorted(d.fl, key=lambda x: -x[1])[:8]
        out.append({"path": path, "name": d.name if depth else path, "size": d.size, "files": d.files, "t": d.t,
                    "cats": cats_of(d, 4), "prog": program_of(path) if os.name == "nt" else "",
                    "subs": [n for n, _ in subs], "top": [f[0] for f in top]})
        for n, c in d.dirs.items():
            if c.size >= minsize or depth < 2:
                walk(c, os.path.join(path, n), depth + 1)
    walk(SC.root, SC.root_path, 0)
    out.sort(key=lambda x: -x["size"])
    return out[:30000]


def save_cards():
    global CARDS, _IDX
    if SC.root is None or SC.state != "done":
        return
    CARDS = [c for c in CARDS if not under(c["path"], SC.root_path)] + build_cards()
    _IDX = None
    _jsave("cards.json", CARDS)


def all_cards():
    have = {c["path"] for c in CARDS}
    extra = [{"path": p, "name": os.path.basename(p.rstrip("\\/")) or p, "size": v.get("size", 0), "files": 0,
              "t": [0, 0, 0], "cats": [], "prog": "", "subs": [], "top": []}
             for p, v in LIB["tags"].items() if p not in have]
    for c in LIB["collections"]:
        for it in c["items"]:
            if it["path"] not in have and it["path"] not in LIB["tags"]:
                extra.append({"path": it["path"], "name": os.path.basename(it["path"].rstrip("\\/")), "size": it.get("size", 0),
                              "files": 0, "t": [0, 0, 0], "cats": [], "prog": "", "subs": [], "top": []})
                have.add(it["path"])
    return CARDS + extra


def toks(s):
    return [t[:6] for t in re.findall(r"[^\W_]+", s.lower())]


def card_text(c):
    tg = LIB["tags"].get(c["path"], {})
    parts = [c["name"]] * 3 + c["path"].replace("\\", " ").replace("/", " ").split() + [k for k, _ in c["cats"]]
    parts += [c["prog"]] + c["subs"] + c["top"] + tg.get("tags", []) * 3 + [tg.get("note", "")]
    parts += _PCOLL.get(c["path"], []) * 2
    return " ".join(parts)


def index():
    global _IDX
    if _IDX is None:
        cards = all_cards()
        docs = [toks(card_text(c)) for c in cards]
        df = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        tf = []
        for d in docs:
            m = {}
            for t in d:
                m[t] = m.get(t, 0) + 1
            tf.append(m)
        _IDX = (cards, tf, [len(d) for d in docs], df, sum(len(d) for d in docs) / max(len(docs), 1))
    return _IDX


def search(q, k=8):
    cards, tf, ln, df, avg = index()
    qt = toks(q)
    n = len(cards)
    sc = []
    for i, m in enumerate(tf):
        s = 0.0
        for t in qt:
            f = m.get(t)
            if f:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * ln[i] / avg))
        if s > 0:
            sc.append((s, i))
    sc.sort(reverse=True)
    return [cards[i] for _, i in sc[:k]]


def fdate(t):
    return time.strftime("%Y-%m-%d", time.localtime(t)) if t else "?"


def card_line(c):
    tg = LIB["tags"].get(c["path"], {})
    return "- %s | %.2f ГБ | файлов %d | создана %s, изм. %s | типы: %s | программа: %s | теги: %s | заметка: %s | коллекции: %s | внутри: %s" % (
        c["path"], c["size"] / 2**30, c["files"], fdate(c["t"][0]), fdate(c["t"][1]),
        ", ".join(k for k, _ in c["cats"]) or "?", c["prog"] or "нет", ", ".join(tg.get("tags", [])) or "нет",
        tg.get("note", "") or "нет", ", ".join(_PCOLL.get(c["path"], [])) or "нет",
        "; ".join((c["subs"] + c["top"])[:8]) or "?")


STOP = set(toks("дубликаты дубли дубликат повторы повторяющиеся одинаковые файлы найди покажи мои у меня есть где"))


def sample_hash(path, size):
    """Хэш по началу, середине и концу файла: быстро для файлов в гигабайты."""
    h = hashlib.sha1(str(size).encode())
    try:
        with open(path, "rb") as f:
            for off in (0, max(size // 2 - (1 << 19), 0), max(size - (1 << 20), 0)):
                f.seek(off)
                h.update(f.read(1 << 20))
    except OSError:
        return None
    return h.hexdigest()


def dups(min_bytes=10 << 20, words=(), limit=200):
    """Файлы одинакового размера и содержимого (по выборке) среди сохранённых в дереве."""
    by = {}

    def walk(d, path):
        for f in d.fl:
            if f[1] >= min_bytes:
                by.setdefault(f[1], []).append(os.path.join(path, f[0]))
        for n, c in d.dirs.items():
            walk(c, os.path.join(path, n))
    if SC.root:
        walk(SC.root, SC.root_path)
    groups = []
    for size, ps in by.items():
        if len(ps) < 2:
            continue
        hh = {}
        for p in ps:
            h = sample_hash(p, size)
            if h:
                hh.setdefault(h, []).append(p)
        for g in hh.values():
            if len(g) > 1 and (not words or any(w in p.lower() for p in g for w in words)):
                groups.append({"size": size, "paths": sorted(g), "wasted": size * (len(g) - 1)})
    groups.sort(key=lambda g: -g["wasted"])
    return {"count": len(groups), "wasted": sum(g["wasted"] for g in groups), "groups": groups[:limit],
            "note": "сравнивались файлы от %d МБ, которые сохранены в дереве; совпадение по размеру и выборке из начала, середины и конца" % (min_bytes >> 20)}


def ask(q, model):
    index()
    ql = q.lower()
    hits = []
    for col in LIB["collections"]:
        if col["name"].lower() in ql:
            have = {c["path"]: c for c in all_cards()}
            hits += [have[it["path"]] for it in col["items"] if it["path"] in have]
    for c in search(q, 8):
        if c not in hits:
            hits.append(c)
    hits = hits[:14]
    dp = None
    if re.search(r"дубл|повтор|одинаков", ql):
        words = [w for w in re.findall(r"[^\W_]+", ql) if len(w) >= 2 and toks(w)[0] not in STOP and not w.startswith(("дубл", "повтор"))]
        dp = dups(words=words)
    src = [dict(c, tags=LIB["tags"].get(c["path"], {}).get("tags", []), note=LIB["tags"].get(c["path"], {}).get("note", ""),
                colls=_PCOLL.get(c["path"], [])) for c in hits]
    if not hits:
        if dp:
            return {"answer": "Дубликаты: групп %d, лишних %.1f ГБ." % (dp["count"], dp["wasted"] / 2**30), "sources": [], "dups": dp}
        return {"answer": "Ничего не нашёл. Просканируйте диск или добавьте теги и заметки.", "sources": []}
    if not model and not profile().get("model"):
        return {"answer": "Модель не выбрана (⚙ Модель). Вот найденные папки.", "sources": src, "dups": dp}
    prompt = ("Ты помощник по данным на компьютере пользователя. Ниже карточки папок (метаданные: размер, даты, типы, "
              "программа, теги, заметки). Отвечай по-русски, коротко, ТОЛЬКО по этим карточкам, называй пути. "
              "Не выдумывай: если данных не хватает, скажи. Про удаление советуй осторожно: сначала архив или корзина.\n\n"
              "Карточки:\n%s\n%s\nВопрос: %s\nОтвет:") % (
        "\n".join(card_line(c) for c in hits),
        ("Найдено дубликатов: групп %d, лишних %.1f ГБ (список покажет интерфейс).\n" % (dp["count"], dp["wasted"] / 2**30)) if dp else "", q)
    try:
        ans = llm(prompt, model, 700)
    except Exception as e:
        return {"answer": "Модель недоступна (%s). Вот найденные папки." % e, "sources": src, "dups": dp}
    return {"answer": ans, "sources": src, "dups": dp}


def suggest(path, model):
    d = SC.find(path)
    if d is None:
        return {"error": "нет такой папки"}
    c = {"path": path, "name": d.name, "size": d.size, "files": d.files, "t": d.t, "cats": cats_of(d, 4),
         "prog": program_of(path) if os.name == "nt" else "",
         "subs": [n for n, _ in sorted(d.dirs.items(), key=lambda x: -x[1].size)[:8]],
         "top": [f[0] for f in sorted(d.fl, key=lambda x: -x[1])[:8]]}
    prompt = ("По карточке папки предложи 3-5 коротких тегов (одно-два слова, по-русски, строчными: что это и для чего) "
              "и одну фразу назначения. Верни ТОЛЬКО JSON: {\"tags\":[...],\"note\":\"...\"}\n" + card_line(c))
    try:
        m = re.search(r"\{.*\}", llm(prompt, model, 200), re.S)
        j = json.loads(m.group(0))
        return {"tags": [str(t).strip().lower() for t in j.get("tags", [])][:6], "note": str(j.get("note", ""))}
    except Exception as e:
        return {"error": "не вышло: %s" % e}


def launch(path):
    """Открывает только то, что пользователь сам положил в коллекцию или что есть среди установленных программ."""
    ok = any(it["path"] == path for c in LIB["collections"] for it in c["items"]) or any(p["path"] == path for p in program_list())
    if not ok or not os.path.exists(path):
        return {"ok": False, "error": "не в лаунчере или нет на диске"}
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])
    u = LIB.setdefault("usage", {}).setdefault(path, {"n": 0, "last": 0})
    u["n"] += 1
    u["last"] = time.time()
    lib_touch()
    return {"ok": True}


def launcher_items():
    out = {}
    for c in LIB["collections"]:
        for it in c["items"]:
            e = out.setdefault(it["path"], {"path": it["path"], "name": os.path.basename(it["path"].rstrip("\\/")) or it["path"],
                                            "dir": it.get("dir", True), "size": it.get("size", 0), "colls": [], "exists": os.path.exists(it["path"])})
            e["colls"].append(c["name"])
    for p, e in out.items():
        tg = LIB["tags"].get(p, {})
        e["tags"], e["note"] = tg.get("tags", []), tg.get("note", "")
        e.update(LIB.get("usage", {}).get(p, {"n": 0, "last": 0}))
    return sorted(out.values(), key=lambda x: (-x["last"], x["name"].lower()))


def lib_info():
    cnt = {}
    for v in LIB["tags"].values():
        for t in v.get("tags", []):
            cnt[t] = cnt.get(t, 0) + 1
    cols = []
    for c in LIB["collections"]:
        items = [dict(it, exists=os.path.exists(it["path"]), tags=LIB["tags"].get(it["path"], {}).get("tags", []),
                      note=LIB["tags"].get(it["path"], {}).get("note", "")) for it in c["items"]]
        cols.append({"id": c["id"], "name": c["name"], "items": items})
    return {"collections": cols, "tags": sorted(cnt.items(), key=lambda x: -x[1]), "cards": len(CARDS)}


def lib_action(b):
    a = b.get("action")
    cols = LIB["collections"]
    if a == "create":
        name = b.get("name", "").strip()
        if not name or any(c["name"].lower() == name.lower() for c in cols):
            return {"ok": False, "error": "пустое или повторное имя"}
        cols.append({"id": str(int(time.time() * 1000)), "name": name, "items": []})
    elif a == "delete":
        LIB["collections"] = [c for c in cols if c["id"] != b.get("id")]
    elif a in ("add", "remove"):
        col = next((c for c in cols if c["id"] == b.get("id")), None)
        if col is None:
            return {"ok": False, "error": "нет такой коллекции"}
        p = b.get("path", "")
        col["items"] = [it for it in col["items"] if it["path"] != p]
        if a == "add":
            col["items"].append({"path": p, "size": b.get("size", 0), "dir": b.get("dir", True)})
    elif a == "tag":
        p = b.get("path", "")
        tags = [t.strip().lower() for t in b.get("tags", []) if t.strip()]
        if tags or b.get("note", "").strip():
            LIB["tags"][p] = {"tags": tags, "note": b.get("note", "").strip(), "size": b.get("size", 0), "dir": b.get("dir", True)}
        else:
            LIB["tags"].pop(p, None)
    else:
        return {"ok": False, "error": "неизвестное действие"}
    lib_touch()
    return {"ok": True}


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
        if u.path == "/api/lib":
            return self.send(lib_info())
        if u.path == "/api/launcher":
            return self.send({"items": launcher_items()})
        if u.path == "/api/programs":
            return self.send({"programs": program_list()})
        if u.path == "/api/models":
            ms = models()
            return self.send({"models": ms, "model": profile().get("model", ""), "recommended": recommend(ms), "profile": profile()["name"]})
        if u.path == "/api/config":
            return self.send(cfg_public())
        if u.path == "/api/dups":
            return self.send(dups(int(float(q.get("min", 10)) * (1 << 20))))
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
        if u.path == "/api/lib":
            return self.send(lib_action(b))
        if u.path == "/api/config":
            return self.send(cfg_action(b))
        if u.path == "/api/config/test":
            return self.send(cfg_test(b))
        if u.path == "/api/launch":
            return self.send(launch(b.get("path", "")))
        if u.path == "/api/ask":
            return self.send(ask(b.get("q", ""), b.get("model", "")))
        if u.path == "/api/suggest":
            return self.send(suggest(b.get("path", ""), b.get("model", "")))
        if u.path == "/api/trash":
            return self.send(to_trash(b.get("path", "")))
        if u.path == "/api/delete":
            return self.send(hard_delete(b.get("path", ""), b.get("confirm", "")))
        if u.path == "/api/web":
            return self.send(web_info(b.get("path", ""), b.get("model", "")))
        if u.path == "/api/describe":
            return self.send(describe(b.get("path", ""), b.get("model", "")))
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
.old{color:#d33}.new{color:#2a9d4a}.tile{border:1px solid var(--line);border-radius:8px;padding:10px;background:var(--pan);cursor:pointer;min-width:0}.tile:hover{border-color:var(--acc)}.tile b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;padding:10px 12px}.chip{background:var(--sel);border-radius:9px;padding:0 7px;margin-right:3px;font-size:12px;cursor:pointer}.rk{font-weight:600}.rk0{color:#2a9d4a}.rk1{color:#c80}.rk2{color:#d33}td.wr{white-space:normal;max-width:280px;text-align:left}
#tm{display:block;width:100%;height:100%}#crumb{position:absolute;left:8px;top:6px;background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:2px 8px;z-index:2}
#tip{position:fixed;pointer-events:none;background:#000d;color:#fff;padding:5px 8px;border-radius:5px;font-size:12px;display:none;z-index:9;white-space:pre}
footer{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:6px 12px;background:var(--pan);border-top:1px solid var(--line)}
footer span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.legend{display:flex;align-items:center;gap:4px;color:var(--mut)}.legend i{width:90px;height:8px;background:linear-gradient(90deg,hsl(130,55%,45%),hsl(65,55%,45%),hsl(0,55%,45%))}
</style></head><body>
<header>
 <span id="drv"></span>
 <input id="path" placeholder="Что сканировать: C:\ или любая папка">
 <label>файлы от <input id="keep" type="number" value="1" min="0" step="0.5" style="width:60px"> МБ</label>
 <button class="p" id="go">Сканировать</button><button id="stop" disabled>Стоп</button>
 <label>Возраст по <select id="field"><option value="m">изменению</option><option value="a">доступу</option><option value="c">созданию</option></select></label>
 <button id="web" disabled title="Поиск в интернете: наружу уходит только имя файла/папки">🌐 В интернете</button><button id="cfg">⚙ Модель</button><span class="legend">свежее<i></i>старше 3 лет</span>
</header>
<div id="st">Выберите диск или папку и нажмите «Сканировать».</div>
<nav><button data-v="tree" class="on">Папки</button><button data-v="map">Карта</button><button data-v="old">Мёртвые папки</button><button data-v="launch">Лаунчер</button><button data-v="lib">Библиотека</button></nav>
<main id="main"></main>
<dialog id="dlg" style="border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);min-width:460px;max-width:90vw"><form method="dialog" id="cf" style="display:grid;gap:6px">
<b>Модель для помощника</b><div style="color:var(--mut)">Любой сервер: Ollama или OpenAI-совместимый (LM Studio, llama.cpp, vLLM, OpenRouter, OpenAI…). В модель уходят только метаданные папок (названия, размеры, даты, типы, теги), не содержимое файлов.</div>
<label>Профиль <select id="cp"></select> <button type="button" id="cnew">Новый</button></label>
<label>Название <input id="cnm" style="width:100%"></label>
<label>Тип <select id="cty"><option value="ollama">Ollama</option><option value="openai">OpenAI-совместимый</option></select>
 <select id="cpre"><option value="">пресет…</option><option value="ollama|http://127.0.0.1:11434">Ollama локально</option><option value="openai|http://127.0.0.1:1234/v1">LM Studio</option><option value="openai|http://127.0.0.1:8080/v1">llama.cpp server</option><option value="openai|http://127.0.0.1:8000/v1">vLLM</option><option value="openai|https://openrouter.ai/api/v1">OpenRouter</option><option value="openai|https://api.openai.com/v1">OpenAI</option><option value="openai|https://api.anthropic.com/v1">Anthropic (OpenAI-режим)</option></select></label>
<label>Адрес <input id="cur" style="width:100%" placeholder="http://127.0.0.1:11434 или https://…/v1"></label>
<label>Ключ API <input id="cky" type="password" style="width:100%" placeholder="для локальных серверов не нужен"></label>
<label>Модель <input id="cmd" list="cml" style="width:100%" placeholder="имя модели"><datalist id="cml"></datalist></label>
<div style="color:var(--mut)">Рекомендуется для этой задачи: небольшая инструкционная модель с русским — <b>qwen3:8b</b> (или 4b на слабой видеокарте); для будущего семантического поиска — эмбеддинги <b>bge-m3</b>. Coder/vision-модели не нужны.</div><div id="cwarn" style="color:#c80"></div><div id="cres" style="color:var(--mut);white-space:pre-wrap"></div>
<div style="display:flex;gap:6px;flex-wrap:wrap"><button type="button" id="csv2" class="p">Сохранить</button><button type="button" id="cts">Проверить и получить список</button><button type="button" id="cact">Сделать активной</button><button type="button" id="cdel">Удалить</button><button value="x">Закрыть</button></div></form></dialog>
<div id="tip"></div>
<div id="ai" style="display:none;padding:6px 12px;background:var(--pan);border-top:1px solid var(--line)"></div>
<footer><span id="sel" style="min-width:200px">—</span><select id="coll" title="Коллекция"></select><button id="tocoll" disabled>В коллекцию</button><button id="tags" disabled>Теги…</button><button id="sug" disabled>Теги ИИ</button><select id="model" title="Локальная модель Ollama"></select><button id="desc" disabled>Что это? (ИИ)</button><button id="rev" disabled>Показать в Проводнике</button><button id="cp" disabled>Копировать путь</button><button id="tomap" disabled>На карте</button><button id="tr" disabled>В корзину</button><button id="rm" disabled style="color:#d33">Удалить навсегда</button></footer>
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
function render(){if(!rootPath&&view!="lib"&&view!="launch")return;({tree:rTree,map:rMap,old:rOld,lib:rLib,launch:rLaunch})[view]()}
const RK=["можно чистить","осторожно","защищено"];
const tg=n=>(n.tags||[]).map(t=>`<span class="chip">${esc(t)}</span>`).join("")+(n.note?` <span title="${esc(n.note)}">📝</span>`:"")+((n.colls||[]).length?` <span title="${esc(n.colls.join(", "))}">📚</span>`:"");
let LB={collections:[],tags:[]},tagFilter="";
async function libLoad(){LB=await api("/api/lib");$("#coll").innerHTML=LB.collections.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join("")||"<option value=''>нет коллекций</option>"}
libLoad();
function pick(n){sel=n;$("#sel").textContent=n?`${n.path||n.name} — ${fmt(n.size)}`:"—";const ok=n&&n.path;$("#rev").disabled=$("#cp").disabled=!ok;$("#tomap").disabled=!(n&&n.dir);
 $("#desc").disabled=!(n&&n.dir&&n.path);$("#web").disabled=!(n&&n.path);$("#tr").disabled=$("#rm").disabled=!(ok&&n.risk!==2);$("#ai").style.display="none";$("#tocoll").disabled=$("#tags").disabled=!ok;$("#sug").disabled=!(n&&n.dir&&ok)}
async function loadModels(){const r=await api("/api/models");const m=r.models.slice();if(r.model&&!m.includes(r.model))m.unshift(r.model);
 $("#model").innerHTML=m.map(x=>`<option>${esc(x)}</option>`).join("")||"<option value=''>⚙ задайте модель</option>";$("#model").title="Модель ("+r.profile+(r.recommended?"; рекомендуется "+r.recommended:"")+")";const w=r.model||r.recommended;if(w&&m.includes(w))$("#model").value=w;$("#cmd").placeholder=r.recommended?"рекомендуется "+r.recommended:"имя модели"}
loadModels();
let CF={profiles:[],active:""},cur=null;
const cfill=p=>{cur=p;$("#cnm").value=p.name||"";$("#cty").value=p.type||"ollama";$("#cur").value=p.url||"";$("#cky").value=p.key||"";$("#cmd").value=p.model||"";$("#cres").textContent="";cwarn()};
const cwarn=()=>{const u=$("#cur").value;$("#cwarn").textContent=u&&!/^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])/.test(u)?"⚠ Внешний сервис: метаданные папок (названия, размеры, даты, теги) будут отправлены наружу.":""};
const cform=()=>({id:cur&&cur.id||"",name:$("#cnm").value,type:$("#cty").value,url:$("#cur").value,key:$("#cky").value,model:$("#cmd").value});
async function cload(sel){CF=await api("/api/config");$("#cp").innerHTML=CF.profiles.map(p=>`<option value="${p.id}">${esc(p.name)}${p.id==CF.active?" ✓":""}</option>`).join("");
 const p=CF.profiles.find(x=>x.id==(sel||CF.active))||CF.profiles[0];$("#cp").value=p.id;cfill(p)}
$("#cfg").onclick=async()=>{await cload();$("#dlg").showModal()};
$("#cp").onchange=()=>cfill(CF.profiles.find(x=>x.id==$("#cp").value));
$("#cnew").onclick=()=>{cfill({name:"Новый профиль",type:"openai",url:"",key:"",model:""})};
$("#cur").oninput=cwarn;
$("#cpre").onchange=()=>{const v=$("#cpre").value;if(!v)return;const [t,u]=v.split("|");$("#cty").value=t;$("#cur").value=u;cwarn();$("#cpre").value=""};
$("#csv2").onclick=async()=>{const r=await api("/api/config",{action:"save",profile:cform()});if(!r.ok)return $("#cres").textContent=r.error;await cload(r.id);await loadModels();$("#cres").textContent="Сохранено."};
$("#cts").onclick=async()=>{$("#cres").textContent="Проверяю…";const r=await api("/api/config/test",{profile:cform()});$("#cml").innerHTML=r.models.map(m=>`<option value="${esc(m)}">`).join("");
 $("#cres").textContent=(r.ok?"Работает, ответ: "+r.text:"Ошибка: "+r.error)+"\nМоделей на сервере: "+r.models.length+(r.models.length?" (список в поле «Модель»)":"")};
$("#cact").onclick=async()=>{if(!cur||!cur.id)return $("#cres").textContent="Сначала сохраните профиль.";await api("/api/config",{action:"activate",id:cur.id});await cload(cur.id);await loadModels()};
$("#cdel").onclick=async()=>{if(cur&&cur.id&&confirm("Удалить профиль?")){await api("/api/config",{action:"delete",id:cur.id});await cload();await loadModels()}};
$("#web").onclick=async()=>{if(!sel)return;const a=$("#ai");a.style.display="block";a.textContent="Ищу «"+sel.name+"» в интернете…";
 const r=await api("/api/web",{path:sel.path,model:$("#model").value});if(r.error){a.textContent=r.error;return}
 a.innerHTML=(r.image?`<img src="${esc(r.image)}" referrerpolicy="no-referrer" style="float:right;max-height:120px;margin-left:8px;border-radius:4px">`:"")+`<b>${esc(r.title||r.query)}</b><br>${esc(r.text)}`+(r.tips?`<br><br><b>Что делать:</b><br>${esc(r.tips).replace(/\n/g,"<br>")}`:"")+
  (r.results.length?"<br><br>"+r.results.map(x=>`<a href="${esc(x.url)}" target="_blank" rel="noreferrer">${esc(x.title)}</a>`).join("<br>"):"")+`<br><i>Сохранено в заметке папки (библиотека).</i>`};
$("#desc").onclick=async()=>{if(!sel)return;const a=$("#ai");a.style.display="block";a.textContent="Думаю… ("+$("#model").value+")";
 const r=await api("/api/describe",{path:sel.path,model:$("#model").value});a.textContent=r.error||r.text};
async function afterLib(){await libLoad();if(view=="lib")rLib();else if(sel){const p=sel.path;render()}}
$("#tocoll").onclick=async()=>{if(!sel||!$("#coll").value)return alert("Сначала создайте коллекцию на вкладке «Библиотека».");await api("/api/lib",{action:"add",id:$("#coll").value,path:sel.path,size:sel.size,dir:sel.dir});await afterLib();$("#ai").style.display="block";$("#ai").textContent="Добавлено в коллекцию."};
async function editTags(def){if(!sel)return;const cur=def||{tags:sel.tags||[],note:sel.note||""};
 const t=prompt(`Теги через запятую, после | — для чего (заметка):\n${sel.path}`,cur.tags.join(", ")+(cur.note?" | "+cur.note:""));if(t===null)return;
 const [a,...b]=t.split("|");await api("/api/lib",{action:"tag",path:sel.path,tags:a.split(","),note:b.join("|"),size:sel.size,dir:sel.dir});
 const s=sel.path;await afterLib();if(view!="lib")render()}
$("#tags").onclick=()=>editTags();
$("#sug").onclick=async()=>{const a=$("#ai");a.style.display="block";a.textContent="Предлагаю теги…";const r=await api("/api/suggest",{path:sel.path,model:$("#model").value});
 if(r.error){a.textContent=r.error;return}a.textContent="Предложено: "+r.tags.join(", ")+" — "+r.note;editTags({tags:r.tags,note:r.note})};
async function gone(r){if(!r.ok)return alert("Не вышло: "+r.error);sel=null;pick(null);render()}
$("#tr").onclick=async()=>{if(sel&&confirm(`Отправить в корзину?\n${sel.path}\n${fmt(sel.size)}\nМесто на диске освободится после очистки корзины.`))gone(await api("/api/trash",{path:sel.path}))};
$("#rm").onclick=async()=>{if(!sel)return;const nm=sel.path.split(sep).filter(Boolean).pop();
 const t=prompt(`УДАЛИТЬ НАВСЕГДА без корзины:\n${sel.path}\n${fmt(sel.size)}\n\nДля подтверждения введите имя: ${nm}`);if(t===null)return;gone(await api("/api/delete",{path:sel.path,confirm:t}))};
$("#rev").onclick=()=>sel&&api("/api/reveal",{path:sel.path});
$("#cp").onclick=()=>sel&&navigator.clipboard.writeText(sel.path);
$("#tomap").onclick=()=>{if(sel&&sel.dir){mapPath=sel.path;document.querySelector('nav [data-v=map]').click()}};
// ---- дерево
async function rTree(){const m=$("#main");m.innerHTML=`<table><thead><tr><th>Имя<th>Размер<th>% от родителя<th>Файлов<th>Создан<th>Изменён<th>Доступ<th>Теги</thead><tbody id="tb"></tbody></table>`;
 const d=await api("/api/children?path="+encodeURIComponent(rootPath));addRows($("#tb"),d.children,0,d.node.size,null)}
function addRows(tb,items,lvl,psize,after){let prev=after;for(const n of items){const tr=document.createElement("tr");tr.className="r";tr.n=n;tr.lvl=lvl;
 const pct=psize?n.size/psize*100:0,f=fi();
 tr.innerHTML=`<td class="nm" style="padding-left:${8+lvl*16}px" title="${esc(n.path)}"><span class="tg">${n.dir&&n.files?"▸":""}</span>${n.dir?"📁":n.misc?"…":"📄"} ${esc(n.name)}<td>${fmt(n.size)}<td><span class="bar" style="width:${Math.round(pct*0.8)}px"></span> ${pct.toFixed(1)}%<td>${n.misc?"":n.files.toLocaleString()}<td>${dt(n.t[0])}<td style="color:${col(n.t[1])}">${dt(n.t[1])}<td style="color:${col(n.t[2])}">${dt(n.t[2])}<td class="wr">${tg(n)}`;
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
// ---- мёртвые папки
async function rOld(){const m=$("#main");m.innerHTML=`<div style="padding:8px 12px">Не менялись дольше <input id="yrs" type="number" value="2" step="0.5" min="0" style="width:60px"> лет (по полю «Возраст по» сверху), размер от <input id="mn" type="number" value="500" style="width:70px"> МБ <button id="ap" class="p">Показать</button> <button id="csv">Экспорт CSV</button> <b id="sum"></b></div><div id="ot"></div>`;
 let items=[];const run=async()=>{const d=await api(`/api/stale?field=${$("#field").value}&years=${$("#yrs").value}&min=${$("#mn").value}`);items=d.items;
  $("#sum").textContent=`найдено ${d.count}, всего ${fmt(d.total)}`;
  $("#ot").innerHTML=`<table><thead><tr><th>Путь<th>Размер<th>Что внутри<th>Программа<th>Совет<th>Создан<th>Изменён<th>Доступ<th>Теги</thead><tbody>`+items.map((n,i)=>`<tr class="r" data-i="${i}"><td class="nm" title="${esc(n.path)}">${n.dir?"📁":"📄"} ${esc(n.path)}<td>${fmt(n.size)}<td class="wr">${n.cats.map(c=>c[0]+" "+fmt(c[1])).join(", ")}<td class="wr">${esc(n.prog)}<td class="rk rk${n.risk}">${RK[n.risk]}<td>${dt(n.t[0])}<td>${dt(n.t[1])}<td>${dt(n.t[2])}<td class="wr">${tg(n)}`).join("")+`</tbody></table>`;
  $("#ot").onclick=e=>{const tr=e.target.closest("tr.r");if(!tr)return;document.querySelectorAll("tr.sel").forEach(x=>x.classList.remove("sel"));tr.classList.add("sel");pick(items[tr.dataset.i])}};
 $("#csv").onclick=()=>{const q=v=>`"${String(v).replace(/"/g,'""')}"`;const t="путь;размер_байт;что_внутри;программа;совет;создан;изменён;доступ\n"+items.map(n=>[q(n.path),n.size,q(n.cats.map(c=>c[0]).join(", ")),q(n.prog),RK[n.risk],dt(n.t[0]),dt(n.t[1]),dt(n.t[2])].join(";")).join("\n");
  const a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["﻿"+t],{type:"text/csv"}));a.download="dead-folders.csv";a.click()};
 $("#ap").onclick=run;run()}
// ---- библиотека: коллекции, теги, помощник
async function rLib(){await libLoad();const m=$("#main");
 m.innerHTML=`<div style="display:flex;height:100%"><div id="lb" style="width:46%;overflow:auto;padding:8px 12px;border-right:1px solid var(--line)"></div>
 <div style="flex:1;display:flex;flex-direction:column;min-width:0"><div id="msgs" style="flex:1;overflow:auto;padding:8px 12px"></div>
 <div style="padding:8px 12px;display:flex;gap:6px"><input id="q" style="flex:1" placeholder="Спросите о своих данных: что у меня из FL Studio? что можно архивировать?"><button id="askb" class="p">Спросить</button></div></div></div>`;
 const lb=$("#lb");const tags=LB.tags.map(([t,n])=>`<span class="chip" data-t="${esc(t)}" style="${t==tagFilter?"outline:2px solid var(--acc)":""}">${esc(t)} ${n}</span>`).join("")||"<i>тегов пока нет</i>";
 lb.innerHTML=`<div><input id="cn" placeholder="новая коллекция"> <button id="cadd">Создать</button></div><div style="margin:8px 0">Теги (клик — фильтр): ${tags}</div><div style="color:var(--mut);margin-bottom:6px">Карточек для помощника: ${LB.cards}. Выберите папку на других вкладках → «В коллекцию» / «Теги…» / «Теги ИИ».</div>`+
  LB.collections.map(c=>{const its=c.items.filter(i=>!tagFilter||i.tags.includes(tagFilter));const tot=its.reduce((a,i)=>a+i.size,0);
   return `<div style="margin:10px 0"><b>${esc(c.name)}</b> — ${its.length} шт., ${fmt(tot)} <button data-del="${c.id}">удалить коллекцию</button>`+
   its.map(i=>`<div class="r" data-c="${c.id}" data-p="${esc(i.path)}" style="padding:2px 0 2px 8px;cursor:pointer;${i.exists?"":"opacity:.5"}">${i.dir?"📁":"📄"} ${esc(i.path)} · ${fmt(i.size)} ${i.tags.map(t=>`<span class="chip">${esc(t)}</span>`).join("")}${i.note?`<div style="color:var(--mut);margin-left:20px">${esc(i.note)}</div>`:""}${i.exists?"":" (нет на диске)"} <a href="#" data-rm="${c.id}" data-p="${esc(i.path)}">✕</a></div>`).join("")+`</div>`}).join("");
 lb.onclick=async e=>{const t=e.target;
  if(t.id=="cadd"){const r=await api("/api/lib",{action:"create",name:$("#cn").value});if(!r.ok)return alert(r.error);return rLib()}
  if(t.dataset.t!==undefined){tagFilter=tagFilter==t.dataset.t?"":t.dataset.t;return rLib()}
  if(t.dataset.del){if(confirm("Удалить коллекцию (файлы не затрагиваются)?")){await api("/api/lib",{action:"delete",id:t.dataset.del});rLib()}return}
  if(t.dataset.rm){e.preventDefault();await api("/api/lib",{action:"remove",id:t.dataset.rm,path:t.dataset.p});return rLib()}
  const row=t.closest(".r");if(row){const c=LB.collections.find(x=>x.id==row.dataset.c),it=c.items.find(x=>x.path==row.dataset.p);pick({...it,name:it.path})}};
 const msgs=$("#msgs"),say=(who,html)=>{const d=document.createElement("div");d.style.margin="8px 0";d.innerHTML=`<b>${who}</b><div>${html}</div>`;msgs.appendChild(d);msgs.scrollTop=1e9;return d};
 say("Помощник","Я ищу по карточкам папок (названия, типы файлов, даты, программа, ваши теги и заметки) и отвечаю через локальную модель. Содержимое файлов не читается.");
 const go=async()=>{const q=$("#q").value.trim();if(!q)return;$("#q").value="";say("Вы",esc(q));const w=say("Помощник","думаю…");
  const r=await api("/api/ask",{q,model:$("#model").value});
  w.lastChild.innerHTML=esc(r.answer).replace(/\n/g,"<br>")+(r.sources.length?`<div style="margin-top:6px;color:var(--mut)">Источники:</div>`+r.sources.map((c,i)=>`<div class="r" data-i="${i}" style="cursor:pointer;padding-left:8px">📁 ${esc(c.path)} · ${fmt(c.size)} ${(c.tags||[]).map(t=>`<span class="chip">${esc(t)}</span>`).join("")}</div>`).join(""):"");
  if(r.dups){w.lastChild.innerHTML+=`<div style="margin-top:8px"><b>Дубликаты:</b> групп ${r.dups.count}, лишних ${fmt(r.dups.wasted)}<div style="color:var(--mut)">${esc(r.dups.note)}</div>`+r.dups.groups.slice(0,30).map(g=>`<div style="margin:6px 0"><b>${fmt(g.size)} × ${g.paths.length}</b>`+g.paths.map(p=>`<div class="r" data-dp="${esc(p)}" data-sz="${g.size}" style="cursor:pointer;padding-left:8px">📄 ${esc(p)}</div>`).join("")+`</div>`).join("")+`</div>`}
  w.onclick=e=>{const dpe=e.target.closest("[data-dp]");if(dpe){pick({path:dpe.dataset.dp,name:dpe.dataset.dp,size:+dpe.dataset.sz,dir:false,risk:0,tags:[]});return}
   const row=e.target.closest(".r");if(row&&row.dataset.i!==undefined){const c=r.sources[row.dataset.i];pick({path:c.path,name:c.name,size:c.size,dir:true,risk:0,tags:c.tags,note:c.note})}}};
 $("#askb").onclick=go;$("#q").onkeydown=e=>{if(e.key=="Enter")go()}}
// ---- лаунчер: всё нужное из одного места
async function rLaunch(){await libLoad();const m=$("#main");
 m.innerHTML=`<div style="padding:8px 12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center"><input id="lf" placeholder="Поиск по названию, тегу, заметке" style="width:300px"><span id="lt"></span><button id="pr">Установленные программы…</button></div><div id="pp"></div><div id="lg" class="grid"></div>`;
 let items=(await api("/api/launcher")).items,tf="";
 const draw=()=>{const f=$("#lf").value.toLowerCase();const tags=[...new Set(items.flatMap(i=>i.tags))];
  $("#lt").innerHTML=tags.map(t=>`<span class="chip" data-t="${esc(t)}" style="${t==tf?"outline:2px solid var(--acc)":""}">${esc(t)}</span>`).join("");
  const sh=items.filter(i=>(!tf||i.tags.includes(tf))&&(!f||(i.name+" "+i.tags.join(" ")+" "+i.note+" "+i.colls.join(" ")).toLowerCase().includes(f)));
  $("#lg").innerHTML=sh.map((i,k)=>`<div class="tile" data-k="${items.indexOf(i)}" style="${i.exists?"":"opacity:.45"}"><b>${i.dir?"📁":/\.exe$/i.test(i.path)?"⚙️":"📄"} ${esc(i.name)}</b><div style="color:var(--mut)">${esc(i.colls.join(", "))} · ${fmt(i.size)}</div><div>${i.tags.map(t=>`<span class="chip">${esc(t)}</span>`).join("")}</div>${i.note?`<div style="color:var(--mut)">${esc(i.note)}</div>`:""}<div style="color:var(--mut);font-size:12px">${i.n?`запусков ${i.n}, последний ${dt(i.last)}`:"ещё не запускали"}${i.exists?"":" · нет на диске"}</div><button data-rv="${items.indexOf(i)}">📂</button></div>`).join("")||`<div style="padding:12px;color:var(--mut)">Пусто. Добавьте папки и файлы в коллекции («В коллекцию» внизу) или нажмите «Установленные программы…».</div>`};
 draw();$("#lf").oninput=draw;
 $("#lt").onclick=e=>{if(e.target.dataset.t!==undefined){tf=tf==e.target.dataset.t?"":e.target.dataset.t;draw()}};
 $("#lg").onclick=async e=>{const rv=e.target.dataset.rv;if(rv!==undefined){api("/api/reveal",{path:items[rv].path});return}
  const t=e.target.closest(".tile");if(!t)return;const it=items[t.dataset.k];pick({...it,risk:0});const r=await api("/api/launch",{path:it.path});if(!r.ok)alert(r.error);else{it.n++;it.last=Date.now()/1000;draw()}};
 $("#pr").onclick=async()=>{const pp=$("#pp");pp.innerHTML="читаю реестр…";const ps=(await api("/api/programs")).programs;
  pp.innerHTML=`<div style="padding:0 12px 8px">Установленные программы (${ps.length}). Коллекция для добавления выбрана внизу. <input id="pf" placeholder="фильтр"></div><div style="max-height:220px;overflow:auto;padding:0 12px 8px" id="pl"></div>`;
  const dp=()=>{const f=$("#pf").value.toLowerCase();$("#pl").innerHTML=ps.map((p,i)=>[p,i]).filter(([p])=>!f||p.name.toLowerCase().includes(f)).slice(0,300).map(([p,i])=>`<div class="r" style="padding:2px 0">${esc(p.name)} <span style="color:var(--mut)">${esc(p.publisher)} · ${p.size?fmt(p.size):""} · ${esc(p.path)}</span> <button data-a="${i}">+ в коллекцию</button></div>`).join("")};
  dp();$("#pf").oninput=dp;
  $("#pl").onclick=async e=>{const a=e.target.dataset.a;if(a===undefined)return;if(!$("#coll").value)return alert("Сначала создайте коллекцию на вкладке «Библиотека».");
   const p=ps[a];await api("/api/lib",{action:"add",id:$("#coll").value,path:p.path,size:p.size,dir:p.dir});await api("/api/lib",{action:"tag",path:p.path,tags:["программа"],note:p.name,size:p.size,dir:p.dir});rLaunch()}}}
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
