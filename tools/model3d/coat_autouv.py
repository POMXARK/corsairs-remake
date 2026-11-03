"""3DCoat 2026 script: the UV of a head mesh by 3DCoat (seams: its Auto Seams or given ones, then Unwrap), no hands.

Console: "C:\\Program Files\\3DCoat-2026\\3DCoatGL64.exe" -script C:\\path\\coat_autouv.py
(it must run in the user's desktop session: over ssh start it through schtasks /it, see README). The job is read
from _coat_job.txt next to this script: input .obj, output .obj, log file, mode, seams file. Modes:
  auto   - (or empty) 3DCoat's own Auto Seams;
  seams  - the seams of the file (head_seams.py: 'a b' 0-based vertex pairs of the input .obj) instead;
  export - only write the UV room as it is (seams and unwrap made by hand).
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


def main():
    job = [s.strip() for s in open(JOB, encoding='utf-8').read().split('\n')] + ['', '']
    src, dst, logp, mode, seams = job[:5]
    log = open(logp, 'w', encoding='utf-8')

    def say(*a):
        log.write(' '.join(str(x) for x in a) + '\n')
        log.flush()

    def islands():
        return coat.Model.fromUv().islandsCount(0)

    try:
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
            if mode == 'seams':
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
