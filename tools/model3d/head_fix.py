#!/usr/bin/env python3
"""Fix a generated head end to end: check it, choose the steps, run them, check again, pick the best variant.

head_fix.py in.glb out.glb --views front.png left.png back.png right.png [options]
  --faces 10000[,20000]  faces of the result (a list = variants; default 20000)
  --seal 3[,2]           SEAL of solidify.py (voxels of the hole sealing; 4 glues the ponytail to the neck; default 3)
  --uv coat|xatlas       UV: 3DCoat Auto Seams over ssh (coat_run.sh, opens 3DCoat on the Windows screen) or the xatlas
                         atlas solidify.py makes (no Windows); default coat
  --skin-guard / --no-skin-guard   the rule 'skin takes no hair' of pdm_project_views.py (default: on if the check finds
                         hair on skin or the model is to be solidified)
  --tex 2048             texture size
  --work dir             intermediate files (default: out.glb without .glb + '_work')
  --plan                 only check in.glb and print the plan with the recommendations, run nothing
Steps: head_check.py in.glb -> plan (solidify when there is a double wall, holes or pieces; UV; paint) -> for every
variant: solidify.py -> obj -> coat_run.sh auto -> uv_from_obj.py -> pdm_project_views.py -> head_check.py; the variant
with the best score is copied to out.glb. The report (before, every variant, after) goes to <work>/report.md and .json.
"""
import itertools
import json
import os
import shutil
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
import head_check as hc  # noqa: E402
import pdm_project_views as pv  # noqa: E402


