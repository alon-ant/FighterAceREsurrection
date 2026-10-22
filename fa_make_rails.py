#!/usr/bin/env python3
r"""
fa_make_rails.py - turn the client's AI::ROADMAP dump into the server's rails_trnNN.json.

Trains run only on terrains that have a rails file next to server.py. Steps, per terrain:
  1. Enter an arena on that terrain (offline training arena is fine) so the client builds its
     ROADMAP for it.
  2. python fa_dump_tank_tables.py        -> writes roadmap.json (roads + nodes + stations)
  3. python fa_make_rails.py --trn <N>     -> writes rails_trnNN.json
  4. restart the server (or `train` console verbs pick the file up on the next supply tick).

roadmap.json nodes are [x, y, z, ?, ?, ?, cumulative_m]; the server wants [x, y, alt, cumulative_m].
"""
import os, sys, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
MAPDATA = os.path.join(HERE, 'mapdata')        # v742f5: terrain / TC data folder
os.makedirs(MAPDATA, exist_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--trn', type=int, required=True, help='terrain number (2 = Mediterrain, 5 = Circle, ...)')
    ap.add_argument('--roadmap', default=os.path.join(MAPDATA, 'roadmap.json'))
    ap.add_argument('--out', default=None)
    ap.add_argument('--station-radius', type=float, default=None,
                    help='metres from a rail node for a scene to count as a station (server default 900; '
                         'English Channel needs ~2000). Written into the rails file, the server honours it.')
    args = ap.parse_args()
    rm = json.load(open(args.roadmap))
    roads_out = []
    for r in rm.get('roads') or []:
        nodes = []
        for n in r.get('nodes') or []:
            # roadmap node layout (fa_dump_tank_tables): [?, z, x, y, ?, ?, cumulative]. v730f5: the
            # first version took [0],[1],[2],[6] and produced [0.0, z, x, cum] - no Y at all, so no
            # scene was near a rail and the station table came out empty (user 09-16).
            if len(n) >= 7:
                nodes.append([float(n[2]), float(n[3]), float(n[1]), float(n[6])])
            elif len(n) == 4:
                nodes.append([float(v) for v in n])
        if len(nodes) < 2:
            continue
        roads_out.append({'index': int(r['index']), 'loop': int(r.get('loop', 0) or 0),
                          'length': float(r['length']), 'nodes': nodes})
    if not roads_out:
        sys.exit('no roads in the roadmap dump - was the game IN an arena when fa_dump_tank_tables.py ran?')
    out = args.out or os.path.join(MAPDATA, f'rails_trn{args.trn:02d}.json')
    # sanity: the nodes must span a real 2-D area, or the column mapping is wrong again
    _xs = [nd[0] for r in roads_out for nd in r['nodes']]; _ys = [nd[1] for r in roads_out for nd in r['nodes']]
    if max(_xs) - min(_xs) < 1000.0 or max(_ys) - min(_ys) < 1000.0:
        sys.exit(f'refusing to write {out}: the node X/Y span looks wrong '
                 f'(x {min(_xs):.0f}..{max(_xs):.0f}, y {min(_ys):.0f}..{max(_ys):.0f}) - check the roadmap node layout')
    _doc = {'terrain': args.trn, 'roads': roads_out}
    if args.station_radius:
        _doc['station_radius'] = float(args.station_radius)
    json.dump(_doc, open(out, 'w'))
    st = rm.get('stations') or []
    print(f'wrote {out}: {len(roads_out)} road(s), {sum(len(r["nodes"]) for r in roads_out)} node(s), '
          f'{len(st)} station entr{"y" if len(st) == 1 else "ies"} in the dump '
          f'(the server derives stations itself from scenes within {900} m of the rails)')
    for r in roads_out:
        print(f'  road {r["index"]}: {r["length"]:.0f} m, {len(r["nodes"])} nodes, loop={r["loop"]}')


if __name__ == '__main__':
    main()
