# Adding a map (terrain) to the server - the data pipeline (v958f5g)

A dogfight arena on any terrain the client ships needs NOTHING from this list: set the arena's
terrain on the web and go. The files below are only for Territorial Combat / economy / tanks /
trains on that terrain. Every dumper is READ-ONLY on the game (ReadProcessMemory); nothing in the
client is modified. Run them from `C:\games\FA Server` in an Administrator prompt while FA.exe
runs OFFLINE with an arena on the NEW terrain fully loaded (in the world, not the HQ screen -
the tables exist only once the terrain is loaded). NN below = the terrain number, two digits.

| Step | Run | Produces (mapdata\) | Needed for |
| --- | --- | --- | --- |
| 1 | `python fa_dump_trn_tables.py` | `trn_tables_trnNN.json` (terrain number read from the game) | scenes, objects -> scene mapping, scene ownership (v958f5g seeds it from here), names; the base for step 3 |
| 2 | `python fa_memdump.py --dump --out mapdata\fa_memdump_trnNN.json` | production defs + the client's own per-camp totals | step 3 |
| 3 | `python fa_build_scene_profiles.py --trn NN --memdump mapdata\fa_memdump_trnNN.json` | `fa_scene_profiles_trnNN.json` | per-scene supply storage / production (without it the generic profiles from fa_scenes.json are used, or blind grants) |
| 4 | `python fa_dump_tank_tables.py` | `roadmap.json` (+ `tank_tables.json`, global) | step 5 |
| 5 | `python fa_make_rails.py --trn NN [--station-radius 2000]` | `rails_trnNN.json` | trains (no file = no trains on that terrain); the radius is how far a scene may sit from the rails to be a station (default 900 m - check the `TRAIN terrain NN: ... station(s)` log line and raise it when depots are missed) |

Steps 1 and 3 read and write `mapdata\` themselves (the server reads mapdata first and falls back to
the server directory). Step 4's `roadmap.json` is overwritten per
terrain, so run step 5 right after it. `tank_tables.json` and `weapon_map.json` are not per
terrain.

Then:
- `TERRAIN_NAMES` in server.py: add the number -> name if it is missing (names only).
- Restart the server and look for `SCENE42 terrain NN (...): scene ownership seeded from
  trn_tables_trnNN.json` and `SUPPLY terrain NN: per-scene profiles loaded` in the log.
- Create the arena on the web with that terrain, enter it, `tc status` lists the scenes.

Mediterrain (02) is the fully dumped reference; English Channel (06) has steps 1-3; Circle (05) step 1.
