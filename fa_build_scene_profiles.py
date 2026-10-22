#!/usr/bin/env python3
r"""
fa_build_scene_profiles.py - the 2009 production model, rebuilt from the client's own tables.

Inputs (both produced from a running FA.exe with the offline training arena loaded):
  trn_tables_trnNN.json   (fa_dump_trn_tables.py v2: 'got' with prod_kind/prod_index, 'goi' objects
                           with their scene, 'gsi' scenes)
  fa_memdump.json         (fa_memdump.py: 'defs' = RESOURCE_STORAGE_DEF / RESOURCE_PRODUCER_DEF /
                           UNIT_PRODUCER_DEF, 'aggregates' = the client's per-camp rate/stored)

Every building class carries PRODUCTION NUMBER = kind*1000 + index (FA.exe FUN_00568fe0):
  kind 0 -> RESOURCE_STORAGE_DEF[index]  = [resource][max_storage]
  kind 1 -> RESOURCE_PRODUCER_DEF[index] = [resource][max_storage][rate_per_min][?]
  kind 2 -> UNIT_PRODUCER_DEF[index]     = [unit][resource][max_storage][rate_per_min][cost][flags]
A scene's capacity = sum of its storage + producer stores; its production = sum of its producers;
its unit producers convert stored metal into units. That is what the offline arena runs.

Output: fa_scene_profiles_trnNN.json  {scene_idx: {name, camp, caps, rates, unit_producers,
        buildings}}  + per-camp totals printed next to the offline aggregates for comparison.

Usage: python fa_build_scene_profiles.py [--trn 2] [--memdump fa_memdump.json]
"""
import os, sys, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
RES = {0: 'metal', 1: 'fuel', 2: 'ammo'}
UNIT = {0: 'aircraft', 1: 'tank', 2: 'ship'}


