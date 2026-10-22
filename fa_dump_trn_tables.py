#!/usr/bin/env python3
r"""
fa_dump_trn_tables.py - rip the loaded terrain TABLE arrays (gst/gat/got/gsi/goi) out of a
live FA.exe and emit the AUTHORITATIVE ground-object -> scene mapping the server needs.

READ-ONLY (ReadProcessMemory only). Run the game, enter the TC arena (the terrain must be
LOADED - the tables exist only in a full world), then:

    python fa_dump_trn_tables.py            # -> mapdata\trn_tables_trnNN.json

WHY THIS WORKS (all from the terrain loader FUN_0055f040, Trn.cpp, decompiled 2026-08-16):
    The client loads five flat tables per terrain from its own archives and keeps them in
    memory behind fixed globals (FA.exe base 0x400000, no ASLR):

        global        ptr @        count @      rec   struct (FA3::)
        gst  scene    0x00c85028   0x00c84fec   0x30  SCENE_TYPE_DEF        (names!)
        gat  airfield 0x00c8502c   0x00c84ff0   0x10  AIRFIELD_TYPE_DEF
        got  gobject  0x00c85030   0x00c84ff4   0xc0  GROUND_OBJECT_TYPE_DEF
        gsi  sceneins 0x00c85034   0x00c84ff8   0x18  SCENE_INST_DEF
        goi  gobjins  0x00c85038   0x00c84ffc   0x2c  GROUND_OBJECT_INST_DEF
        terrain number             0x00c84fe8   (int)

    * PARR<TRN_SCENE*> is created size=nSceneInst and filled IN gsi ROW ORDER ->
      **the msg-36 scene index IS the gsi row index**.
    * PARR<TRN_OBJECT*> is created size=nGroundObjectInst and filled IN goi ROW ORDER ->
      **the msg-31 ground-object index IS the goi row index**.
    * goi rec: +0 TypeIndex(got) ; +4 SceneInstIndex(gsi)  <- THE OBJ->SCENE MAPPING
               +8 f32 X ; +0xc f32 Y ; rest dumped raw.
    * gsi rec: +0 SceneTypeIndex(gst) ; +4 flags (low nibble = CAMP - printed as column 2 of
               the client's 'Info TRNnn - scenes with valuable objects' listing) ;
               +8 f32 X ; +0xc f32 Y ; rest raw.
    * got rec: +0xa0 s32 Value (>0 = 'valuable'/destructible-for-score; <0 = decoration and
               the loader SKIPS creating a TRN_OBJECT for it) ; +0xb0 s32 radius-ish ;
               +0xb4 s32 Category (1/2/3 gated by arena settings) ; +0xbc u8 destroy-mode
               (FUN_00568eb0: 2 = never, 1 = local-kill path). Name = leading char field.
    * gst rec: name char[...] + floats (data00_scenes.json layout: name/h/cls/flag/link).

The emitted JSON also contains the derived tables the server loads directly:
    obj_to_scene   { goiRow: gsiRow }                      (msg-31 obj -> msg-36 scene)
    scene_objects  { gsiRow: [ {obj,type,name,value}, ] }  (destructibles only, value>0)
    scene_info     { gsiRow: {camp,type,name,x,y,total_value,n_destructible} }
"""
import os, sys, json, struct, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fa_memdump import find_processes, Mem, FA_NAMES   # reuse the proven win32 plumbing

TBL = {
    #        ptr addr     count addr   rec size
    'gst': (0x00c85028, 0x00c84fec, 0x30),
    'gat': (0x00c8502c, 0x00c84ff0, 0x10),
    'got': (0x00c85030, 0x00c84ff4, 0xc0),
    'gsi': (0x00c85034, 0x00c84ff8, 0x18),
    'goi': (0x00c85038, 0x00c84ffc, 0x2c),
}
TERRAIN_NO = 0x00c84fe8