def run(cmd, env=None, log=None):
    t = time.time()
    print('$', ' '.join(cmd), flush=True)
    p = subprocess.run(cmd, env={**os.environ, **(env or {})}, capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip().splitlines()
    for ln in out[-4:]:
        if 'moved to the mesh' not in ln:
            print('   ', ln)
    if log is not None:
        log.append({'cmd': ' '.join(cmd), 'env': env or {}, 's': round(time.time() - t, 1), 'tail': out[-6:]})
    if p.returncode:
        raise SystemExit(f'failed: {" ".join(cmd)}\n' + '\n'.join(out[-20:]))


def glb_to_obj(glb, obj):
    """Positions welded (the glb is split along UV seams): 3DCoat unwraps one connected surface."""
    P, _, tris, _ = hc.load(glb)
    V, F = hc.weld(P, tris)
    with open(obj, 'w') as f:
        f.write(''.join(f'v {x:.6f} {y:.6f} {z:.6f}\n' for x, y, z in V))
        f.write(''.join(f'f {a + 1} {b + 1} {c + 1}\n' for a, b, c in F))


def plan(before, a):
    """Steps and options from the issues of the check and the given options; every choice with its reason."""
    ids = {i['id'] for i in before['issues']}
    why = []
    solid = bool(ids & {'double_wall', 'holes', 'pieces', 'nonmanifold'}) or before['geometry']['faces'] > 60000
    if a['solidify'] is not None:
        solid = a['solidify']
        why.append(f"solidify: {'да' if solid else 'нет'} (задано)")
    else:
        why.append('solidify: ' + ('да — ' + ', '.join(sorted(ids & {'double_wall', 'holes', 'pieces', 'nonmanifold', 'faces'}))
                                  if solid else 'нет — сетка уже одна стенка без дыр'))
    faces = a['faces'] or [20000 if 'faceted' in ids or before['geometry']['faces'] > 20000 else before['geometry']['faces']]
    why.append(f"граней: {', '.join(map(str, faces))}" + (' (задано)' if a['faces'] else
               ' — 20 тыс.: на 10 тыс. хвост гранёный' if faces == [20000] else ''))
    seal = a['seal'] or [3]
    why.append(f"SEAL: {', '.join(map(str, seal))}" + (' (задано)' if a['seal'] else ' — 4 склеивает хвост с шеей, 3 оставляет щель'))
    uv = a['uv'] or 'coat'
    why.append(f"UV: {uv}" + (' (задано)' if a['uv'] else ' — 3DCoat Auto Seams: score 4–4,6 против 1,1 у xatlas'))
    guard = a['guard'] if a['guard'] is not None else ('hair_on_skin' in ids or solid)
    why.append(f"кожа не берёт волосы: {'да' if guard else 'нет'}" +
               (' (задано)' if a['guard'] is not None else ' — найдены волосы на коже' if 'hair_on_skin' in ids else
                ' — новая шея и крышка снизу без защиты берут цвет хвоста' if guard else ''))
    for i in before['issues']:
        if i['id'] in ('silhouette', 'face_shape', 'face_missing', 'lost', 'skin_as_hair_view'):
            why.append(f"конвейер не правит «{i['id']}»: {i['fix']}")
    return dict(solid=solid, faces=faces, seal=seal, uv=uv, guard=guard, tex=a['tex']), why


def variant(src, views_p, work, solid, faces, seal, uv, guard, tex, steps):
    tag = f"f{faces // 1000}k_s{seal}_{uv}{'_sg' if guard else ''}" if solid else f"keep_{uv}{'_sg' if guard else ''}"
    d = os.path.join(work, tag)
    os.makedirs(d, exist_ok=True)
    py = sys.executable
    mesh = src
    if solid:
        mesh = os.path.join(d, 'solid.glb')
        run([py, os.path.join(HERE, 'solidify.py'), src, mesh, '0.002', str(faces), str(tex)], {'SEAL': str(seal)}, steps)
    mid = mesh
    if uv == 'coat':
        obj, uvobj, mid = os.path.join(d, 'mesh.obj'), os.path.join(d, 'mesh_uv.obj'), os.path.join(d, 'mid.glb')
        glb_to_obj(mesh, obj)
        run(['bash', os.path.join(HERE, 'coat_run.sh'), obj, uvobj, 'auto'], None, steps)
        run([py, os.path.join(HERE, 'uv_from_obj.py'), src, uvobj, mid, str(tex)], None, steps)
    final = os.path.join(d, 'final.glb')
    run([py, os.path.join(TOOLS, 'pdm_project_views.py'), mid, final, *views_p, '--no-smooth'] +
        (['--skin-guard'] if guard else []), None, steps)
    return tag, final


def parse(argv):
    a = dict(faces=None, seal=None, uv=None, guard=None, solidify=None, tex=2048, work=None, plan=False, views=None)
    rest = []
    i = 0
    while i < len(argv):
        x = argv[i]
        if x == '--views':
            a['views'] = argv[i + 1:i + 5]
            i += 5
            continue
        if x in ('--faces', '--seal'):
            a[x[2:]] = [int(v) for v in argv[i + 1].split(',')]
        elif x == '--uv':
            a['uv'] = argv[i + 1]
        elif x == '--tex':
            a['tex'] = int(argv[i + 1])
        elif x == '--work':
            a['work'] = argv[i + 1]
        else:
            flag = {'--skin-guard': ('guard', True), '--no-skin-guard': ('guard', False), '--plan': ('plan', True),
                    '--solidify': ('solidify', True), '--no-solidify': ('solidify', False)}.get(x)
            if flag:
                a[flag[0]] = flag[1]
            else:
                rest.append(x)
            i += 1
            continue
        i += 2
    return rest, a


def md(before, why, rows, best):
    L = ['# head_fix', '', f"Вход: `{before['model']}`", '', '## До', '', '```', hc.report_text(before), '```', '',
         '## План', ''] + [f'- {w}' for w in why]
    if rows:
        L += ['', '## Варианты', '', '| вариант | оценка | граней | двойная стенка | острые рёбра (худшая зона) | IoU мин | лицо | '
              'волосы на коже | чёрных | UV score |', '|---|---|---|---|---|---|---|---|---|---|']
        for tag, r in rows:
            g, t = r['geometry'], r['texture']
            iou = min(v['iou'] for v in r['views'].values()) if r.get('views') else '-'
            L.append(f"| {tag}{' ✓' if tag == best else ''} | {r['score']} | {g['faces']} | {g['double_wall'] * 100:.1f} % | "
                     f"{g['sharp_worst'] * 100:.0f} % ({g['sharp_zone']}) | {iou} | {r.get('face', {}).get('mean', '-')} | "
                     f"{t.get('hair_on_skin', 0) * 100:.1f} % | {t['black'] * 100:.2f} % | {r['uv'].get('score')} |")
        after = dict(rows)[best]
        L += ['', '## После (лучший вариант)', '', '```', hc.report_text(after), '```']
    return '\n'.join(L) + '\n'


def main():
    rest, a = parse(sys.argv[1:])
    src, dst = rest[:2]
    if not a['views']:
        raise SystemExit('--views front left back right are needed')
    work = a['work'] or os.path.splitext(dst)[0] + '_work'
    os.makedirs(work, exist_ok=True)
    views = {n: pv.load_view(p) for n, p in zip(pv.NAMES, a['views'])}
    print('== check before', flush=True)
    before = hc.check(src, views, None, os.path.join(work, 'before'))
    print(hc.report_text(before))
    p, why = plan(before, a)
    print('== plan\n' + '\n'.join('  - ' + w for w in why), flush=True)
    rows, steps = [], []
    if not a['plan']:
        combos = list(itertools.product(p['faces'], p['seal'])) if p['solid'] else [(None, None)]
        for faces, seal in combos:
            tag, final = variant(src, a['views'], work, p['solid'], faces, seal, p['uv'], p['guard'], p['tex'], steps)
            r = hc.check(final, views, src, os.path.join(work, tag))
            print(hc.report_text(r), flush=True)
            rows.append((tag, r))
        best = max(rows, key=lambda t: t[1]['score'])[0]
        shutil.copy(os.path.join(work, best, 'final.glb'), dst)
        print(f'== best {best}: {dict(rows)[best]["score"]} (before {before["score"]}) -> {dst}')
    else:
        best = None
    open(os.path.join(work, 'report.md'), 'w').write(md(before, why, rows, best))
    json.dump({'before': before, 'plan': p, 'why': why, 'variants': dict(rows), 'best': best, 'steps': steps},
              open(os.path.join(work, 'report.json'), 'w'), indent=1, ensure_ascii=False, default=lambda o: o.tolist()
              if isinstance(o, np.ndarray) else str(o))
    print('report:', os.path.join(work, 'report.md'))


if __name__ == '__main__':
    main()
