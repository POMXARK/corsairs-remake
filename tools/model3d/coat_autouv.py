"""3DCoat 2026 script: the UV of a head mesh by 3DCoat (seams: its Auto Seams or given ones, then Unwrap), no hands.

Console: "C:\\Program Files\\3DCoat-2026\\3DCoatGL64.exe" -script C:\\path\\coat_autouv.py
(it must run in the user's desktop session: over ssh start it through schtasks /it, see README). The job is read
from _coat_job.txt next to this script: input .obj, output .obj, log file, mode, seams file. Modes:
  auto   - (or empty) 3DCoat's own Auto Seams;
  seams  - the seams of the file (head_seams.py: 'a b' 0-based vertex pairs of the input .obj) instead;
  auto+seams - Auto Seams, then the seams of the file added on top (head_seams.py split: cuts of the islands that
           lie over themselves);
  export - only write the UV room as it is (seams and unwrap made by hand);
  remesh - no UV: the mesh goes into a voxel volume of the Sculpt room (density from job line 6, voxels per
           scene unit, 0 = 3DCoat's own) and comes back as an even surface of at most N faces (job line 7);
  ops    - no UI: separate 3DCoat tools applied in turn to the mesh, job line 8, ';' between them, ':' before the
           arguments (OPS of coat_run.sh). Mesh tools keep the vertices and their order (head_tools.coat_relax takes
           the moved positions back): relax:degree[:tangent 0/1[:crease angle]] (Mesh.relax), weld[:rel distance]
           (Mesh.weld), triangulate, reduce:faces (reduceToPolycount). Volume tools give a new surface: vrelax:degree
           (surface volume, Volume.relaxSurface), voxrelax:steps (voxels, relaxVoxels), closeholes:size (voxels,
           Volume.closeHoles), vfaces:N (back from the volume with at most N faces, else fromVolume);
  probe  - the input is a list made by coat_probe.py: single tools on small test meshes (flattenSingleIsland with
           each of its methods, Mesh.relax), each result written next to the list (black-box study of the tools).
The mesh is imported for per pixel painting (the import dialog is confirmed by $DialogButton#1), the old seams are
cleared in the UV room, then the seams, Unwrap (it packs too: Pack UV after it packed worse, fill 0.574 vs 0.611),
Apply UV; the result is written as .obj with UV and 'done' goes to the log (the runner closes 3DCoat then).
Command IDs are the ones of the UI buttons (data/Languages/English.xml: ClearEdges, AutoEdges, Unwrap, ApplyUV).
"""
import os
import traceback

import coat

JOB = os.path.join(os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else
                   'C:/Users/User/cof/coat', '_coat_job.txt')


def press_ok():
    coat.ui.cmd('$DialogButton#1')


def remesh(src, dst, dens, faces, say):
    m = coat.Mesh()
    say('read', m.Read(src), 'faces', m.facesCount(), 'bounds diagonal', m.getBounds().GetDiagonal())
    # no toRoom('Sculpt'): it opens a modal 'Getting to Sculpt' message; the volume works from any room
    el = coat.Scene.sculptRoot().addChild('remesh')
    if dens > 0:  # before the voxels: the default (about one voxel per unit) gave a 8 face box for a 1 unit head
        el.density(dens)
    v = el.Volume()
    v.toVoxels()
    m.toVolume(v)
    coat.io.step(20)
    say('voxelized', v.isVoxelized())
    full = coat.Mesh()
    full.fromVolume(v)
    say('volume surface faces', full.facesCount())
    out = coat.Mesh()
    out.fromVolumeWithMaxPolycount(v, faces)
    say('reduced faces', out.facesCount())
    if out.facesCount() > faces * 1.05:  # fromVolumeWithMaxPolycount stops early on detailed heads (79 k for 10 k)
        out.reduceToPolycount(faces)
        say('reduceToPolycount', out.facesCount())
    say('write', dst, out.Write(dst))