def _name_from(rec, maxlen=48):
    """Leading NUL-terminated printable run (both gst and got start with a name field)."""
    out = []
    for b in rec[:maxlen]:
        if b == 0:
            break
        if 32 <= b < 127:
            out.append(chr(b))
        else:
            break
    return ''.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pid', type=int, help='FA.exe pid (default: auto-detect)')
    ap.add_argument('--out', help='output json path (default: trn_tables_trnNN.json)')
    args = ap.parse_args()

    pid = args.pid
    if pid is None:
        cands = [(p, n) for p, n in find_processes() if n in FA_NAMES]
        if not cands:
            sys.exit('No FA.exe process found - start the game and load the arena first.')
        pid = cands[0][0]
        print(f'Attached to {cands[0][1]} pid={pid}')
    m = Mem(pid)

    trn = m.u32(TERRAIN_NO)
    raw = {}
    counts = {}
    for name, (paddr, caddr, rsz) in TBL.items():
        ptr, cnt = m.u32(paddr), m.u32(caddr)
        if not ptr or not cnt or cnt > 100000:
            sys.exit(f'{name}: ptr=0x{ptr or 0:08x} count={cnt} - arena not loaded yet? '
                     f'(enter the game world first)')
        data = m.read(ptr, cnt * rsz)
        if data is None:
            sys.exit(f'{name}: ReadProcessMemory failed at 0x{ptr:08x} ({cnt}x{rsz}B)')
        raw[name] = data
        counts[name] = cnt
        print(f'{name}: {cnt} recs x 0x{rsz:02x} @ 0x{ptr:08x}')

    # ---- decode ----
    gst = []
    for i in range(counts['gst']):
        r = raw['gst'][i*0x30:(i+1)*0x30]
        gst.append({'i': i, 'name': _name_from(r), 'raw_tail': r[32:].hex()})

    got = []
    for i in range(counts['got']):
        r = raw['got'][i*0xc0:(i+1)*0xc0]
        _pn = struct.unpack_from('<i', r, 0xb8)[0]        # v2: PRODUCTION NUMBER = kind*1000 + def index
        got.append({
            'i': i, 'name': _name_from(r, 64),
            'value':    struct.unpack_from('<i', r, 0xa0)[0],
            'life':     struct.unpack_from('<i', r, 0xa8)[0],   # v2 (FUN_00568fe0: x GAME_DEF+0x400 %)
            'repair':   struct.unpack_from('<i', r, 0xac)[0],   # v2
            'radius':   struct.unpack_from('<i', r, 0xb0)[0],
            'category': struct.unpack_from('<i', r, 0xb4)[0],
            'prod_num': _pn,
            # v2: FUN_00568fe0 (Trn_Obj.cpp:0x94): kind 0 -> FUN_00566f10 (RESOURCE_STORAGE_DEF, 8 B),
            # 1 -> FUN_00567f10 (RESOURCE_PRODUCER_DEF, 16 B), 2 -> FUN_00566220 (UNIT_PRODUCER_DEF, 24 B)
            'prod_kind': (_pn // 1000) if _pn >= 0 else None,
            'prod_index': (_pn % 1000) if _pn >= 0 else None,
            'destroy_mode': r[0xbc],
        })

    gsi = []
    for i in range(counts['gsi']):
        r = raw['gsi'][i*0x18:(i+1)*0x18]
        st, fl = struct.unpack_from('<iI', r, 0)
        x, y = struct.unpack_from('<ff', r, 8)
        gsi.append({'i': i, 'scene_type': st, 'camp': fl & 0xf, 'flags': fl,
                    'x': x, 'y': y, 'tail': r[16:].hex(),
                    'type_name': gst[st]['name'] if 0 <= st < len(gst) else None})

    goi = []
    for i in range(counts['goi']):
        r = raw['goi'][i*0x2c:(i+1)*0x2c]
        ti, si = struct.unpack_from('<ii', r, 0)
        x, y = struct.unpack_from('<ff', r, 8)
        goi.append({'i': i, 'type': ti, 'scene': si, 'x': x, 'y': y, 'tail': r[16:].hex()})

    # ---- derived server tables ----
    obj_to_scene = {}
    scene_objects = {}
    for o in goi:
        t = got[o['type']] if 0 <= o['type'] < len(got) else None
        if o['scene'] is not None and o['scene'] >= 0:
            obj_to_scene[o['i']] = o['scene']
        if t and t['value'] > 0 and o['scene'] >= 0:
            scene_objects.setdefault(o['scene'], []).append(
                {'obj': o['i'], 'type': o['type'], 'name': t['name'], 'value': t['value']})
    scene_info = {}
    for s in gsi:
        objs = scene_objects.get(s['i'], [])
        scene_info[s['i']] = {'camp': s['camp'], 'type': s['scene_type'],
                              'name': s['type_name'], 'x': s['x'], 'y': s['y'],
                              'total_value': sum(o['value'] for o in objs),
                              'n_destructible': len(objs)}

    _md = os.path.join(HERE, 'mapdata'); os.makedirs(_md, exist_ok=True)      # v958f5g: write to mapdata\
    out = args.out or os.path.join(_md, f'trn_tables_trn{trn:02d}.json')
    json.dump({'terrain': trn, 'counts': counts,
               'gst': gst, 'got': got, 'gsi': gsi, 'goi': goi,
               'obj_to_scene': {str(k): v for k, v in obj_to_scene.items()},
               'scene_objects': {str(k): v for k, v in scene_objects.items()},
               'scene_info': {str(k): v for k, v in scene_info.items()}},
              open(out, 'w'), indent=1)
    print(f'\nterrain {trn}: wrote {out}')
    print(f'  {len(obj_to_scene)} obj->scene entries, '
          f'{sum(1 for v in scene_info.values() if v["n_destructible"])} scenes with '
          f'destructible objects')
    # sanity echo of the client's own 'valuable objects' listing for eyeballing
    for k in sorted(scene_info, key=int):
        v = scene_info[k]
        if v['n_destructible']:
            print(f'  {int(k):3d} {v["camp"]} {v["total_value"]:5d} {v["name"]} '
                  f'({v["n_destructible"]} objs)')
    m.close()


if __name__ == '__main__':
    main()
