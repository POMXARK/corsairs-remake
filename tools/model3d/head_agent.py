#!/usr/bin/env python3
"""The agent that fixes a region of a head by itself and learns which tools help (a contextual bandit, UCB).

head_agent.py in.glb out.glb --views f l b r --parts parts.npy [--region eyes,neck] [--prompt "сгладить глаза"]
              [--passes 8] [--work dir] [--policy head_policy.json] [--check]
              [--ref ref12/ --game pdm-game --model hero1]   (the reference shape of head_views.py: hull, snap, mirror)

Every pass: the agent picks a tool with its parameters (an arm) for the context (the parts of the region and the
intents of the prompt), applies it to a copy of the head, scores the region (head_tools.region_score: colour against
the views, skin painted as hair, folds, drift), and keeps the change when the score grew by more than ACCEPT, else rolls
back. The gain is the reward: the mean reward of the arm in this context, in every part of the region and overall is
stored in the policy file, so the next head (and the next run) starts with the tools that helped before. The choice is
the estimate plus an exploration bonus (UCB); arms of the prompt intents and of the parts get a prior.
Every pass goes to work/passes/NNN/ (pass.png: the region before | after | view, pass.json) and work/state.json (the GUI
head_gui.py shows it). --check: the full head_check score before and after.
"""
import json
import math
import os
import re
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import head_tools as ht  # noqa: E402

POLICY = os.path.join(HERE, 'head_policy.json')
ACCEPT = 0.3  # region score points: a smaller gain is noise, the pass is rolled back
UCB_C = 3.0  # exploration: score points of bonus for an arm never tried in the context

ARMS = [
    ('relax', {'steps': 5}), ('relax', {'steps': 15}), ('relax', {'steps': 40}),
    ('membrane', {'blend': 0.3}), ('membrane', {'blend': 0.6}), ('membrane', {'blend': 1.0}),
    ('push', {'amount': 0.002}), ('push', {'amount': -0.002}),
    ('repaint', {'views': 'all'}), ('repaint', {'views': 'front'}), ('repaint', {'views': 'sides'}),
    ('repaint', {'views': 'back'}),
    ('hair_to_skin', {}), ('skin_to_hair', {}), ('blur', {'sigma': 1.0}), ('blur', {'sigma': 3.0}), ('lama', {'grow': 1}), ('lama', {'grow': 3}),
    # against the reference shape (head_views.py, --ref): the twelve silhouettes and the surface of the original
    ('hull', {'blend': 0.5}), ('hull', {'blend': 1.0}), ('snap', {'blend': 0.3}), ('snap', {'blend': 0.6}),
    ('mirror', {'blend': 0.5}), ('mirror', {'blend': 1.0}), ('despike', {}), ('orient', {}),
]


def arm_id(a):
    return a[0] + ''.join(f' {k}={v}' for k, v in a[1].items())


# ---------- the prompt ----------