def ops(src, dst, spec, dens, say):
    m = coat.Mesh()
    say('read', m.Read(src), 'faces', m.facesCount())
    vol = None
    for op in [o for o in spec.split(';') if o.strip()]:
        name, *a = op.strip().split(':')
        if name == 'relax':
            m.relax(float(a[0]) if a else 0.5, bool(int(a[1])) if len(a) > 1 else False, float(a[2]) if len(a) > 2 else 180.)
        elif name == 'weld':
            m.weld(float(a[0]) if a else 0.0001)
        elif name == 'triangulate':
            m.triangulate()
        elif name == 'reduce':
            m.reduceToPolycount(int(a[0]))
        elif name in ('vrelax', 'voxrelax', 'closeholes'):
            el = coat.Scene.sculptRoot().addChild('op_' + name)
            if dens > 0:
                el.density(dens)
            vol = el.Volume()
            if name == 'vrelax':
                vol.toSurface()
            else:
                vol.toVoxels()
            m.toVolume(vol)
            coat.io.step(10)
            if name == 'vrelax':
                vol.relaxSurface(float(a[0]) if a else 0.5)
            elif name == 'voxrelax':
                vol.relaxVoxels(int(a[0]) if a else 3)
            else:
                vol.closeHoles(int(a[0]) if a else 20)
            coat.io.step(10)
            m = coat.Mesh()
            m.fromVolume(vol)
        elif name == 'vfaces' and vol is not None:
            m = coat.Mesh()
            m.fromVolumeWithMaxPolycount(vol, int(a[0]))
        else:
            say('unknown op', op)
            continue
        say('op', op, 'faces', m.facesCount())
    say('write', dst, m.Write(dst))


def uv_room(src, dst, op, args, say):
    """A probe in the UV room: the scene is cleared, the mesh imported for per pixel painting, then autoseams (Clear,
    Auto Seams; the seams as vertex pairs to dst + '.seams.txt', Unwrap, Apply) or pack R (the UV of the file packed by
    uv.pack(0, rotate R, no shuffle), Apply)."""
    coat.Scene.clearScene(False)
    coat.io.step(10)
    coat.ui.toRoom('Paint', True)
    coat.io.step(10)
    coat.ui.setFileForFileDialog(src)
    coat.ui.cmd('$ImportDPMesh', press_ok)
    coat.io.step(30)
    coat.ui.toRoom('UV', True)
    coat.io.step(30)
    n0 = coat.Model.fromUv().islandsCount(0)
    if op == 'autoseams':
        coat.ui.cmd('$ClearEdges', press_ok)
        coat.io.step(10)
        coat.ui.cmd('$AutoEdges', press_ok)
        coat.io.step(10)
        sm = coat.uv.getSeams()
        with open(dst + '.seams.txt', 'w') as f:
            f.write(''.join(f'{sm[i]} {sm[i + 1]}\n' for i in range(0, len(sm) - 1, 2)))
        coat.ui.cmd('$Unwrap', press_ok)
        coat.io.step(20)
    else:
        coat.uv.pack(0, bool(int(args[0])) if args else True, False)
        coat.io.step(20)
    coat.ui.cmd('$ApplyUV', press_ok)
    coat.io.step(20)
    u = coat.Model.fromUv()
    say('probe uv', os.path.basename(src), op, *args, 'islands', n0, '->', u.islandsCount(0),
        'write', u.getWholeMesh().Write(dst))


