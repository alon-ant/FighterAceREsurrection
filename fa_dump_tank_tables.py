#!/usr/bin/env python3
r"""
fa_dump_tank_tables.py - read the two tables the tank-spawn work needs straight out of a
running FA.exe (READ-ONLY, ReadProcessMemory - same plumbing as fa_dump_trn_tables.py).

  1. NET create-record header table  @ 0x00a30c98  (static .rdata, readable at the main menu)
        FUN_007e4e00 walks msg-2 records with  HeaderSize = table[Type*3]  (12-byte entries)
        and a fixed 13-byte trailer [St u16][ONumber u16][9x0]. Known: Type 0 (client) = 35,
        Type 1 (plane) = 28, Type 2 (parachuter) = 10. We need Type 3 (NetTank) - and 4..7
        (train/car/ship/soldier) while we're at it.
  2. Tank CLASS list  @ 0x00c891fc  (heap; loaded from AIUNITS\*.tki by FUN_0061d2a0 at
        startup). FUN_0061cd50 (tankfact.cpp:0x19e) matches the create record's rec[1]
        against  *(*(node+0x10)+0x10)  - the numeric class id the server must put in the
        record. Node layout (FUN_00619cf0): object base = node-0x24; base+0x34 = pCTI
        (= node+0x10); pCTI+0x11c = gunsnum (<4); pCTI+0x120.. = gun defs, 0x98 each.

Usage:  python fa_dump_tank_tables.py          -> prints both + writes tank_tables.json
Run with the game at least at the main menu (table 1) / after the arena's AI units loaded
(table 2 - if the list is empty, enter an arena and re-run).
"""
import os, sys, json, struct, string

HERE = os.path.dirname(os.path.abspath(__file__))
# v742f5: terrain / TC data now lives in mapdata\ next to server.py (the tools write there too)
MAPDATA = os.path.join(HERE, 'mapdata')
os.makedirs(MAPDATA, exist_ok=True)
sys.path.insert(0, HERE)
from fa_memdump import find_processes, Mem, FA_NAMES

CREATE_HDR_TABLE = 0x00a30c98
CREATE_HDR_BYTES = 0x80            # up to the next defined item @0xa30d18
TANK_LIST_HEAD   = 0x00c891fc
LIST_LO          = 0x00c891e8      # DAT_00c891e8/ec bracket the load (heap watermark before/after)
LIST_HI          = 0x00c891ec
TYPE_NAMES = {0: 'client', 1: 'plane', 2: 'parachuter', 3: 'tank', 4: 'train', 5: 'car',
              6: 'ship', 7: 'soldier', 8: 'plane(alt)'}
# v2: the float scale constants the tank Unpack (FUN_0061dcf0) and its sub-decoders use.
#   FUN_007ccb20 pos:  X,Y = s24 * a46770 ; Z = u8 * a245e0 - a28f20
#   FUN_007ccf90 dir:  s14 * a32c20 ; Unpack turret/aux s16 * c10f84 ; +0x2f8 s16 * c89298 ;
#   +0x2fc s16 * c89294 (the last two are set on first Unpack: 6.103702e-05 / 1.9175344e-05)
FLOAT_CONSTS = {
    'pos_xy_scale   a46770': 0x00a46770,
    'pos_z_scale    a245e0': 0x00a245e0,
    'pos_z_offset   a28f20': 0x00a28f20,
    'dir_s14_scale  a32c20': 0x00a32c20,
    's16_scale      c10f84': 0x00c10f84,
    'tank_speed_mult c10d80': 0x00c10d80,     # FUN_00617f40: max speed = class+0x74 * this
    'move_dt        a282b4': 0x00a282b4,      # per-frame position step factor
    'one            a2324c': 0x00a2324c,
    'one?           a231f8': 0x00a231f8,
    # v4: soldier Unpack (FUN_0068ebc0) divisors - runtime globals, each scale = 1.0 / value
    'sold_div_c169d0 (bytes 0xc/0xd)': 0x00c169d0,
    'sold_div_c169d4 (aim s16)': 0x00c169d4,
    'sold_div_c169d8 (+0x290 s16)': 0x00c169d8,
    'sold_div_c16a20 (+0x294 s16)': 0x00c16a20,
    # v5: plane/chute family packed position (FUN_007cca00): X s25 | Y s25 | Z u22 bit-packed in 9
    # bytes, X/Y/Z x this double, Z minus a28f20 (500). Needed to read chute landing points.
    'plane_pos_scale a48090': 0x00a48090,
    # v9: train (train.cpp / railcar FUN_006865c0): update u16 speed x c163ac = m/s(?); state 3 target
    # speed = c16de0 x loco class +0x44
    'train_speed_scale c163ac': 0x00c163ac,
    'train_max_mult c16de0': 0x00c16de0,
    'dt_scale a243f0': 0x00a243f0,
}
PRINTABLE = set(bytes(string.printable, 'ascii')) - set(b'\t\n\r\x0b\x0c')


