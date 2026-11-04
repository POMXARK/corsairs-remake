#!/usr/bin/env python3
"""The head improves itself: twelve views of the original find the defects, the tools fix them one by one (ours).

head_auto.py in.glb out.glb --views f.png l.png b.png r.png --parts parts.npy --ref ref12/ [--game pdm-game]
             [--model hero1] [--rounds 3] [--tries 3] [--jobs N] [--work dir] [--policy head_policy.json]

A round: head_views.evaluate scores the whole head against the twelve reference views of the original (silhouettes,
the visual hull, the reference surface, symmetry, skin/hair classes, the mesh) and head_views.defects joins the bad
faces of every kind into regions (a bulge of the hair, an asymmetric ear, a fold of the ponytail, faces turned inside
out ...). For every region the tools of its kind (head_agent.INTENT_TOOLS: outside -> hull, snap; asym -> mirror;
spike -> despike; fold -> relax, membrane; flip -> orient; wrong class -> skin_to_hair, hair_to_skin) are tried, at most
--tries of them, in the order of the learned policy (head_agent.estimates: what helped the same kind and part before),
each on a copy of the head. A try is kept when
  - the twelve-view score of the whole head grows by more than ACCEPT, and
  - the region does not look worse against the four Qwen views (guard_score: head_tools.region_score without its
    drift term, which forbids any move; the colour, skin painted as hair, the detail and the folds of the head the
    model was made of) by more than GUARD;
  or the score grows by more than SMALL and the region looks better against Qwen by QWEN_GAIN (a small region);
the best kept try of a region is taken, the others are rolled back. An arm rolled back on a region is not tried on
the same region (kind, parts, size) in the next rounds. The gain is the reward of the arm in the policy file
(the same one head_agent.py and head_gui.py learn in). After a geometry tool the region is repainted from the four views.
The tries of a region run at once in forked processes (--jobs, default --tries up to 4).
The rounds stop when no region was fixed. work/: before.png and after.png (the twelve views sheets), passes/NNN.png
(every try: the region before | after | the view), report.json (every try with its scores).
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import head_agent as ha  # noqa: E402
import head_tools as ht  # noqa: E402
import head_views as hv  # noqa: E402

ACCEPT = 0.05  # twelve-view score points: a smaller gain of the whole head is noise
GUARD = 1.0  # region score points (the four Qwen views) a kept try may lose
SMALL = 0.01  # a smaller gain of the whole head is kept too when the region looks better against Qwen by QWEN_GAIN
EARLY_MARGIN = 0.02  # the repaint changed the twelve-view score by 0.01 at most (18 tries on hero1)
ALIGN_ONCE = True  # --no-align-once: align the views in every try (the old behaviour)
EARLY = True  # --no-early: repaint every geometry try (slower, the old behaviour)
QWEN_GAIN = 2.0  # (a small region cannot move the twelve-view score of the whole head by ACCEPT)


def accepted(gain, q, q2):
    return (gain > ACCEPT and q2 >= q - GUARD) or (gain > SMALL and q2 >= q + QWEN_GAIN)


def guard_score(r):
    """region_score without its drift term: the tools of the reference shape move the region on purpose, the guard
    only keeps the colour, the hair on the skin, the detail and the folds against the four Qwen views."""
    return round(float(np.clip(100 - 1.2 * r['colour'] - 80 * r['skin_as_hair'] - 40 * r['hair_light']
                               - 30 * r['detail_loss'] - 0.3 * r['angle'] - 60 * r['folds'], 0, 100)), 2)


def arms_for(kind):
    tools = ha.INTENT_TOOLS.get(hv.INTENT[kind], {})
    return [a for a in ha.ARMS if a[0] in tools]


def try_arm(h, arm, mask, base=None):
    """A copy of h with the arm applied. A geometry arm is scored on the shape first (1 s); when the shape alone is
    not better than SMALL (the repaint moves the score by 0.01 at most) the repaint (13 s of the 15 s of a try) is skipped: such a try cannot be kept
    (accepted() needs a gain above SMALL). Returns (trial, note, early report or None)."""
    trial = h.copy()
    note = ht.apply(trial, arm[0], mask, **arm[1])
    pre = None
    if ht.TOOLS[arm[0]][3] == 'geometry':  # the texture follows the new shape
        if base is not None and EARLY:
            pre = hv.evaluate(trial, h.ref)
            if pre[0]['score'] - base + EARLY_MARGIN <= SMALL:
                return trial, note + '; shape gain too small, no repaint', pre
        note += '; ' + ht.apply(trial, 'repaint', ht.grow(trial, mask, 1), views='all')
    return trial, note, None


_JOB = {}  # the head, the region and the arms of the tries run in parallel (inherited by the forked workers)


def _score_try(i):
    """One try in a worker: only what changed goes back (the views of the head are hundreds of MB)."""
    h, mask, arm = _JOB['h'], _JOB['mask'], _JOB['arms'][i]
    t0 = time.time()
    trial, note, pre = try_arm(h, arm, mask, _JOB.get('base'))
    r2, f2 = pre if pre is not None else hv.evaluate(trial, h.ref)
    q2 = guard_score(ht.region_score(trial, mask))
    return trial.P, trial.img, trial.tris, note, r2, f2, q2, time.time() - t0


def run_tries(h, mask, arms, jobs, base=None):
    """[(trial, note, report, faces, guard score, seconds)] of every arm on a copy of h; the tries of a region are
    independent, so up to `jobs` run at once in forked processes (a try is ~13 s, mostly the repaint)."""
    import multiprocessing as mp
    _JOB.update(h=h, mask=mask, arms=arms, base=base)
    if jobs > 1 and len(arms) > 1:
        with mp.get_context('fork').Pool(min(jobs, len(arms))) as pool:
            res = pool.map(_score_try, range(len(arms)))
    else:
        res = [_score_try(i) for i in range(len(arms))]
    out = []
    for P, img, tris, note, r2, f2, q2, sec in res:
        trial = h.copy()
        trial.P, trial.img = P, img
        if tris is not h.tris and not np.array_equal(tris, h.tris):  # orient turned faces
            trial.tris, trial._weld = tris, None
        out.append((trial, note, r2, f2, q2, sec))
    return out


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--views', nargs=4, required=True)
    ap.add_argument('--parts')
    ap.add_argument('--ref', required=True)
    ap.add_argument('--game', default='pdm-game')
    ap.add_argument('--model', default='hero1')
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--tries', type=int, default=3)
    ap.add_argument('--work')
    ap.add_argument('--policy', default=ha.POLICY)
    ap.add_argument('--jobs', type=int, default=0, help='tries run at once (default: --tries, at most 6 and half of the cores)')
    ap.add_argument('--no-early', action='store_true', help='repaint every geometry try, even when the shape got worse')
    ap.add_argument('--no-align-once', action='store_true', help='align the views in every try')
    a = ap.parse_args()
    global EARLY, ALIGN_ONCE
    EARLY = not a.no_early
    ALIGN_ONCE = not a.no_align_once
    jobs = a.jobs or min(a.tries, 6, max(1, (os.cpu_count() or 4) // 2))
    work = a.work or os.path.splitext(a.dst)[0] + '_auto'
    os.makedirs(os.path.join(work, 'passes'), exist_ok=True)
    log = lambda s: print(s, flush=True)
    views = {n: ht.pv.load_view(p) for n, p in zip(ht.pv.NAMES, a.views)}
    h = ht.Head(a.src, views, a.parts)
    h.ref = hv.Reference(a.game, a.model, a.ref)
    h.fit = hv.fit_frame(h.P, h.tris, h.ref)
    log(f"fit: scale {h.fit[1]:.4f}, Qwen fullness px {h.ref.adopt(h)}")
    pol = ha.load_policy(a.policy)
    pol['runs'] = pol.get('runs', 0) + 1
    rep, faces = hv.evaluate(h, h.ref, out=work)
    os.replace(os.path.join(work, 'views12.png'), os.path.join(work, 'before.png'))
    start = rep
    log(f"start: score {rep['score']} {rep['parts']}")
    report = {'model': a.src, 'start': start, 'tries': []}
    n = 0
    failed = set()  # (kind, parts, faces, arm) rolled back
    for rnd in range(a.rounds):
        fixed = 0
        dl = hv.defects(h, faces)
        log(f"round {rnd + 1}: {len(dl)} defects: " + ', '.join(f"{k} {s} {'+'.join(p)}" for k, _, s, p in dl))
        for kind, mask, size, names in dl:
            intent = hv.INTENT[kind]
            est = ha.estimates(pol, names, [intent], arms_for(kind))
            key = (kind, tuple(names), int(size))
            order = sorted((x for x in arms_for(kind) if key + (ha.arm_id(x),) not in failed),
                           key=lambda x: -est[ha.arm_id(x)][0])[:a.tries]
            if not order:
                continue
            if ALIGN_ONCE:
                ht.ensure_aligned(h)
            base_r = guard_score(ht.region_score(h, mask))
            best = None
            for arm, (trial, note, r2, f2, q2, sec) in zip(order, run_tries(h, mask, order, jobs, rep['score'])):
                aid = ha.arm_id(arm)
                gain = r2['score'] - rep['score']
                ok = accepted(gain, base_r, q2)
                if not ok:
                    failed.add(key + (aid,))
                n += 1
                ck = '|'.join(ha.context(names, [intent]))
                reward = float(np.clip(gain + 0.02 * (q2 - base_r) if q2 >= base_r - GUARD else min(gain, 0) - 1,
                                       -20, 20))
                pol['ctx'].setdefault(ck, {})[aid] = ha.update(pol['ctx'].get(ck, {}).get(aid, [0, 0.]), reward)
                for p in names:
                    pol['part'].setdefault(p, {})[aid] = ha.update(pol['part'].get(p, {}).get(aid, [0, 0.]), reward)
                pol['arm'][aid] = ha.update(pol['arm'].get(aid, [0, 0.]), reward)
                ha.save_policy(pol, a.policy)
                label = f"{n}: {kind} {'+'.join(names)}: {aid}  {rep['score']} -> {r2['score']}  " \
                        f"qwen {base_r} -> {q2}  {'годен' if ok else 'откат'}"
                ht.pass_picture(ht.render(h), ht.render(trial), mask, trial,
                                os.path.join(work, 'passes', f'{n:03d}.png'), label)
                rec = {'n': n, 'round': rnd + 1, 'kind': kind, 'parts': names, 'faces': size, 'arm': aid, 'note': note,
                       'score': [rep['score'], r2['score']], 'qwen_region': [base_r, q2],
                       'ok': bool(ok), 'seconds': round(sec, 1)}
                report['tries'].append(rec)
                log(f"  {label}; {note} ({rec['seconds']} s)")
                if ok and (best is None or gain > best[0]):
                    best = (gain, trial, r2, f2, rec)
            if best:
                _, h, rep, faces, rec = best
                h.aligned = None  # the shape changed: align the views again for the next region
                rec['kept'] = True
                fixed += 1
                h.save(os.path.join(work, 'current.glb'))
                log(f"  kept {rec['arm']}: score {rep['score']}")
        if not fixed:
            log(f'round {rnd + 1}: nothing fixed, stop')
            break
    h.save(a.dst)
    final, _ = hv.evaluate(h, h.ref, out=work)
    os.replace(os.path.join(work, 'views12.png'), os.path.join(work, 'after.png'))
    report['final'] = final
    json.dump(report, open(os.path.join(work, 'report.json'), 'w'), ensure_ascii=False, indent=1)
    log(f"score {start['score']} -> {final['score']}; iou {start['parts']['iou']} -> {final['parts']['iou']}, "
        f"bulge {start['parts']['bulge']} -> {final['parts']['bulge']}, asym {start['parts']['asym']} -> "
        f"{final['parts']['asym']}; {sum(1 for t in report['tries'] if t.get('kept'))} of {n} tries kept -> {a.dst} {work}")


if __name__ == '__main__':
    main()