def probe(listfile, say):
    """Black-box probe of single 3DCoat tools (coat_probe.py makes the list): each line 'in.obj op arg... out.obj'.
    flatten M: uv.flattenSingleIsland(mesh, M, no rotation, scaled to the geometry) - M 0 plane, 1 LSCM, 2 ABF, 3 GU,
    4 stripe; relax D T C: Mesh.relax(D, tangent T, crease C); ops SPEC [DENS]: the ops mode on the file;
    autoseams, pack R: uv_room (the UV room jobs go last in the list: they clear the scene)."""
    here = os.path.dirname(listfile)
    for ln in open(listfile, encoding='utf-8'):
        w = ln.split()
        if len(w) < 3:
            continue
        src, op, args, dst = os.path.join(here, w[0]), w[1], w[2:-1], os.path.join(here, w[-1])
        try:
            m = coat.Mesh()
            m.Read(src)
            if op in ('autoseams', 'pack'):
                uv_room(src, dst, op, args, say)
                continue
            if op == 'ops':  # the ops of the ops mode: volume tools, reduce, weld
                ops(src, dst, args[0], float(args[1]) if len(args) > 1 else 0., say)
                continue
            if op == 'flatten':
                out = coat.uv.flattenSingleIsland(m, int(args[0]), False, True)
            elif op == 'relax':
                m.relax(float(args[0]), bool(int(args[1])), float(args[2]))
                out = m
            else:
                say('unknown op', ln.strip())
                continue
            say('probe', w[0], op, *args, 'faces', out.facesCount(), 'write', out.Write(dst))
        except Exception:
            say('probe failed', ln.strip(), traceback.format_exc().replace('\n', ' | '))


def main():
    job =[s.strip() for s in open(JOB, encoding='utf-8').read().split('\n')] + [''] * 5
    src, dst, logp, mode, seams, dens, faces, opspec = job[:8]
    log = open(logp, 'w', encoding='utf-8')

    def say(*a):
        log.write(' '.join(str(x) for x in a) + '\n')
        log.flush()

    def islands():
        return coat.Model.fromUv().islandsCount(0)

    try:
        if mode == 'probe':
            probe(src, say)
            open(dst, 'w').write('# probe: the results lie next to the list\n')  # coat_run.sh fetches dst
            say('done')
            log.close()
            return
        if mode == 'ops':
            ops(src, dst, opspec, float(dens or 0), say)
            say('done')
            log.close()
            return
        if mode == 'remesh':
            remesh(src, dst, float(dens or 0), int(faces or 20000), say)
            say('done')
            log.close()
            return
        if mode != 'export':
            coat.ui.toRoom('Paint', True)
            coat.io.step(10)
            coat.ui.setFileForFileDialog(src)
            say('import for per pixel painting', coat.ui.cmd('$ImportDPMesh', press_ok))
            coat.io.step(30)
            say('paint objects', coat.Scene.PaintObjectsCount())
            coat.ui.toRoom('UV', True)
            coat.io.step(30)
            say('room', coat.ui.currentRoom(), 'uv faces', coat.Model.fromUv().facesCount(), 'islands', islands())
            say('cmd $ClearEdges', coat.ui.cmd('$ClearEdges', press_ok))
            coat.io.step(10)
            if mode == 'auto+seams':
                say('cmd $AutoEdges', coat.ui.cmd('$AutoEdges', press_ok))
                coat.io.step(10)
            if mode in ('seams', 'auto+seams'):
                pairs = [tuple(int(x) for x in ln.split()) for ln in open(seams) if ln.strip()]
                m = coat.Model.fromUv()  # a reference to the UV room mesh
                for a, b in pairs:  # coat.uv.addSeam(a, b) is bound with a DWORDS2 first argument: TypeError on ints
                    m.setEdgeSeam(a, b, True)
                m.UpdateMesh()
                say('seams set', len(pairs), 'seams in the mesh', len(coat.uv.getSeams()) // 2,
                    'first is seam', m.isSeam(*pairs[0]))
            else:
                say('cmd $AutoEdges', coat.ui.cmd('$AutoEdges', press_ok))
            coat.io.step(10)
            for cid in ('$Unwrap', '$ApplyUV'):
                say('cmd', cid, coat.ui.cmd(cid, press_ok))
                coat.io.step(20)
                say('  islands', islands())
        u = coat.Model.fromUv()
        say('uv faces', u.facesCount(), 'islands', u.islandsCount(0))
        say('write', dst, u.getWholeMesh().Write(dst))
    except Exception:
        say(traceback.format_exc())
    say('done')
    log.close()


main()