PART_WORDS = [  # word starts of the prompt (lower case) -> parts of head_parts.EN
    (r'глаз|век|веки|зрач', 'eyes'), (r'рот|рта|губ', 'mouth'), (r'нос', 'nose'), (r'бров', 'brows'),
    (r'ух[оау]|уш', 'ears'), (r'ше[яиюей]', 'neck'), (r'хвост', 'ponytail'), (r'лиц[оае]|лицу|щёк|щек|скул', 'face'),
    (r'срез\w* шеи|низ шеи|дно шеи', 'cut'), (r'волос|причёск|прическ|макушк|затыл', 'hair'),
]
INTENT_WORDS = [
    (r'сглад|ровн|склад|осколк|остр|гран|кривы|странн|морщ|мят', 'smooth'),
    (r'форм|плёнк|пленк|ям|дыр|провал|срезан|обрез', 'shape'),
    (r'выдав|выпукл|вперёд|вперед|толщ', 'inflate'), (r'вдав|впал|утоп|тоньш', 'deflate'),
    (r'(убр|убер|стер|без|нет|снять|сним)\w*\s+(\w+\s+)?волос|волос\w*\s+(\w+\s+)?(на|с|со)\s', 'hair_off'),
    (r'цвет|текстур|перекрас|окрас|краск|красн|светл|темн|тёмн', 'colour'),
    (r'шум|пятн|крапин|точк|размы', 'denoise'),
    (r'симметр|перекош|кривое лицо|разн\w* (уш|глаз|щёк|щек)', 'asym'), (r'шип|игл|торч|осколок', 'spike'),
    (r'вылез|раздут|оригинал|эталон|силуэт|лишн\w* объём|лишн\w* объем', 'outside'),
    (r'(кож\w*|светл\w*)\s+(\w+\s+)?(на|в)\s+(волос|хвост)|(волос|хвост)\w*\s+(\w+\s+)?(в|со?)\s+(\w+\s+)?(кож|светл|пятн)', 'skin_off'),
]
INTENT_TOOLS = {  # intent -> tools (priors, score points)
    'smooth': {'relax': 4, 'membrane': 3},
    'shape': {'membrane': 4, 'relax': 2, 'push': 1},
    'inflate': {'push': 5}, 'deflate': {'push': 5},
    'hair_off': {'hair_to_skin': 5, 'repaint': 3},
    'colour': {'repaint': 4, 'blur': 1, 'lama': 2},
    'denoise': {'blur': 4, 'repaint': 2, 'skin_to_hair': 2, 'lama': 3},
    'skin_off': {'skin_to_hair': 5, 'blur': 1},
    # the defects head_views.py finds (head_auto.py), and the prompt words above
    'outside': {'hull': 5, 'snap': 3, 'relax': 1},
    'asym': {'mirror': 5, 'relax': 1},
    'spike': {'despike': 5, 'relax': 3},
    'fold': {'relax': 4, 'membrane': 2, 'despike': 1},
    'flip': {'orient': 5},
    'wrong_class': {'skin_to_hair': 4, 'hair_to_skin': 4, 'repaint': 2, 'lama': 2},
}
PART_TOOLS = {  # what usually helps a part before anything is learned
    'eyes': {'membrane': 2, 'relax': 2, 'repaint': 1}, 'mouth': {'relax': 1, 'repaint': 1}, 'nose': {'relax': 1},
    'ears': {'relax': 1, 'repaint': 1}, 'neck': {'hair_to_skin': 2, 'repaint': 1}, 'cut': {'hair_to_skin': 2},
    'ponytail': {'skin_to_hair': 2, 'relax': 1}, 'face': {'repaint': 1}, 'hair': {'relax': 1}, 'brows': {'repaint': 1},
}


def parse_prompt(text):
    """Russian prompt -> (parts, intents). Keyword rules (a local LLM may replace this function: same output)."""
    t = ' ' + (text or '').lower().replace('ё', 'е') + ' '
    intents = [i for pat, i in INTENT_WORDS if re.search(pat.replace('ё', 'е'), t)]
    parts = []
    for pat, p in PART_WORDS:
        if re.search(r'(?<![а-я])(' + pat.replace('ё', 'е') + ')', t) and p not in parts:
            parts.append(p)
    if 'hair_off' in intents and len(parts) > 1 and 'hair' in parts:
        parts.remove('hair')  # «убрать волосы с шеи»: the region is the neck, the hair is what goes
    if 'deflate' in intents and 'inflate' in intents:
        intents.remove('inflate')
    return parts, intents


# ---------- the policy ----------

def load_policy(path):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return {'ctx': {}, 'part': {}, 'arm': {}, 'runs': 0}


