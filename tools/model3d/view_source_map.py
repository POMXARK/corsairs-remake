#!/usr/bin/env python3
"""Which view paints which texel: view_source_map.py in.glb out.glb front.png left.png back.png right.png

in.glb is the model before pdm_project_views.py (its own texture). The texture of out.glb is half the colour that
pdm_project_views would paint and half the colour of the view that dominates the texel: front green, back blue,
left yellow, right violet; red - no view sees the texel well (pdm_project_views fills it from the nearest painted faces
in space, or it keeps the colour of in.glb). Look at it with render_glb.py or in Blender: hair on the neck that is blue
comes from the back view, red - from the fill.
"""
import io
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import numpy as np
from PIL import Image
import pdm_project_views as pv
src, dst = sys.argv[1:3]
views = {n: pv.load_view(p) for n, p in zip(pv.NAMES, sys.argv[3:7])}
j, b = pv.read_glb(src); prim = j['meshes'][0]['primitives'][0]
P = pv.accessor(j, b, prim['attributes']['POSITION']); UV = pv.accessor(j, b, prim['attributes']['TEXCOORD_0'])
tris = pv.accessor(j, b, prim['indices']).reshape(-1, 3)
bv = j['bufferViews'][j['images'][0]['bufferView']]
atlas = np.asarray(Image.open(io.BytesIO(b[bv.get('byteOffset', 0):bv.get('byteOffset', 0)+bv['byteLength']])).convert('RGB')).astype(np.float32)
best=None
for side in (1., -1.):
    acc, ws, _, _ = pv.paint(P, UV, tris, atlas, views, side, step=12)
    w = sum(ws.values()); a = sum(acc.values()); m = w > 1e-3
    err = np.abs(a[m]/w[m][:, None]-atlas[m]).mean()
    if best is None or err < best[0]: best = (err, side)
acc, ws, cover, used = pv.paint(P, UV, tris, atlas, views, best[1], do_align=True)
painted, w = pv.combine(atlas, acc, ws, P, UV, tris)
good = (cover > 0.05) & (w > pv.SEEN_W)
# which view dominates
names = list(ws); W = np.stack([ws[n] for n in names]); dom = W.argmax(0)
col = {'front': [60, 200, 60], 'back': [60, 120, 255], 'left': [255, 220, 0], 'right': [200, 60, 255]}
pal = np.array([col[n] for n in names], np.float32)
out = np.where(good[..., None], pal[dom]*0.5+painted*0.5, np.array([255,0,0],np.float32)*0.6+atlas*0.4)
print(names, 'good share', good[used].mean())
buf = io.BytesIO(); Image.fromarray(out.clip(0,255).astype(np.uint8)).save(buf, 'PNG'); png = buf.getvalue()
o = bv.get('byteOffset', 0); nb = b[:o] + png + b[o+bv['byteLength']:]
delta = len(png) - bv['byteLength']; bv['byteLength'] = len(png)
for v in j['bufferViews']:
    if v is not bv and v.get('byteOffset', 0) > o: v['byteOffset'] += delta
j['buffers'][0]['byteLength'] = len(nb)
pv.write_glb(dst, j, nb)
