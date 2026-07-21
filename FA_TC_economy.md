# Fighter Ace — TC (Territorial Conquest) production, supply & damage model

Sources, in order of authority:
1. FA.exe static analysis (base 0x400000, no ASLR) — `WORK3/Production.cpp/.hpp`
2. ACWIKI `TC_Production_and_Supply` page (2006, Shad@HQ)
3. Game manual p.7, p.74, p.77 (scene data readouts)
4. 2009 live-server session log `messages04.log` (wire ground truth)

---

## 1. The core model

Production is **per-building**, aggregated **per-camp**. Three building types, three
resources, two unit types.

| Building type      | PMT enum                | Role |
|--------------------|-------------------------|------|
| Resource Producer  | `PMT_RESOURCE_PRODUCER` | makes Metal / Fuel / Ammo each step |
| Resource Storage   | `PMT_RESOURCE_STORAGE`  | holds overflow, capped |
| Unit Producer      | `PMT_UNIT_PRODUCER`     | consumes Metal -> Tank/Plane *units*; draws Fuel+Ammo to equip |

Resources: **Metal, Fuel, Ammo**. Units: **Tank, Plane, Ship**.
A "unit" is a built-but-not-yet-deployed tank/plane. Deploying it consumes Fuel+Ammo.

### Production step = once per minute

The wiki states the step is 1/minute. **Confirmed on the wire**: `messages04.log` shows
`in 40'38` (msg 40, fixed 38 bytes, host-gated handler `0x4f6ab0`) arriving at a rock-steady
~60 s cadence, 184 times across the session:

```
01:33:54.770  01:34:54.755  01:35:55.083  01:36:56.114  01:37:54.442  01:38:54.958 ...
```

=> **msg 40 is the per-minute production-step broadcast.** This closes the "msg 40 layout TBD"
item from FA_groundwar_protocol.md.

Step order (per wiki):
1. Resources produced
2. Resources stored
3. Units produced from resources (Metal)
4. Units stored
5. Tanks/planes/ships produced from units
6. Those are supplied with Fuel + Ammo

---

## 2. Damage -> production is BINARY per building, not a scalar efficiency

This was the open question. The binary settles it.

Each production building has a **`Works()`** boolean. There is no per-building continuous
efficiency multiplier. `FUN_00588850` is the "producer died" path:

```c
void FUN_00588850(int *param_1)
{
  (&DAT_00c87c60)[*(int*)param_1[7] + param_1[6]*8] -= param_1[8];  // subtract its rate
  param_1[8] = 0;                                                    // contribution zeroed
  if (*(int*)param_1[7] == 0) {
    FUN_007cb090("pp destroyed, but working\n");
    param_1[2] = 1;                       // mark not-working
    (**(code**)(*param_1 + 0xc))();
  }
  param_1[9] = 0;
}
```

So: **destroying a producer subtracts exactly its rate from the camp production total.**
The "production efficiency %" the manual shows on the Single Scene Data panel is therefore
an *emergent ratio* — (sum of rates of still-alive producers) / (sum of all rates) — not a
stored field. That is very good news: we do not need a damage curve, only per-building alive/dead.

### The two global aggregate arrays

`RESOURCE_STORAGE_BASE::Add` (`FUN_00565dc0`) reveals the object layout and the accumulators:

| offset | meaning |
|--------|---------|
| `+0x08` | `Works()` flag (0 = dead; adding to a dead store logs `fixit: add - not works`) |
| `+0x18` | camp / owner index |
| `+0x1c` | current stored Value |
| `+0x20` | -> Def; `Def+0` = ResourceType, `Def+4` = MaxStorageValue |

```c
(&DAT_00c87d60)[Def->ResourceType + campIdx*8] += amount;   // aggregate STORED
(&DAT_00c87c60)[         resType  + campIdx*8] -= rate;     // aggregate RATE (on death)
```

Stride is **8 resource slots per camp** — matches the assert `nResourcesUsed()<=8`.
Hard invariant: `Value <= Def->MaxStorageValue` (assert `Value<=Def->MaxStorageValue`).
Overflow beyond capacity is **discarded**, matching the wiki ("any new resources simply vanish").

### Buildings repair

Buildings are **not permanently dead** — the arena config exposes `BuildingsRepairRate` and
`RepairTime`, and FA.exe warns `Object %i %s (%s) has Life=%i but doesn't have Repair`.
So a bombed producer comes back online after repair, restoring its rate to the camp total.

---

## 3. Does an airfield produce its own supplies?

**It depends entirely on the scene profile.** From the extracted profile table
(`fa_scenes.json` -> `profiles`), airfields split cleanly into two classes:

| Profile | metal/min | fuel/min | ammo/min | metalCap | fuelCap | ammoCap | Self-producing? |
|---|---|---|---|---|---|---|---|
| Tank Factory          | 2000 | 1000 | 5500 | 19000 | 30000 | 50000 | YES |
| **Front Line Airfield** | 1000 | 1000 | 4580 | 66000 | 36000 | 60000 | **YES** |
| Port                  | 1000 | 1000 | 4500 |  5000 | 30000 | 55000 | YES |
| Tank Factory 1 / 2    | 1000 | 1000 | 4500 |  9000 | 33000 | 45000 | YES |
| **Tower Airfield**    | 1000 | 1000 | 4500 | 11000 | 33000 | 50000 | **YES** |
| Support Factory 1 / 2 | 1000 | 1000 | 4500 |  7500 | 30000 | 45000 | YES |
| Village               |    0 |    0 | 4500 |     0 |     0 | 55000 | YES (ammo only) |
| Support Factory       | 1000 | 1000 |    0 |  5000 | 30000 |     0 | YES |
| Large Tank Factory 1/2| 1000 | 1000 |    0 | 12000 | 30000 |     0 | YES |
| Metal Factory         | 1000 | 1000 |    0 | 12000 | 30000 |     0 | YES |
| Fuel Factory          |    0 | 1000 |    0 |     0 | 30000 | 10000 | YES |
| **Front Airfield**    |   25 |    0 |    0 |  9000 |  4500 | 10000 | **trace metal only** |
| **Airfield**          |    0 |    0 |    0 |  9000 |  4500 | 10000 | **NO — storage only** |
| **Bomber Airfield**   |    0 |    0 |    0 |  9000 |  4500 | 10000 | **NO — storage only** |
| **Grass Airfield**    |    0 |    0 |    0 |  9000 |  4500 | 10000 | **NO — storage only** |
| FAB                   |    0 |    0 |    0 |  2000 |  3000 | 20000 | NO — storage only |
| Substation 1          |    0 |    0 |    0 |  3000 |     0 |     0 | NO — storage only |

**Answer:** plain `Airfield`, `Bomber Airfield`, `Grass Airfield` and `FAB` produce **nothing**.
They are pure storage and must be fed from elsewhere. `Front Line Airfield` and `Tower Airfield`
are full producers and are self-sufficient.

---

## 4. Supply radius — why "no supply trains" is mostly harmless

Manual p.77: *a scene can instantly draw and provide supplies to/from any other scene within
its supply radius.* This is automatic and free — no train required.

Radius is a per-scene-def field (`link` in `data00_scenes.json`) **and** is overridable per
arena by GAME_DEF:

```
ResourceProducerLinkRadius   PlaneProducerLinkRadius
TankProducerLinkRadius       ShipProducerLinkRadius
SupplyResourceRadius         ParachuteResourceRadius
```

Observed `link` values across 1120 scene defs:
`10000 (738x), 30000 (280x), 40000 (37x), 20000 (30x), 60000 (30x), 35000 (4x), 15000 (1x)`

**Trains only matter for moving supplies/tanks *beyond* the link radius**, and for AI tank
transport to distant triggers (wiki: tanks ride rails to targets, unload if the train is hit).
A storage-only airfield sitting inside a producer's radius is fed instantly. So **not running
supply trains does not starve a normal TC field** — it only bites for a field outside every
producer's radius, which then depends on **air-drop** (`DropSupply`, `ParachuteResourceRadius`).

---

## 5. Full arena-configurable economy / damage parameter set (from FA.exe settings dump)

Economy:
```
InitialStorage            FriendlyResources        UseSceneUnitProducers
SupplyResourceRadius      ParachuteResourceRadius  ResourceProducerLinkRadius
PlaneProducerLinkRadius   TankProducerLinkRadius   ShipProducerLinkRadius
GetFuelWhenLimFuel        GetAmmoWhenLimAmmo       CargoPercent   DropSupply
```
Buildings / damage:
```
BuildingsLife    BuildingsArmor   BuildingsRepairRate   BuildingsScore
BuildingDamage   FriendlyDamage   RepairTime
```
Scene triggers (the damage thresholds that drive capture):
```
AttackPercent    DefensePercent   CapturePercent
AttackToggleDelay  DefenseToggleDelay  UnderAttackToggleDelay
EnemiesForce     FriendsForce
```

`AttackPercent` / `DefensePercent` / `CapturePercent` are the **scene damage levels** that
gate triggering — i.e. "soften a scene to X% then tanks form". These are exactly the knobs
that turn our per-scene HP tracking into real TC behaviour.

---

## 6. Scene defs we have extracted

`data00_scenes.json`: **94 tables, 1120 scene defs**, fields `{i, name, h, cls, flag, link}`
grouped by terrain (`near` = terrain name: Mediterrain, Kursk, Guadalcanal, Midway,
North Cape, Western Desert, Korea, Two Islands, Pacific, NAW, Classic, Five Towers, Germany,
English Channel, Mountains, North Africa).