def load_defs(md):
    defs = md.get('defs') or {}
    lens = md.get('def_lengths') or {}
    rs = defs.get('resource_storage_def') or []
    rp = defs.get('resource_producer_def') or []
    up = defs.get('unit_producer_def') or []
    # the producer array was over-read in the August dump (the heuristic walked into the storage
    # array); cut it at the file-object length
    def _n(v, default):
        if isinstance(v, dict):
            v = v.get('count')
        return int(v) if v else default
    n_rp = _n(lens.get('resource_producer_def'), len(rp))
    n_rs = _n(lens.get('resource_storage_def'), len(rs))
    n_up = _n(lens.get('unit_producer_def'), len(up))
    rs = rs[:n_rs]; rp = rp[:n_rp]; up = up[:n_up]
    storage = [{'resource': r['resource'], 'max': int(r['max_storage'])} for r in rs]
    producer = []
    for r in rp:
        raw = r.get('raw') or [0, 0, 0, 0]
        producer.append({'resource': RES.get(raw[0], raw[0]), 'max': int(raw[1]),
                         'rate_per_min': int(raw[2]), 'f3': int(raw[3])})
    unitp = [{'unit': u['unit'] if isinstance(u['unit'], str) else UNIT.get(u['unit'], u['unit']),
              'resource': u['resource'], 'max': int(u['max_storage']),
              'rate_per_min': int(u['rate_per_min']), 'cost': int(u['cost']), 'flags': u.get('flags')}
             for u in up]
    return storage, producer, unitp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--trn', type=int, default=2)
    ap.add_argument('--memdump', default=None, help='default: mapdata\\fa_memdump_trnNN.json, else fa_memdump.json')
    ap.add_argument('--tables', default=None)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    if args.memdump is None:
        args.memdump = f'fa_memdump_trn{args.trn:02d}.json' if os.path.exists(os.path.join(HERE, 'mapdata', f'fa_memdump_trn{args.trn:02d}.json')) else 'fa_memdump.json'
    # v958f5g: terrain data lives in mapdata\ next to server.py (falls back to this directory)
    MAPDATA = os.path.join(HERE, 'mapdata')
    def _find(name):
        for d in (MAPDATA, HERE):
            if os.path.exists(os.path.join(d, name)):
                return os.path.join(d, name)
        return os.path.join(MAPDATA, name)
    tables = args.tables or _find(f'trn_tables_trn{args.trn:02d}.json')
    memdump = args.memdump if os.path.exists(args.memdump) else _find(os.path.basename(args.memdump))
    if not os.path.exists(tables):
        sys.exit(f'{tables} not found - run fa_dump_trn_tables.py with terrain {args.trn} loaded first')
    if not os.path.exists(memdump):
        sys.exit(f'{memdump} not found - run fa_memdump.py --dump --out mapdata\\fa_memdump_trn{args.trn:02d}.json first')
    print(f'tables : {tables}\nmemdump: {memdump}')
    tt = json.load(open(tables))
    md = json.load(open(memdump))
    storage, producer, unitp = load_defs(md)
    got = tt['got']; goi = tt['goi']; gsi = tt['gsi']
    if not any('prod_num' in g for g in got):
        sys.exit('the tables file has no prod_num - re-run fa_dump_trn_tables.py (v2) with the arena loaded')

    scenes = {}
    for s in gsi:
        scenes[s['i']] = {'name': s.get('type_name'), 'camp': s.get('camp'), 'x': s['x'], 'y': s['y'],
                          'caps': {'metal': 0, 'fuel': 0, 'ammo': 0},
                          'rates': {'metal': 0, 'fuel': 0, 'ammo': 0},
                          'unit_producers': [], 'buildings': []}
    unknown = set()
    for o in goi:
        si = o.get('scene')
        if si is None or si < 0 or si not in scenes:
            continue
        g = got[o['type']] if 0 <= o['type'] < len(got) else None
        if not g:
            continue
        pk, pi = g.get('prod_kind'), g.get('prod_index')
        if pk is None:
            continue
        sc = scenes[si]
        entry = {'obj': o['i'], 'class': o['type'], 'name': g['name'], 'kind': pk, 'index': pi}
        if pk == 0 and pi < len(storage):
            d = storage[pi]; sc['caps'][d['resource']] += d['max']; entry.update(d)
        elif pk == 1 and pi < len(producer):
            d = producer[pi]; sc['caps'][d['resource']] += d['max']
            sc['rates'][d['resource']] += d['rate_per_min']; entry.update(d)
        elif pk == 2 and pi < len(unitp):
            d = unitp[pi]; sc['unit_producers'].append(dict(d)); entry.update(d)
        else:
            unknown.add((pk, pi, g['name']))
        sc['buildings'].append(entry)

    os.makedirs(MAPDATA, exist_ok=True)
    out = args.out or os.path.join(MAPDATA, f'fa_scene_profiles_trn{args.trn:02d}.json')
    json.dump({'terrain': args.trn, 'defs': {'storage': storage, 'producer': producer, 'unit': unitp},
               'scenes': {str(k): v for k, v in scenes.items()}}, open(out, 'w'), indent=1)
    print(f'wrote {out}: {len(scenes)} scenes')
    if unknown:
        print('UNRESOLVED production numbers (def index beyond the dumped tables):')
        for u in sorted(unknown):
            print('  ', u)

    # per-camp totals vs the client's own aggregates
    totals = {}
    for sc in scenes.values():
        c = sc['camp']
        t = totals.setdefault(c, {'cap': {'metal': 0, 'fuel': 0, 'ammo': 0}, 'rate': {'metal': 0, 'fuel': 0, 'ammo': 0}})
        for r in ('metal', 'fuel', 'ammo'):
            t['cap'][r] += sc['caps'][r]; t['rate'][r] += sc['rates'][r]
    agg = (md.get('aggregates') or {})
    if isinstance(agg, list):
        agg = agg[-1] if agg else {}
    _RIDX = {'metal': 0, 'fuel': 1, 'ammo': 2}          # resource enum order = used_resource_ids slot order
    def _agg(kind, c, r):
        d = (agg.get(kind) or {}).get(f'camp{c}', {}) or {}
        for k, v in d.items():
            if str(k).startswith(r):
                return v
        ids = agg.get('used_resource_ids') or []
        i = _RIDX.get(r)
        if i is not None and i < len(ids):                 # v958f5g: dumps key the slots 'res<id>(id<id>)'
            for k, v in d.items():
                if str(k).startswith(f'res{ids[i]}'):
                    return v
        return None
    print(f'used resource ids (client aggregate slot order): {agg.get("used_resource_ids")}')
    print('\ncamp  resource   computed rate/min   client rate   computed cap   client stored')
    for c in sorted(totals):
        for r in ('metal', 'fuel', 'ammo'):
            cr = _agg('production_rate', c, r)
            cs = _agg('stored', c, r)
            print(f'{c:4d}  {r:8s}   {totals[c]["rate"][r]:15d}   {str(cr):>11s}   {totals[c]["cap"][r]:12d}   {str(cs):>13s}')
    print('\nper scene:')
    for k in sorted(scenes, key=int):
        sc = scenes[k]
        if sc['buildings']:
            up = ','.join(f'{u["unit"]}:{u["rate_per_min"]}/min' for u in sc['unit_producers'])
            print(f'  {k:3d} c{sc["camp"]} {sc["name"]:22s} caps m/f/a {sc["caps"]["metal"]:6d}/{sc["caps"]["fuel"]:6d}/{sc["caps"]["ammo"]:6d}'
                  f'  rates {sc["rates"]["metal"]:5d}/{sc["rates"]["fuel"]:5d}/{sc["rates"]["ammo"]:5d}  units {up}')


if __name__ == '__main__':
    main()
