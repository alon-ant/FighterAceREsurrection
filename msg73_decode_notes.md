# msg-73 (0x49) SendRepairInfo - decode notes (started 2026-08-12, v428f5 era)

Client -> server, 39-byte body (43 with VNET header), builder FUN_004c8690, sent after every
msg-60 grant that takes the bit0==0 or bit0-resource path (the 0x07 vfunc20(1) shortcut SKIPS
it; 0x06 sends it - one reason TC rich tier uses 0x06).

## Layout (confirmed so far)

Raw capture shape (SUPPLY-CAP): 02 72 00 00 49 SS | BODY(37)
  SS       = increments per resupply within a session (00,00,03 observed) - resupply counter?
  BODY[0]  = 0x01 always so far - subrecord count? version?
  BODY[1:3]  u16 LE - 0 in parked samples; 0x0a3c=2620 twice in one Korea sample - UNKNOWN
  BODY[3:5]  u16 LE - same value repeated in that sample - UNKNOWN (drawn amounts? pre-state?)
  BODY[5:7]  u16 LE - 0 in all samples so far
  BODY[7:9]  u16 LE - CURRENT FUEL, lb        << CONFIRMED by anchors below
  BODY[9:11] u16 LE - CURRENT AMMO WEIGHT, lb << CONFIRMED (incl. ordnance: bomber showed 13000)
  BODY[11:]  remaining ~26 bytes: contain 0x00008000-pattern u32 words that line up with the
             gun/rack state masks the msg-60 handler tests (+0xaf0/+0xaf4/+0xaf8/+0xafc/+0xb00/
             +0xb04) - station status words, likely which racks/guns are empty. UNMAPPED.

## Calibration anchors (server.log 2026-08-11, room 49 Korea unless noted)

  07:07:44 after console `resupply 0x01 0 0` (FULL DRAIN)  -> fuel=0     ammo=0     (all-zero)
  07:04:43 after auto grant 0x01 3000/1000                 -> fuel=5560  ammo=3390
  07:05:19 after console 0x02 100 100 (fuel->HQ loadout)   -> fuel=2840  ammo=3390
           (fuel snapped 5560 -> 2840 = the HQ-selected loadout in lb; ammo already max)
  07:06:49 after console 0x03 50 1000 (bit1 wins fuel)     -> fuel=2840  ammo=3390
  06:47:46 (bomber?) after 0x01 3000/1000: fuel=5840 ammo=13000, BODY[1:5]=2620,2620 - the only
           sample with BODY[1:5] nonzero; meaning unknown.
  06:22:12 terrain-2 session: fuel=1480 ammo=6360 AFTER amt2=0 grant - ammo NOT zero, which
           contradicts the drain probe; maybe the reply predates part of the rearm on that
           build/plane, or ordnance weight survives the gun wipe. RE-CHECK with a controlled
           probe.

## Next controlled-probe protocol (one parked plane, note gauge state before each)

  PROBED 2026-08-11 (messages38.log): incremental amounts CONFIRMED in kg - `0x40 10 0` adds
  22lb fuel, `0x40 22 0` adds 49lb (kg * 2.2046); ammo adds display as % of the plane's total
  (10kg = 4%, 20kg = 8% on the test fighter -> total ammo weight ~250kg). `0x40 0 0` performs
  nothing but shows 'No additional fuel/ammunition available' (0xa3/0xa4) - AND STILL SENDS
  out 73'39. The report fires on EVERY in 60'8 in the bit0==0 path, no-ops included.

  => STATE QUERY: flags 0x30 (bit4|bit5) with any amounts should be fully SILENT - in the
  incremental path the suppress bits short-circuit the && so FUN_004ebf50/FUN_004ecad0 are
  never called (no add, no message), while FUN_004c8690 still fires. PROBE `resupply 0x30 0 0`
  to confirm: expect zero on-screen messages + an out 73'39 with the plane's current state.
  Once confirmed, the server can poll parked planes for exact fuel/ammo before TC grants.

  OPEN: our server ECHOES msg 73 back to the sender (`in 73'39` 5-30ms after every out,
  messages37/38.log) - find the reflection path (generic relay? ack machinery?) and squelch;
  an unsolicited msg-73 at the client is undefined behaviour.

  1. note fuel% + ammo state -> `resupply 0x40 0 0` (pure no-op incremental, forces a report
     with NO state change) -> read BODY[7:9]/[9:11] = exact current state. This makes 0x40 0 0
     a free STATE QUERY - potentially the biggest win: the server can poll a parked plane's
     real fuel/ammo before deciding a TC grant, making debits exact.
  2. burn a known amount (taxi 1 min), 0x40 0 0 again -> BODY[1:5] behaviour on no-op.
  3. fire N rounds of one gun only, 0x40 0 0 -> which tail word changes = station map.
  4. drop one bomb, 0x40 0 0 -> rack word.

## Server plumbing status

  SUPPLY-CAP already logs every 0x49 (plain, counter-wrapped, and PFX framings all captured).
  Not yet parsed/stored per-session. When the layout is pinned: parse into s.last_repair_info,
  use as pre-grant state for exact TC debits (fuel_needed = loadout - current, etc.).