def save_policy(pol, path):
    tmp = path + '.tmp'
    json.dump(pol, open(tmp, 'w'), ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def update(stat, r):
    n, m = stat
    return [n + 1, m + (r - m) / (n + 1)]


def context(parts, intents):
    return '+'.join(sorted(parts)) or 'custom', '+'.join(sorted(intents)) or 'fix'


def estimates(pol, parts, intents, arms=ARMS):
    """{arm: (estimate, tries in the context, prior)}: the context mean when tried there, else the mean over the parts,
    else overall, shrunk to the prior by the number of tries."""
    ck = '|'.join(context(parts, intents))
    out = {}
    for a in arms:
        aid = arm_id(a)
        prior = sum(INTENT_TOOLS.get(i, {}).get(a[0], 0) for i in intents) + \
            sum(PART_TOOLS.get(p, {}).get(a[0], 0) for p in parts)
        if 'inflate' in intents and a[0] == 'push' and a[1]['amount'] < 0 or \
                'deflate' in intents and a[0] == 'push' and a[1]['amount'] > 0:
            prior -= 5
        n, m = pol['ctx'].get(ck, {}).get(aid, [0, 0.])
        if n == 0:
            st = [pol['part'].get(p, {}).get(aid, [0, 0.]) for p in parts]
            pn = sum(s[0] for s in st)
            if pn:
                n_, m = 0, sum(s[0] * s[1] for s in st) / pn
                est = (pn * m + 2 * prior) / (pn + 2)
            else:
                g = pol['arm'].get(aid, [0, 0.])
                est = (g[0] * g[1] + 2 * prior) / (g[0] + 2)
        else:
            est = (n * m + prior) / (n + 1)
        out[aid] = (est, n, prior)
    return out


def allowed(intents):
    """Arms the intents allow: a prompt about colour does not move the mesh and the other way round."""
    if not intents:
        return ARMS
    tools = set()
    for i in intents:
        tools |= set(INTENT_TOOLS[i])
    return [a for a in ARMS if a[0] in tools]


class Agent:
    def __init__(self, head, mask, parts, intents, work, policy=POLICY, log=lambda s: print(s, flush=True)):
        self.h, self.mask, self.parts, self.intents = head, mask, parts, intents
        self.work, self.policy_path, self.log = work, policy, log
        self.pol = load_policy(policy)
        self.passes, self.stop = [], False
        self.repaint = 'all'  # views to repaint a region after a geometry tool ('' = keep the texture as it is)
        os.makedirs(os.path.join(work, 'passes'), exist_ok=True)
        self.pics = ht.render(head)
        self.score = ht.region_score(head, mask, self.pics)
        self.history = [self.score['score']]
        self.state()

    def weights(self):
        est = estimates(self.pol, self.parts, self.intents)
        return [{'arm': k, 'estimate': round(v[0], 2), 'tries': v[1], 'prior': v[2]} for k, v in
                sorted(est.items(), key=lambda kv: -kv[1][0])]

    def state(self, running=False, extra=None):
        s = {'time': time.time(), 'running': running, 'parts': self.parts, 'intents': self.intents,
             'context': '|'.join(context(self.parts, self.intents)), 'score': self.score, 'history': self.history,
             'passes': self.passes, 'weights': self.weights(), 'model': self.h.path, **(extra or {})}
        tmp = os.path.join(self.work, 'state.json.tmp')
        json.dump(s, open(tmp, 'w'), ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(self.work, 'state.json'))

    def learn(self, aid, r):
        ck = '|'.join(context(self.parts, self.intents))
        self.pol['ctx'].setdefault(ck, {})[aid] = update(self.pol['ctx'].get(ck, {}).get(aid, [0, 0.]), r)
        for p in self.parts:
            self.pol['part'].setdefault(p, {})[aid] = update(self.pol['part'].get(p, {}).get(aid, [0, 0.]), r)
        self.pol['arm'][aid] = update(self.pol['arm'].get(aid, [0, 0.]), r)
        save_policy(self.pol, self.policy_path)

    def choose(self, tabu):
        est = estimates(self.pol, self.parts, self.intents)
        cand = [a for a in allowed(self.intents) if arm_id(a) not in tabu]
        if not cand:
            return None
        total = sum(v[1] for v in est.values()) + 1
        return max(cand, key=lambda a: est[arm_id(a)][0] + UCB_C * math.sqrt(math.log(total + 1) / (est[arm_id(a)][1] + 1)))

    def step(self, arm, learn=True):
        """Apply one arm; keep it when the region got better. Returns the pass record."""
        aid = arm_id(arm)
        t0 = time.time()
        trial = self.h.copy()
        note = ht.apply(trial, arm[0], self.mask, **arm[1])
        if ht.TOOLS[arm[0]][3] == 'geometry' and self.repaint:  # the texture follows the new shape: painted from the views
            note += '; ' + ht.apply(trial, 'repaint', ht.grow(trial, self.mask, 1), views=self.repaint)
        pics = ht.render(trial)
        sc = ht.region_score(trial, self.mask, pics)
        reward = sc['score'] - self.score['score']
        keep = reward > ACCEPT
        i = len(self.passes) + 1
        d = os.path.join(self.work, 'passes', f'{i:03d}')
        os.makedirs(d, exist_ok=True)
        ht.pass_picture(self.pics, pics, self.mask, trial, os.path.join(d, 'pass.png'),
                        f'{i}: {aid}  {self.score["score"]} -> {sc["score"]}  {"принят" if keep else "откат"}')
        if learn:
            self.learn(aid, float(np.clip(reward, -20, 20)))
        rec = {'n': i, 'arm': aid, 'note': note, 'before': self.score, 'after': sc, 'reward': round(reward, 2),
               'kept': keep, 'seconds': round(time.time() - t0, 1), 'picture': f'passes/{i:03d}/pass.png'}
        self.trial = (trial, pics, sc)
        if keep:
            self.h, self.pics, self.score = trial, pics, sc
            self.h.save(os.path.join(self.work, 'current.glb'))
            rec['model'] = 'current.glb'
        self.history.append(self.score['score'])
        self.passes.append(rec)
        json.dump(rec, open(os.path.join(d, 'pass.json'), 'w'), ensure_ascii=False, indent=1)
        self.log(f"pass {i}: {aid}: {rec['before']['score']} -> {sc['score']} ({reward:+.2f}) {'kept' if keep else 'rolled back'}; {note}")
        self.state(True)
        return rec

    def run(self, passes=8):
        self.pol['runs'] = self.pol.get('runs', 0) + 1
        tabu = set()
        for _ in range(passes):
            if self.stop:
                break
            arm = self.choose(tabu)
            if arm is None:
                self.log('every allowed tool was tried since the last gain: stop')
                break
            rec = self.step(arm)
            if rec['kept']:
                tabu = {rec['arm']} if rec['reward'] < 1 else set()  # a small gain: try the others before repeating it
            else:
                tabu.add(rec['arm'])
        self.state(False)
        return self.h


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
    parts_file = opt('--parts')
    spec = opt('--region')
    prompt = opt('--prompt', default='')
    passes = int(opt('--passes', default=8))
    policy = opt('--policy', default=POLICY)
    ref_dir, game, model = opt('--ref'), opt('--game', default='pdm-game'), opt('--model', default='hero1')
    check = '--check' in a
    a = [x for x in a if x != '--check']
    src, dst = a[:2]
    work = opt('--work', default=os.path.splitext(dst)[0] + '_agent')
    views = {n: ht.pv.load_view(p) for n, p in zip(ht.pv.NAMES, vp)}
    pp, intents = parse_prompt(prompt)
    spec = spec or ','.join(pp)
    parts = [p for p in spec.split('~')[0].split(',') if p and not p.startswith('faces:')]
    if not spec:
        raise SystemExit('no region: --region eyes,neck[~rings] or a prompt that names a part')
    print('region', spec, 'intents', intents, flush=True)
    h = ht.Head(src, views, parts_file)
    if ref_dir:  # the reference shape for hull, snap, mirror (head_views.py)
        import head_views as hv
        h.ref = hv.Reference(game, model, ref_dir)
        h.fit = hv.fit_frame(h.P, h.tris, h.ref)
        h.ref.adopt(h)
    mask = ht.region(h, spec)
    if check:
        r0 = ht.hc.check(src, views)
        print('head_check before', r0['score'])
    ag = Agent(h, mask, parts, intents, work, policy)
    h = ag.run(passes)
    h.save(dst)
    print(f"region score {ag.history[0]} -> {ag.history[-1]}, {sum(p['kept'] for p in ag.passes)} of {len(ag.passes)} passes kept")
    if check:
        print('head_check after', ht.hc.check(dst, views)['score'])
    print('->', dst, work)


if __name__ == '__main__':
    main()