`h` = scene health pool. By class:

| cls | n | h min | h max | h mean | likely meaning |
|-----|---|-------|-------|--------|----------------|
| 0 | 349 | 0 | 1786 | 564 | misc / structures |
| 1 | 212 | 0 | 1632 | 850 | airfields |
| 2 | 212 | 0 | 3780 | 614 | villages |
| 3 | 282 | 0 | 1082 | 194 | factories |
| 4 |  18 | 0 |  284 | 144 | small |
| 5 |  41 | 0 |  647 | 246 | AA |
| 6 |   6 | 504 | 848 | 734 | special |

**Known gap:** only **359 / 1120** scene defs currently match a name in the `profiles` table.
Unmatched include `Figter  Airfield` (sic, 40x), `Mostiki` (20x), `Aircraft Factory` (16x),
`Planes Factory` (15x), `Substation`, `AntiAircrafts`. The profiles table needs extending
before the economy sim is complete for every map.

---

## 6b. Production def files & struct sizes (CONFIRMED from FA.exe)

`FUN_0058cb50` is `PRODUCTION::Init` (Production.cpp:0x2e2-0x2f1). It loads three
per-scene def files and asserts their lengths, which pins the struct sizes exactly:

| File | Assert | sizeof |
|------|--------|--------|
| `<scene>.prs` | `Length & 7 == 0`     | **8**  `RESOURCE_STORAGE_DEF` |
| `<scene>.prp` | `Length & 0xf == 0`   | **16** `RESOURCE_PRODUCER_DEF` |
| `<scene>.pup` | `Length % 0x18 == 0`  | **24** `UNIT_PRODUCER_DEF` |

Extensions read from `.rdata`: `0xa3b458=".prs"`, `0xa3b408=".prp"`, `0xa3b3b8=".pup"`.

`RESOURCE_STORAGE_DEF` layout **confirmed** via `RESOURCE_STORAGE_BASE::Add`:
```c
struct RESOURCE_STORAGE_DEF {   // 8 bytes
    u32 ResourceType;           // +0x00
    u32 MaxStorageValue;        // +0x04
};
```
`RESOURCE_PRODUCER_DEF` (16 B) and `UNIT_PRODUCER_DEF` (24 B) field order is **not yet
pinned** — that is what `extract_production.py` is for.

The init also confirms the aggregate array geometry: the clear loop steps `iVar7 += 0x20`
while `< 0x100`, i.e. **8 camps x 8 resources x u32** for both `DAT_00c87c60` (rate) and
`DAT_00c87d60` (stored). Globals: `DAT_00c87e6c/70/74` = RS/RP/UP data pointers,
`DAT_00c87e84` = `nResourcesUsed`.

## 7. Implementation plan for the emulator

Current state: we seed `InitialStorage` and answer msg 59->60 per spawn, but **never replenish**
— so bases monotonically drain. That is the bug this document closes.

1. **Extend the profile table** to cover the ~760 unmatched scene names (blocking).
2. **Build per-terrain scene state** at arena start: for each scene, `{profile, camp, hp,
   link, storage{metal,fuel,ammo}, units{tank,plane}, alive_producers}`, seeded from
   `InitialStorage` as a % of cap.
3. **Compute supply-radius adjacency** once per arena (O(n^2) over <=142 scenes, trivial),
   honouring the GAME_DEF radius overrides. Pool storage across each connected complex.
4. **Run the minute tick**: for each scene, add `rate * (alive_producers/total_producers)`
   per resource, clamp to cap, discard overflow. Apply `BuildingsRepairRate` to bring
   damaged producers back.
5. **Emit msg 40** on each tick, and periodic msg 42 (full snapshot) for resync.
6. **Wire damage in**: incoming msg 31 decrements scene HP; crossing `AttackPercent` /
   `CapturePercent` fires triggers; destroyed producers drop out of the alive count.
7. **Feed 59->60 from real storage** instead of a constant grant — deny/partial-fill when the
   complex is dry, which is what reproduces "Insufficient aircraft units... taking from tank
   production" seen in the 2009 log.
8. Trains: **skip for v1** (in-radius transfer is instant and covers the normal case).

## 8. On the offline training missions

Manual p.78-79 lists 11 training missions — they are flight/gunnery lessons (01 Basic Flight
... 07 Air-to-Ground Gunnery, 08 Rockets, 09 Level Bombing, 10 Dive Bombing, 11 Torpedo).
**Useful for observing PvE destroy behaviour and AA response offline**, but note: offline means
**no network, so no `messages*.log` wire capture** — they cannot yield protocol data.
For economy *numbers*, the better offline lever is a **Sample arena** on a TC map
(manual p.10: "the best way to learn the details of a game map"): mouse over each scene to read
Single Scene Data (production/min, efficiency %, storage, capacity, units) and the white
supply-radius circles/links directly from the UI.