def ascii_runs(blob, minlen=4):
    out, cur = [], bytearray()
    for b in blob:
        if b in PRINTABLE:
            cur.append(b)
        else:
            if len(cur) >= minlen:
                out.append(cur.decode('ascii'))
            cur = bytearray()
    if len(cur) >= minlen:
        out.append(cur.decode('ascii'))
    return out


def dump_create_table(m):
    raw = m.read(CREATE_HDR_TABLE, CREATE_HDR_BYTES)
    if not raw:
        print('!! could not read the create-header table'); return None
    dw = struct.unpack('<%dI' % (len(raw) // 4), raw)
    print(f'create-record header table @0x{CREATE_HDR_TABLE:08x} (dword[{len(dw)}]):')
    print('  ' + ' '.join(f'{d:08x}' for d in dw[:16]))
    print('  ' + ' '.join(f'{d:08x}' for d in dw[16:32]))
    table = {}
    print('  per Type (12-byte entries, HeaderSize = entry[0]; record on the wire = HeaderSize+13):')
    for t in range(0, min(10, len(dw) // 3)):
        e = dw[t * 3:t * 3 + 3]
        table[t] = {'header_size': e[0], 'f1': e[1], 'f2': e[2], 'record_bytes': e[0] + 13}
        print(f'    Type {t} {TYPE_NAMES.get(t, "?"):11s} header={e[0]:3d}  +13 trailer = {e[0] + 13:3d} B   '
              f'(f1=0x{e[1]:x} f2=0x{e[2]:x})')
    return {'raw_dwords': list(dw), 'by_type': table}


def dump_tank_classes(m):
    head = m.u32(TANK_LIST_HEAD)
    print(f'tank class list head @0x{TANK_LIST_HEAD:08x} = 0x{head or 0:08x}  '
          f'(load bracket 0x{m.u32(LIST_LO) or 0:08x}..0x{m.u32(LIST_HI) or 0:08x})')
    out = []
    node, n = head, 0
    seen = set()
    while node and node not in seen and n < 256:
        seen.add(node); n += 1
        base = node - 0x24
        pcti = m.u32(node + 0x10) or 0
        cid = m.u32(pcti + 0x10) if pcti else None
        guns = m.u32(pcti + 0x11c) if pcti else None
        blob = m.read(pcti, 0x140) if pcti else b''
        names = ascii_runs(blob) if blob else []
        # v3: the physics block FUN_00617f40 reads (class+0x70 reverse speed, +0x74 max speed,
        # +0x7c turn-accel limit, +0x80 accel limit) plus the leading float table for reference
        def _f(off):
            return struct.unpack_from('<f', blob, off)[0] if blob and len(blob) >= off + 4 else None
        phys = {'rev_speed_70': _f(0x70), 'max_speed_74': _f(0x74), 'turn_accel_7c': _f(0x7c),
                'accel_80': _f(0x80), 'f18': _f(0x18), 'f1c': _f(0x1c), 'f20': _f(0x20),
                'f24': _f(0x24), 'f28': _f(0x28), 'f2c': _f(0x2c), 'f30': _f(0x30),
                'f34': _f(0x34), 'f38': _f(0x38), 'f3c': _f(0x3c)}
        rec = {'node': hex(node), 'base': hex(base), 'pcti': hex(pcti), 'class_id': cid,
               'gunsnum': guns, 'pcti_head_hex': blob[:0x90].hex() if blob else '',
               'strings_in_pcti': names[:8], 'phys': phys}
        out.append(rec)
        print(f'  [{n:2d}] node=0x{node:08x} pCTI=0x{pcti:08x} class_id={cid} gunsnum={guns} '
              f'max_speed(+74)={phys["max_speed_74"]} rev(+70)={phys["rev_speed_70"]} '
              f'turn(+7c)={phys["turn_accel_7c"]} accel(+80)={phys["accel_80"]}')
        node = m.u32(node + 4) or 0
    if not out:
        print('  (empty - the .tki set is loaded with the arena; enter a TC arena and re-run)')
    return out


def dump_float_consts(m):
    out = {}
    print('telemetry scale constants:')
    for name, addr in FLOAT_CONSTS.items():
        raw = m.read(addr, 8)
        f = struct.unpack('<f', raw[:4])[0] if raw else None
        d = struct.unpack('<d', raw)[0] if raw and len(raw) == 8 else None
        out[name] = {'addr': hex(addr), 'f32': f, 'f64': d, 'hex': raw.hex() if raw else ''}
        print(f'  {name}: f32={f!r}  (1/f32={1.0 / f if f else float("nan"):.6f})  f64={d!r}  raw={raw.hex() if raw else "?"}')
    return out


def dump_soldier_classes(m):
    """v4: soldier class list @0xcab408 (FUN_0068d930, soldinfo.cpp): node+0xc -> info,
    info+0x14 = class id, info+4/+8 = string-table ids of the names; class base = node-0x24."""
    head = m.u32(0x00cab408) or 0
    print(f'soldier class list head @0x00cab408 = 0x{head:08x}')
    out = []
    node, n, seen = head, 0, set()
    while node and node not in seen and n < 64:
        seen.add(node); n += 1
        info = m.u32(node + 0xc) or 0
        cid = m.u32(info + 0x14) if info else None
        s1, s2 = (m.u32(info + 4), m.u32(info + 8)) if info else (None, None)
        blob = m.read(info, 0x60) if info else b''
        rec = {'node': hex(node), 'info': hex(info), 'class_id': cid, 'name_str_ids': [s1, s2],
               'info_head_hex': blob.hex() if blob else ''}
        out.append(rec)
        print(f'  [{n:2d}] node=0x{node:08x} info=0x{info:08x} class_id={cid} name_str_ids={s1},{s2}')
        node = m.u32(node + 4) or 0
    if not out:
        print('  (empty - enter an arena with soldiers/paratroops loaded and re-run)')
    return out



def dump_car_classes(m):
    """v10 (2026-10-23): CAR class list @0xcab130 (FUN_0067fe30, carinfo.cpp: 'Create NetCar'):
    node+0x10 -> info, info+0x1c = class id (the msg-2 record byte [1]); the info head carries the
    string-table ids of the names like the wagon/soldier records; class base = node-0x24."""
    head = m.u32(0x00cab130) or 0
    print(f'car class list head @0x00cab130 = 0x{head:08x}')
    out = []
    node, n, seen = head, 0, set()
    while node and node not in seen and n < 64:
        seen.add(node); n += 1
        info = m.u32(node + 0x10) or 0
        cid = m.u32(info + 0x1c) if info else None
        head_ids = [m.u32(info + i * 4) for i in range(7)] if info else []
        blob = m.read(info, 0x120) if info else b''
        base = m.read(node - 0x24, 0x40) if node > 0x24 else b''
        def _f(off):
            return struct.unpack_from('<f', blob, off)[0] if blob and len(blob) >= off + 4 else None
        rec = {'node': hex(node), 'info': hex(info), 'class_id': cid, 'head_dwords': head_ids,
               'info_head_hex': blob.hex() if blob else '', 'base_hex': base.hex() if base else '',
               'strings_in_info': ascii_runs(blob) if blob else [],
               'floats': {hex(o): _f(o) for o in range(0x20, 0xa0, 4)}}
        out.append(rec)
        print(f'  [{n:2d}] node=0x{node:08x} info=0x{info:08x} class_id={cid} head={head_ids}')
        node = m.u32(node + 4) or 0
    if not out:
        print('  (empty - the car .tki set loads with the arena; enter a TC arena and re-run)')
    return out

def dump_film_table(m):
    """v6: FILM record-type table (FilmRea3.cpp). Handler xrefs land at 0xc2c2d8 / 0xc2c330 (stride
    0x2c?) - dump the raw region so the (type -> size, callback) layout can be solved offline, and
    list every dword that looks like a code pointer into the film-reader area."""
    base, size = 0x00c2c000, 0x1800
    raw = m.read(base, size)
    if not raw:
        print('!! could not read the film table region'); return None
    open(os.path.join(HERE, 'film_table.bin'), 'wb').write(raw)
    hits = []
    for off in range(0, len(raw) - 3, 4):
        v = struct.unpack_from('<I', raw, off)[0]
        if 0x007a0000 <= v <= 0x007c0000:
            hits.append((base + off, v))
    print(f'film table region 0x{base:08x}+0x{size:x} -> film_table.bin; {len(hits)} code pointers:')
    for a, v in hits[:80]:
        ctx = raw[a - base - 8:a - base + 12]
        print(f'  @0x{a:08x} -> 0x{v:08x}   ctx {ctx.hex()}')
    return {'base': hex(base), 'size': size, 'code_ptrs': [(hex(a), hex(v)) for a, v in hits]}


def dump_film_sizes(m):
    """v7: FILM tag size table @0xaad790 (FilmFilm.cpp FUN_007835d0 logs FilmTag(tag, table[tag*3]));
    12-byte entries, index = record tag byte, [0] = record size."""
    n = 214
    raw = m.read(0x00aad790, n * 12)
    if not raw:
        print('!! could not read the film size table'); return None
    out = {}
    for t in range(n):
        a, b, c = struct.unpack_from('<III', raw, t * 12)
        out[t] = (a, b, c)
    print('film tag table @0x00aad790 (tag: size, f1, f2):')
    print('  ' + ' '.join(f'{t}:{v[0]}' for t, v in out.items() if v[0]))
    open(os.path.join(HERE, 'film_sizes.bin'), 'wb').write(raw)
    return {str(t): list(v) for t, v in out.items()}


def dump_roadmap(m):
    """v8: the AI::ROADMAP (rails) @DAT_00c88974 (roadmap.cpp). Known from FUN_005c4ae0 /
    FUN_005c4bc0: this+0x10 -> roads (32 B each: +4 loop flag, +0x18 total length f32, +0x1c ->
    nodes 28 B each with +0x18 cumulative length f32); this+0x18/+0x1c = station vector
    (12 B entries: road, node, STATION*; STATION vtable+8 = scene number). Counts are found by
    heuristics here; the raw header is printed so the layout can be pinned offline. Needs the
    game IN an arena (the map is built per terrain)."""
    rm = m.u32(0x00c88974) or 0
    print(f'roadmap @0x00c88974 -> 0x{rm:08x}')
    if not rm:
        print('  (null - enter an arena first)'); return None
    hdr = m.read(rm, 0x40) or b''
    print('  header:', hdr.hex())
    roads_ptr = m.u32(rm + 0x10) or 0
    st_begin = m.u32(rm + 0x18) or 0
    st_end = m.u32(rm + 0x1c) or 0
    print(f'  roads @0x{roads_ptr:08x}  stations 0x{st_begin:08x}..0x{st_end:08x} ({(st_end - st_begin) // 12 if st_end >= st_begin else "?"} entries)')
    roads = []
    for i in range(256):
        r = roads_ptr + i * 32
        rec = m.read(r, 32)
        if not rec:
            break
        length = struct.unpack_from('<f', rec, 0x18)[0]
        nodes_ptr = struct.unpack_from('<I', rec, 0x1c)[0]
        if not (0 < length < 1e6) or nodes_ptr < 0x10000 or nodes_ptr > 0x7fffffff:
            break
        nodes = []
        prev = -1.0
        for j in range(20000):
            nb = m.read(nodes_ptr + j * 28, 28)
            if not nb:
                break
            cum = struct.unpack_from('<f', nb, 0x18)[0]
            if j > 0 and (cum < prev or cum > length + 1.0 or cum != cum):
                break
            prev = cum
            nodes.append([round(v, 3) for v in struct.unpack_from('<6f', nb, 0)] + [round(cum, 3)])
        roads.append({'index': i, 'raw': rec.hex(), 'loop': rec[4], 'length': round(length, 2),
                      'nodes_ptr': hex(nodes_ptr), 'nodes': nodes})
        print(f'  road {i}: len {length:.1f} m, {len(nodes)} node(s), loop={rec[4]}, raw {rec.hex()}')
    stations = []
    if 0 < st_begin <= st_end and st_end - st_begin < 12 * 4096:
        sb = m.read(st_begin, st_end - st_begin) or b''
        for k in range(len(sb) // 12):
            road, node, sp = struct.unpack_from('<III', sb, k * 12)
            srec = m.read(sp, 0x40).hex() if sp else ''
            stations.append({'road': road, 'node': node, 'station_ptr': hex(sp), 'station_raw': srec})
        print(f'  {len(stations)} station(s): ' + ' '.join(f'r{s["road"]}n{s["node"]}' for s in stations[:40]))
    out = {'roadmap_ptr': hex(rm), 'header_hex': hdr.hex(), 'roads': roads, 'stations': stations}
    open(os.path.join(MAPDATA, 'roadmap.json'), 'w').write(json.dumps(out))
    print('  -> mapdata\\roadmap.json')
    return {'roads': len(roads), 'stations': len(stations)}


def dump_wagon_classes(m):
    """v8: wagon/loco class list @0xcab624 (vaninfo.cpp FUN_00694740): node+0x14 -> info,
    info+0x14 = class id; class base = node-0x24 (like the tanks)."""
    head = m.u32(0x00cab624) or 0
    print(f'wagon class list head @0x00cab624 = 0x{head:08x}')
    out = []
    node, n, seen = head, 0, set()
    while node and node not in seen and n < 64:
        seen.add(node); n += 1
        info = m.u32(node + 0x14) or 0
        cid = m.u32(info + 0x14) if info else None
        s1, s2 = (m.u32(info + 4), m.u32(info + 8)) if info else (None, None)
        blob = m.read(info, 0x80) if info else b''
        out.append({'node': hex(node), 'info': hex(info), 'class_id': cid, 'name_str_ids': [s1, s2],
                    'info_head_hex': blob.hex() if blob else ''})
        print(f'  [{n:2d}] node=0x{node:08x} info=0x{info:08x} class_id={cid} name_str_ids={s1},{s2}')
        node = m.u32(node + 4) or 0
    return out


def main():
    procs = [(pid, nm) for pid, nm in find_processes() if nm.lower() in {x.lower() for x in FA_NAMES}]
    if not procs:
        print('FA.exe not running'); return 2
    pid = procs[0][0]
    m = Mem(pid)
    try:
        res = {'create_header_table': dump_create_table(m), 'tank_classes': dump_tank_classes(m),
               'float_consts': dump_float_consts(m), 'soldier_classes': dump_soldier_classes(m),
               'car_classes': dump_car_classes(m),
               'film_table': dump_film_table(m), 'film_sizes': dump_film_sizes(m),
               'wagon_classes': dump_wagon_classes(m), 'roadmap': dump_roadmap(m)}
    finally:
        m.close()
    path = os.path.join(MAPDATA, 'tank_tables.json')
    json.dump(res, open(path, 'w'), indent=1)
    print(f'-> {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
