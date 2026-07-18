#!/usr/bin/env python3
r"""
Fighter Ace LAN Server v279
===========================
v279: AUTO-RESUPPLY SPAWN GRACE - stop corrupting a plane that is still being built. With v278's
      targeting the air-resupply and instability are gone, but resupplying right after a respawn
      (no flight first) desynced the plane. Firestorm's client log (messages51) shows:
        05.50.26.677  Create NetPlane (F4U-1a). St=0, ONumber=258
        05.50.26.681  Repair PlnID:5; 0, Firestorm Full=1, Load:0      <- our msg-60, 4ms later
        05.50.26.681  ERROR: IPC net PlnID:5; Cur:0, New:0, Net:1
      ...and that error then repeats every ~200ms for 8.5 MINUTES (2239 times) - the local loadout
      state (Cur/New=0) never reconciles with the network state (Net=1). The grant landed while the
      client was still constructing the plane object, leaving it permanently inconsistent.
      v279 records s.spawn_time on every ServerConfirm and refuses to auto-grant until
      AUTO_RESUPPLY_SPAWN_GRACE (10s) has passed, so a freshly spawned plane is fully built before
      it can be repaired. Runway-damage repair still works - it just waits out the grace window
      (~12s from spawn) instead of firing into the middle of object creation. BLIND (TC gate = P2b).
v278: AUTO-RESUPPLY targeted + one-shot (fixed air-resupply/freeze/instability with peers).
v277: AUTO-RESUPPLY freshness guards (staleness must never look like stillness).
v276: AUTO-RESUPPLY base change treated as an HQ entry/respawn (clean per-base settle).
v275: AUTO-RESUPPLY WORKING - at_airfield scan-framing fix (the bug that broke all prior versions).
v274: AUTO-RESUPPLY position-static gate (correct, but at_airfield never set due to scan framing).
v273: AUTO-RESUPPLY via telemetry-absence (FAILED - type-7 keeps flowing when parked).
v272: AUTO-RESUPPLY via plane_movement (FAILED - type-7 stops when idle, no position data parked).
v271: AUTO-RESUPPLY proxy-event trigger (missed no-move-from-spawn; fired on touchdown roll).
v270: AUTO-RESUPPLY engine-off trigger (only fired at spawn - client sends 5300 once).
v269: AUTO-RESUPPLY over-tightened to post-flight only (WRONG - reverted).
v268: AUTO-RESUPPLY settle-timer (worked but fired pre-takeoff at full loadout = no-op).
v267: AUTO-RESUPPLY (P2a) - engine-edge trigger (FAILED - states arrive out of order).
v266: msg-60 SUPPLY GRANT sender = the in-world REARM/REFUEL trigger (CONFIRMED WORKING).
v265: `resupply` console command (msg-36 test lever - ruled out, msg-36 is destroy/capture).
v264: SUPPLY capture widened (v263 watched the wrong sub numbers). The 2009 '59/60/40/73' are
      CONDUCTOR (in-game world) channel numbers; on our reliable channel the spawn/land messages
      show as different subs (seen: type=0x12 sub=0x60 sz=5 right after StartPlace/ServerConfirm;
      a PREFIXED sub=0x40 we currently ignore). v264 logs EVERY reliable-channel message while the
      pilot is in-arena and decodes the prefixed inner sub (pl[8]), so the real supply/repair flow
      is visible instead of guessed. Still capture-only, no behaviour change.
v263: SUPPLY/REPAIR capture instrumentation (Phase 2 start - resupply/repair on landing).
      Adds _supply_msg_instrument to log the FULL bytes of inbound supply/repair messages
      (msg 59/60/40/73 = 0x3b/0x3c/0x28/0x49) so their formats can be reversed from real captures.
      2009 flow (messages04.log): InsertPlayer(OnGround) -> client out-59 (supply/startplace request)
      -> server in-60 (grant) -> Repair PlnID:.. Full=1/0 (server-driven rearm via msg 40/73). As the
      server we receive 0x3b and must reply 0x3c then send 40/73 to rearm. No behaviour change yet -
      capture first, build the grant/repair replies from ground truth next (replay, don't author).
      Gated by SUPPLY_MSG_INSTRUMENT.
v262: BAIL CHUTE = NAMED FREEFALL (revert byte9 to 0). The stock parachuter ctor FUN_004a8c20 copies
      the pilot NAME into the tag (+0x154) ONLY on the byte9==0 branch; byte9>=1 (deploy) writes a
      numeric code instead - so a deployed chute structurally cannot carry the pilot name via create.
      Since the real game named EVERY chute (user spec) and a 2009 SPECTATOR saw a bail as freefall
      (the canopy deploy was owner-local), byte9=0 is the authentic, named bail: the pilot floats down
      with their name+rank tag. The v261 [2:4] owner fix is kept (PARA_FIX_OWNER_REF) so the name
      binds correctly. Trade: the remote won't see the canopy visibly OPEN (deploy is owner-local),
      but a NAMED falling pilot matches the real spectator view. The "deployed AND named" case (needed
      for TC cargo paratroopers, which are always deployed yet named) is separate work: those get their
      name from the REMOTE_PLAYER bind path, not the ctor strcpy - to be built with the TC cargo drop.
v261: PARACHUTER NAME TAG fix (deployed chute now shows the pilot name).
      The deployed chute (v259 byte9=1) rendered but had NO name tag, unlike the old freefall chute.
      RE of the master object factory FUN_004f26b0 (VNet.cpp) case 2 showed the name comes from a
      BIND: it resolves record body[2:4] as an object number (FUN_004f2530 -> objtable[n]) to the
      owner's GamerClientScore, then FUN_00427530 binds it to chute+0x128 = the name tag. The ctor's
      strcpy fallback only fills the name for byte9==0 (freefall); byte9>=1 relies entirely on the
      bind. Our record copied the bailing CLIENT's out-4 body verbatim, whose [2:4] holds that
      client's LOCAL plane number - which does NOT match the peer-visible number the server assigned
      the plane (log proof: [2:4]=0x0101=257 was BIGALON's own plane, not Test2's plane 256) -> the
      peer's lookup missed -> no name. Fix (PARA_FIX_OWNER_REF): overwrite body[2:4] with the
      peer-visible plane number src.my_obj_number so the bind resolves and the pilot name renders.
      Matches the real game: every canopy (pilot/paratrooper/cargo) is named, killable, collidable.
v260: ARENA ISOLATION fixes (cross-arena leakage) + no-team roster fix.
      BUG B (real): after an arena SWITCH, current_room went stale so chat, telemetry and roster
      kept scoping to the OLD arena -> peers in different arenas saw each other's chat, saw each
      other in the 3D world, and a switched player still showed in the old arena's roster. Root:
        (1) handle_leave_arena cleared entered_game but NEVER current_room; and
        (2) the enter handler (sub=0xc8) only resolved a room 'if not current_room', so a switch
            left current_room pointing at the old room.
      Fix: handle_leave_arena now sets current_room=None; the enter handler ALWAYS resolves the
      GameIndex->room and, if it differs from the current room, leaves the old arena cleanly
      (player-leave + object-delete + db_room_leave) before switching. All broadcast paths already
      scoped to get_sessions_in_room(current_room), so correct current_room = correct isolation.
      BUG A (cosmetic): a player who hadn't picked a side showed under US in peers' rosters. Root:
      build_add_player_62 encoded a None camp as 0 (=US). Fix (ADD_PLAYER_NOTEAM_NEUTRAL): encode
      as 0xff so the handler maps it to camp=-1 (no side / In Menu) - the same encoding the client
      gives its own local entry at grant. msg 63 still sets the real side on team-select.
v259: ★ PARACHUTER DEPLOY located and made testable (create-time, one byte). ★
      Deep RE this session found the master object factory FUN_004f26b0 (VNet.cpp). Its parachuter
      case (type 2) calls the ctor as:
          FUN_004a8c20( body[8], owner, *(body+4), (body[0]&0x70)>>4, body[9] )
      so record body BYTE[9] = ctor param_6 = the DEPLOY / model selector:
          0   = ParaTrooper, FREEFALL, no canopy  (the value the client's own out-4 body carries)
          1   = ParaTrooper, canopy DEPLOYED  (net-create branch calls FUN_004a6780 -> 0x324=1)
          >=2 = ParaCargo model, N troops, deployed
      The deploy is a CREATE-TIME property, NOT a per-object update message: a parachuter IGNORES
      both msg-7 (coord applier FUN_007e3a70, its vtable[+4] just returns size) and msg-12 (state
      applier, its vtable[+0x14] is a stub). Proven by the 2009 spectator log: a remote parachuter
      created ONCE, never updated, still deploys - so the deploy must be baked at create.
      v259 adds PARA_DEPLOY_BYTE9 (default 1) to set body[9] in build_parachuter_record. Set 1 to
      test whether the peer renders an OPEN canopy; None to keep the client's freefall value.
      NOTE: for a fresh BAIL the chute should freefall first (byte9=0) then deploy on pilot input;
      byte9=1 forces instant canopy. For the TC CARGO paratrooper drop, instant-deploy is CORRECT.
v258: INSTRUMENTATION to find the parachuter descent + deploy mechanism (no behaviour change).
      Established this session (dual-log analysis, Bigalon messages21 + Test2 server run):
        * After bail, Test2 sends the server ONLY a byte-identical 36-byte keepalive - NOTHING about
          the deploy, and it does NOT change when the chute deploys. Bigalon receives ZERO telemetry
          for the plane OR chute during the whole descent. So the deploy is NOT a relayable client
          message - the bailing client goes silent and the SERVER is authoritative for the pilotless
          plane and the parachuter (confirmed by 2009: a spectator client sees other players' chutes
          descend + delete cleanly, only possible if the server drives them).
        * 'in 20' hypothesis (a poll?) TESTED and REJECTED: 1820 'in 20' vs only 8 'out 20' (227:1),
          variable 13-129 byte payloads -> it's a SERVER->CLIENT state BROADCAST, not a poll, and its
          'out 20' replies cluster around players ENTERING/JOINING -> msg 20 is ROSTER sync, probably
          not the parachuter mechanism.
        * During 2009 parachuter 975's descent the non-roster messages were 'in 30'5' (tiny, right
          after create and again seconds later - the strongest per-object STATE/deploy candidate),
          plus 'in 72'/'in 73'.
      v258 logs the FULL bytes of msg 20 (MSG20 channel) and, while a parachuter is alive, every
      watched in-game type 30/72/73/20/31/40 (PARAWATCH channel) with object-number hit detection.
      Gated by MSG20_INSTRUMENT. Next test: bail + deploy the chute; the PARAWATCH lines will show
      which message carries the deploy so we can drive it server-side.
v257: TWO parachuter fixes, both from the v256 client log (messages20).
      (1) *** THE v256 SERVER DELETE WAS DOUBLE-WRAPPED. *** _para_land sent
          send_rel(peer, build_msg13(build_delete_object_3(...))) but build_delete_object_3 ALREADY
          returns build_msg13(body). So the wire carried msg13(msg13(delete)); the client parsed the
          inner as 'in 0'18' -> "ERROR: Unsupported message 0" -> the delete FAILED, and both the
          plane (257) and the chute (258) went stale and were culled (bsr=0, dif~25000) instead of a
          clean server delete (bsr=1). Now sends build_delete_object_3(...) directly (single wrap).
      (2) SCORE PRIME. The chute-OPEN (canopy deploy) is NOT a network message - 2009 shows a
          receiving client gets the create then nothing until the delete, and the canopy deploys via
          the ParaTrooper's LOCAL physics (update FUN_004a6780 branches on the object's +0x2dc: <1 =
          trooper free-fall, >=1 = canopy open). On the OWNER (Test2) it deploys; on the REMOTE
          (Bigalon) the trooper falls but the canopy doesn't open. The one wire difference we can see:
          2009 object-only parachuter creates are PRECEDED by 'in 25'46' score blocks; ours are bare.
          So v257 sends the peer a msg-25 for the bailing pilot right before the create (PARA_PRIME
          _SCORE, send_stat_block_25 now takes dst=). If the deploy binds to the score/identity, this
          fixes it; if not, the next client log will show the canopy still falling without opening,
          and we RE the exact +0x2dc setter.
v256: THE REAL PARACHUTER LIFECYCLE - from the 2009 ground truth. This is a TC gameplay mechanic
      (paratroopers dropped from cargo planes must descend and land), not cosmetic.
      WHAT THE 2009 LOG PROVES about a real parachuter:
        * Created object-only ('in 2'24'), model loads (ParaTrooperlod0.Q6).
        * NO network telemetry EVER names the object again. The client FREE-FALLS the canopy locally
          from the create-time seeded position (the ctor FUN_004a8c20 copies the owner plane's
          position + a fall rate).
        * The 'out 6'3' the client emits after the create is FIRE-AND-FORGET - 2009 never answers it
          (zero 'in 6'), so it was never the render blocker (v254's msg-6 theory was wrong).
        * The server ends the canopy with a type-3 "Server require delete object N" 5-21s later,
          scaling with bail ALTITUDE. The client then removes it cleanly (DelObject, bsr=1).
      WHAT WE WERE DOING WRONG (v254/v255): sending cloned plane telemetry. v255's instrumentation
      proved the packets arrived at the client, but it can't map a type-7 plane packet to a type-2
      parachuter object - it logged "Get coord for missing object 0" and ignored them, and then
      CULLED the canopy as stale (bsr=0) at ~28s because we never sent the real delete.
      v256 FIX:
        * SEND_PARACHUTER_TELEM = False - no telemetry (wrong mechanism, actively harmful).
        * PARA_SERVER_DELETE - after PARA_DESCENT_SECONDS the server sends the type-3 delete to peers,
          exactly like 2009. This gives the canopy the proper lifecycle and stops the stale-cull.
      The canopy is created + seeded + free-falls locally + landed by the server. If the 3D render is
      still missing after this, the next lead is the score/identity binding: 2009 object-only
      parachuter creates are preceded by 'in 25' score blocks that prime GamerClientScore[St]; ours
      sends St with no accompanying 25. That is the next thing to add if needed.
v255: INSTRUMENT the parachuter telemetry send. v254's clones were logged as "sent" but Bigalon's
      client received ZERO of them (messages18: no 'in 7'/'in 8' after the bail, received bytes drop
      to 0). The v254 log line printed whether or not a peer was actually found, so "8 sent" proved
      only that the function RAN 8 times - not that any packet left the socket. v255 logs the real
      per-peer sendto (byte count, destination addr, first bytes) and counts actual sends, so the
      next test shows definitively whether the packets leave and where they go.
      CONTEXT (confirmed this session): after Test2 bails he transmits only a static keepalive, so the
      normal relay has nothing to forward and Bigalon goes silent ("received bytes -> 0") - that part
      is expected. The parachuter clones were meant to fill that gap; they aren't arriving, and v255
      is about finding out why (send path vs client rejection) with evidence instead of inference.
v254: THE PARACHUTE BUG IS A SWALLOWED COORDINATE REQUEST - not the record. And the fix REPLAYS a
      real packet instead of authoring one.
      RE (this session) established the whole chain:
        * msg 6 = the client's "send me coordinates for object N" request:
              [bc=0][T=0x32][00][00][sub=0x06][ONumber LE]
          The client emits it right after creating ANY net object (planes too).
        * For a PLANE, coords arrive via normal telemetry relay -> positioned -> request satisfied.
        * For the PARACHUTER, the client asks for object 258's coords, but 258 has no telemetry (the
          bailing client sends only a static keepalive), AND our server SWALLOWS all msg 6. So the
          request is never answered -> 'in 6' -> "Unsupported message 6" -> the canopy sits at
          "Get coord for missing object 258", visible on radar but never rendered in 3D.
        * The create RECORD was never the bug (v250/v251 fixed bytes that were already fine): the
          create succeeds and the ctor FUN_004a8c20 even seeds the parachuter with the plane's
          position when linked. It just never gets ONGOING coords.
      THE FIX (v254): after creating the canopy on peers, answer the coord request by giving object
      258 a telemetry stream - by CLONING the plane's last real type-7 packet and retargeting only
      the ONumber (bytes 7:9). We author NOTHING: the 88-byte telemetry position encoding is only
      partially understood (scattered smooth fields; the v243 '3x u16' was a crash-test approximation,
      not the true format), and hand-building it is exactly the guess that CTD'd us five times. A
      cloned packet is every-byte-valid because the bailing client produced it microseconds earlier.
      A short burst (PARA_TELEM_BURST) covers a dropped packet.
      RESULT: the canopy should appear at the plane's position (where the pilot jumped) and the
      "Unsupported message 6" error should stop. It does NOT self-descend yet - the altitude field
      isn't safely located, and inventing it would risk a CTD - so the canopy hovers at the jump
      point until removed. That is a real improvement on invisible, and it cannot crash.
      Gated by SEND_PARACHUTER_TELEM. If anything misbehaves, flip it off and we are back to v253
      (radar contact, no 3D, no crash).
v253: *** THE CREATE WAS NEVER THE PROBLEM. WE WERE CRASHING THE CLIENT WITH OUR OWN TICK. ***
      Bigalon's client log settles three versions of guessing:
            in 2'24
            Receive create object 258
            Create NetParachuter. St=0, ONumber=258
            <<< LOAD OBJECT (PLANES/PARA/ParaTrooperlod0.Q6) >>>
      The parachuter record PARSES PERFECTLY and the canopy IS BUILT. v251 was already correct. I
      spent v250 and v251 fixing a record that was fine, because I never once looked at what happened
      AFTER the create.
      WHAT ACTUALLY KILLS IT, from the same log:
            in 7'84   x11     <- normal telemetry, all session
            in 7'118          <- ONE packet, the instant the canopy exists
            Exception in Fighter Ace engine:  bounds error
            class ARR<class NET::OBJECT *,2048>[20983] 0..2047
      The ServerConfirm makes the bailing client start transmitting the parachuter. Its telemetry
      packet grows 84 -> 118 bytes - a MULTI-OBJECT form we have never parsed - and relay_telemetry
      blindly rewrites BYTE 5 of it with a conductor tick. The client reads that tick back as an
      object index: 20983 is TICK-sized, not object-sized, and the object array is 2048 entries.
      We crashed the peer with our own re-stamp.
      FIXES:
        1. TELEM_RESTAMP_MAX_LEN - re-stamp ONLY the form we understand (a packet naming the sender's
           own PLANE, within the size we have always seen). Everything else is relayed BYTE-FOR-BYTE.
           We do not rewrite bytes we cannot parse. That is the same discipline as v251's "copy the
           client's record, don't author it" - I applied it to the record and not to the relay.
        2. PARA_SEND_CONFIRM = False, PARA_SEND_CREATE = True. One variable at a time, given the
           record so far. The canopy is now CREATED and VISIBLE on peers but does not move (its owner
           is never told to transmit it). That cannot crash anyone, and it is a real improvement on
           invisible.
      NEXT: after a clean run, flip PARA_SEND_CONFIRM back on. The verbatim relay should now carry the
      118-byte form safely, and the canopy should actually descend.
v252: PARACHUTER OFF. Three failures means my MODEL is wrong, not just my bytes.
      v248 = wrong record size. v250 = right size, invented contents. v251 = right size, the CLIENT'S
      OWN verbatim body. Still CTD + a message-box loop. That third result is the informative one: if
      copying the client's own bytes still kills the peer, then the record contents were probably
      never the problem, and I have been fixing the wrong thing three times running.
      SEND_PARACHUTER = False. The bail now behaves exactly as it did in v247 - consumed, no confirm,
      no create: no parachute, but no crash, and kill credit still works (v247's object-keyed latch is
      untouched).
      WHAT I ACTUALLY DON'T KNOW, and should have isolated three attempts ago: we do TWO things at
      bail time, and I have never established which one the client dies on.
            1. ServerConfirm 5 for the parachuter object -> the BAILING client
            2. create-object type 2                      -> the PEERS
      New flags PARA_SEND_CONFIRM / PARA_SEND_CREATE split them, so the next test BISECTS instead of
      guessing. That is the only responsible next step, and it needs one thing I do not have: the
      CLIENT LOGS from the crash. Specifically whether the peer ever logs
            "Receive create object 258"   /   "Create NetParachuter. St=..., ONumber=258"
      If it does, the record parsed fine and the crash is downstream (the ctor, the score binding, or
      the missing telemetry for an object that exists but never moves). If it does NOT, the record is
      still being rejected in the loop and the size/shape is still wrong.
      A message-BOX loop (not a silent crash) also suggests a repeating ASSERT rather than a wild
      pointer - most likely "There is no GamerClientScore for Client=%i" (FUN_004f26b0, bit7 path),
      which would point at the tag's human-owned bit or at St - NOT at the body bytes at all. That is
      a hypothesis to TEST, not to ship.
v251: *** STOP AUTHORING THE PARACHUTER RECORD. THE CLIENT ALREADY SENDS IT. ***
      Two CTDs, both because I was inventing bytes. v250 fixed the SIZE (23 = HeaderSize 10 + 13,
      proven from the type table at 0xa30c98 and matching the 2009 wire's `in 2'24`) - but the
      CONTENTS were still my guesses, and the client died again, harder.
      THE BAILING CLIENT HANDS US THE CORRECT BODY IN ITS OWN out-4. That payload is
            [sub=4][ident u16][record BODY of HeaderSize bytes][2 trailing]
      PROOF, from our own code: for a PLANE out-4, pl[8] is the PLN_INFO id - which is exactly the
      `s.plane_type = pl[8]` this server has relied on since v201. pl[8] is body[1]. So the out-4
      body IS the object-record body, for every type.
      The real parachute body (run 083507) is:
            82 80 00 01 00 00 00 00 00 00
            [0] 0x82  tag: TYPE 2, human-owned, nation 0    <- I had 0x92 (wrong nation)
            [1] 0x80                                        <- I had 0x00
            [2:4] 256 = the PLANE's ONumber                 <- the ONE byte pair I got right
            [9] 0     model                                 <- I had 1
      Three of ten body bytes wrong. Any one could be the crash; guessing a fourth time would have
      been indefensible.
      SO: we now COPY the client's 10-byte body VERBATIM and append only the 13-byte trailer - the
      one part the server legitimately owns, because only the server knows the object number it just
      assigned (St @ [10], ONumber @ [12], rest zero).
      This is the right shape for the whole subsystem: the client authors its own object, the server
      assigns the number and relays it. Nothing is reverse-engineered that doesn't have to be.
      (The v250 hand-built builder is left in place, renamed and inert, as dead code - safe to delete.)
v250: *** THE PARACHUTER RECORD IS 23 BYTES, NOT 41. That CTD was mine. ***
      v248 built the type-2 create-object as a 41-byte PLANE-shaped record. Test2 bailed and
      AC2E_Bigalon's client died on the spot.
      GROUND TRUTH, from the 2009 session log - real parachuters on a real host:
            in 2'24                                       <- 24 bytes = 1 + a 23-BYTE record
            Receive create object 993
            Create NetParachuter. St=101, ONumber=993
      and the arithmetic holds across every variant in that log:
            plane, object-only            in 2'42   = 1 + 41
            client + plane                in 2'83   = 1 + 41 + 41
            PARACHUTER                    in 2'24   = 1 + 23
            client + PARACHUTER           in 2'65   = 1 + 41 + 23      <- pins 23 exactly
            client + plane + parachuter   in 2'106  = 1 + 41 + 41 + 23
      THE BINARY CONFIRMS IT. The msg-2 record loop (LAB_007e4e00) reads a per-TYPE HeaderSize from a
      table at 0xa30c98 and advances by HeaderSize + 13:
            mov   al, [edi]                  ; rec[0] = tag
            and   eax, 0xf                   ; TYPE = tag & 0x0f
            mov   esi, [ebx*4 + 0xa30c98]    ; HeaderSize   (ebx = TYPE*3)
            movzx eax, word ptr [esi+edi+2]  ; ONumber = *(u16*)(rec + HeaderSize + 2)
            add   esi, edi                   ; param_1 = rec + HeaderSize   (the TRAILER)
            push  edi                        ; param_2 = rec               (the BODY)
            lea   edi, [edi + ebx + 0xd]     ; ADVANCE: rec += HeaderSize + 13
      The table:  TYPE 0 (client) 35 -> 48 | TYPE 1/8 (plane) 28 -> 41 | TYPE 2 (PARACHUTER) 10 -> 23
      So sending 41 made the loop advance 18 bytes too far and parse a bogus record out of the tail -
      exactly the tag-0 bounds-crash the v187 comment warns about. It is also why "Create
      NetParachuter" never appeared in the victim's log at all: the client died in the record LOOP,
      before the type switch ever reached case 2.
      AND St/ONumber are NOT at rec[28]/rec[30] (that is the PLANE's trailer offset) - the trailer
      starts at HeaderSize, so for a parachuter they are at rec[10]/rec[12].
      TWO THEORIES I HAD, BOTH WRONG, both now ruled out:
        * message size / bc framing - the 42-byte object-only form is PROVEN fine
          (in 13'45 -> in 2'42 -> "Create NetPlane").
        * FUN_004f2530 bounds - it indexes a 2048-entry array by object number; 256/258 are in range.
      bit7 (human-owned) is KEPT SET: that is what makes the handler bind GamerClientScore[St], which
      is precisely what puts the PILOT's name and rank on the canopy instead of an aircraft tag. The
      station already exists from the plane's client record, so the 'no GamerClientScore' assert
      cannot fire.
      Still not identified (left 0, harmless): rec[1], rec[4:8], rec[8]. If the canopy renders in the
      wrong PLACE, those are the bytes to chase - the size and the tags are now settled.
v249: *** OFFICIAL SCORING. Everything before this was invented, and it was badly wrong. ***
      The user supplied the game's own published scoring page (facfs.com, revised 01/02/2001). Up to
      v248 our scoring was a flat 100 per kill, a 50-point death, and a 13-step rank ladder I made up
      with names the game has never had ('Recruit', 'Air Marshal'). All replaced with the real thing.

      RANK - nine ranks, and the page's 1-based "Rank Value" is exactly our client rank index + 1.
      Our own probes already proved that mapping: f0=5 rendered "Major" (Rank Value 6), f0=6 rendered
      "Lieut. Colonel" (Rank Value 7), rank 0 renders "Cadet" (Rank Value 1).
            idx  RankValue  Rank                   Score
             0       1      Cadet                  0 -   999
             1       2      Sergeant            1000 -  1999
             2       3      Second Lieutenant   2000 -  3999
             3       4      First Lieutenant    4000 -  5999
             4       5      Captain             6000 -  9999
             5       6      Major              10000 - 13999
             6       7      Lieutenant Colonel 14000 - 21999
             7       8      Colonel            22000 - 29999
             8       9      Brigadier General  30000 - 46000
      Our old thresholds were ~10x too generous: 3,583 points had AC2E_Bigalon wearing a Lt.Colonel's
      rank when the real ladder makes that a 2nd Lieutenant.

      AIR KILL = value of the plane you shot down + a RANK BONUS:
            (target's rank value / attacker's rank value) x 100
      So killing UP the ladder pays, and a General farming Cadets barely scores. Plane values are
      Table 1 from the page (90-195 fighters, 145-650 bombers), keyed by name against PLANE_ROSTER;
      FA4.20's later additions (jets etc.) are not in the 2001 table and are priced from their
      nearest listed variant - clearly marked, and any name that fails to resolve is logged at boot.

      LOSSES (the page's list): a plane destroyed costs its VALUE, and a dead pilot costs a further
      100. So being shot down or crashing = -(plane + 100). A BAIL-OUT costs the plane only - the
      pilot walked away. (The page counts a bail over ENEMY territory as a death; we cannot yet tell
      friendly ground from enemy, so for now every bail is treated as friendly.)

      ALSO RECORDED, not yet wired up:
        * Table 2 ground/AI values (GROUND_TARGET_VALUES), and "bombs on a MOVING ground unit score
          x4" (GROUND_BOMB_MULTIPLIER).
        * The real ASSIST rule (ASSIST_DAMAGE_FRACTION = 0.20): "the kill is awarded to the attacker
          who did the MOST damage; if another attacker did 20% or more, he is awarded an Assist."
          This is exactly what the user asked for and needs per-attacker damage accumulation from
          msg 28 - the next job.
        * The page confirms the ACE rule we already had: five kills without dying = one Ace level.
v248: *** THE PARACHUTER IS A SECOND OBJECT. Confirm it, and create it on peers. ***
      The user's hint - "after bail out the plane object and pilot object are 2 separate entities;
      the pilot object has the pilot name tag, rank etc., the aircraft has a plane type tag" - and
      the RE agrees exactly. FUN_004f26b0 case 2 is literally "Create NetParachuter":
            piVar12 = FUN_004f2530();          // record[2:4] as i16 -> the SCORE OBJECT
            obj = FUN_004a8c20(rec[8], piVar12, *(u32*)(rec+4), (rec[0]&0x70)>>4, rec[9]);
            FUN_004f1ef0(ONumber, FUN_004269a0());   // register the NAME under this ONumber
      The ctor copies the pilot's NAME out of the owner object (owner+0x154) and binds its score - so
      the parachuter's record POINTS AT THE PLANE'S OBJECT NUMBER, and that is where the name and
      rank on the tag come from. rec[9] selects the model (0/1 ParaTrooper, >1 ParaCargo).
      WE WERE DOING NEITHER HALF OF IT:
        * The parachute's msg-4 was CONSUMED WITHOUT A ServerConfirm. A client only starts
          transmitting an object once the server confirms it - so the bailing client had nothing to
          send. THAT is the "stale telemetry": a static 36-byte keepalive, byte-for-byte identical
          every 2 seconds, on a different outer header, carrying no position and no tick. It is not
          the parachute - it is a client waiting on a confirm that never came.
        * No create-object type 2 was ever sent, so peers had no object to render. "Create
          NetParachuter" appears in NEITHER client's log, ever.
      NOW: the parachute msg-4 gets a ServerConfirm, and a type-2 create-object goes out to every
      peer, bound to the pilot's plane so the tag reads the pilot's name and rank.
      *** AND THE TRAP THAT ALMOST CERTAINLY BROKE v197: the parachuter gets its OWN slot
      (s.para_obj_number). A normal spawn-confirm reassigns my_obj_number / obj_confirmed / flying;
      doing that for the parachute would make the server think the player's PLANE *is* the parachute,
      and the real plane's later delete would then land on an object nobody owns - which is exactly
      the reported v197 symptom ("Confirm object 258 not found in list, send delete" -> the FRESH
      PLANE got deleted, dead engine after respawn). The plane's slot is never touched.
      Also: the parachuter's own delete (pilot lands or is killed under the canopy) is relayed to
      peers and does NOT run the plane's death path; and the crash-detection position history now
      only tracks the PLANE's object number, so the canopy's drift can't be mistaken for a plane
      still flying.
      Gated by SEND_PARACHUTER - flip it to False to restore the old consume-and-ignore behaviour.
      HONEST CAVEAT: record fields rec[4:8] and rec[8] are passed straight to the ctor and are not
      yet identified; they are left 0. If the canopy renders in the wrong place or the wrong model,
      those are the bytes to chase.
v247: EVENT-BASED KILL ATTRIBUTION - the time windows are gone.
      The user's point, and it is the right one: a kill is credited when the plane goes DOWN, but the
      plane can take a very long time to get there. Bail out at 20,000 feet and the empty aircraft
      glides for minutes. Any time window is therefore a GUESS about how long a plane takes to fall,
      and a high-altitude kill will always be able to outlast it. v246's 180s BAIL_CREDIT_WINDOW was
      the same mistake as v244's 30s one, just larger.
      THE FIX: the attribution is a FACT, established the moment the VICTIM'S OWN CLIENT reports the
      damage (msg 28 names both the victim and the hunter). So LATCH IT AGAINST THE OBJECT and hold
      it until THAT OBJECT's delete-notify arrives. No clock anywhere.
            PENDING_KILL[ONumber] = {'killer': ONumber, 'at': ts, 'why': 'damage'|'bail'}
            set      : on every msg-28 damage report
            marked   : on the bail (parachute msg-4) - only so the log explains itself
            consumed : when the delete-notify for that object arrives (popped, so never double-counted)
            dropped  : when a new spawn reuses that object number (numbers are recycled)
      Attribution chain is now:
            1. EXACT    - the hunter named in the exit entry (long-form deaths)
            2. LATCHED  - the msg-28 damage report, held against the object. NO EXPIRY.
            3. FALLBACK - most recent shooter within KILL_CREDIT_WINDOW. This one IS a guess, so a
                          clock is appropriate; it only runs when 1 and 2 find nothing.
      BAIL_CREDIT_WINDOW is removed entirely.

      ON THE BAILED PLANE'S TELEMETRY - NOT FIXED, and it cannot be fixed by relaying: THERE IS
      NOTHING TO RELAY. After the bail, Test2's client sends only a static keepalive, byte-for-byte
      identical every 2 seconds, carrying no state at all:
            before bail:  0014 0542 05420000 07 3de8 0001 fb45...   <- real telemetry, opcode 0x07
            after  bail:  000007d10001001000000000000000000029003d  <- identical, every 2s, forever
      So the straight-line glide on the peer's screen is dead reckoning over an empty channel.
      LIKELY CAUSE (next job): a normal spawn goes out-4 -> ServerConfirm, and only THEN does the
      client start transmitting that object. We CONSUME the parachute's msg-4 and never confirm it
      ("no echo/confirm"), so the client is waiting on a confirm that never comes and transmits
      nothing - which would explain the silence AND the invisible parachute in one stroke. Not done
      here on purpose: the code comment records that a naive confirm (v197) produced
      "Confirm object 258 not found in list, send delete" and DELETED THE FRESH PLANE on respawn.
      That needs doing carefully and on its own.
v246: *** THE BAILOUT DELETE WAS BEING EATEN BY A FRAMING BUG. ***
      Test2 bailed; on his machine the empty plane flew into the ground; on Bigalon's it kept flying
      straight until it timed out; Bigalon got no kill. Run 083507, 08:47:
            08:47:24  DAMAGE28  Test2 damaged by obj 0x0101          (last_hit_by set - fine)
            08:47:34  msg-4 parachute/bail -> consumed, no echo       (the bail)
            08:47:57  [00000542|00420000] +03000150
                      PEERDEL: delete for object 0x0042 - neither its own (0x0100) nor any
                      peer's -> SWALLOW                               (<-- the plane's death, EATEN)
      (1) THE FRAMING BUG. Reliable framing is [bc][T][00][00][sub][...], but when the packet's `cmd`
          field is NON-ZERO the payload carries a 4-byte prefix - [counter u16][cmd u16 BE] - in
          front of it:
                normal  delete: [00 42 00 00 | 03 00 01 a0]
                bailout delete: [00 00 05 42 | 00 42 00 00 | 03 00 01 50]   cmd=1346
          The codebase already knew this in two places (the login reads pl[4:6]; handle_compound does
          `inner = pl[4:]`) - but handle_compound only fires for a HARD-CODED WHITELIST of three cmds
          (COMPOUND_CMDS = {530, 578, 4610}). cmd 1346 isn't on it, so the delete was parsed from the
          wrong offset: ONumber read as 0x0042 instead of 0x0100, and v235's peer-object check then
          correctly concluded it was "neither its own nor any peer's" and swallowed it.
          FIX: re-frame prefixed DELETE-NOTIFIES from offset 4.
          DELIBERATELY NOT GLOBAL: ~10% of reliable messages are prefixed and have been ignored for
          the entire life of this server (they parse to sub=0x00 and match nothing). Turning them all
          on at once is how you break a working lobby - one of them decodes to sub=0xd4 = LEAVE. Every
          other prefixed message is now LOGGED (REFRAME channel) so the rest can be done one at a
          time, on evidence.
      (2) THE CREDIT WINDOW WAS TOO SHORT ANYWAY. A bailout is a DELAYED death: the pilot jumps and
          the empty plane flies on until it hits the ground. Here the gap from the last hit to the
          delete was 33 SECONDS - already past KILL_CREDIT_WINDOW (30s) - so even a correctly-parsed
          delete would have found the attribution expired and credited nobody.
          FIX: latch the attribution AT THE MOMENT OF THE BAIL (we see it as the parachute msg-4) and
          honour it for BAIL_CREDIT_WINDOW (180s). New BAIL log channel. Cleared on every spawn.
      STILL OPEN: the parachuting pilot is not visible to peers. We consume the parachute msg-4 and
      never create the object on anyone else, so there is nothing to render. Needs a create-object
      (msg 2) with the PARACHUTER record type - noted, not yet done.
v245: *** THE IN-FLIGHT "NEW ACE" / "NEW RANK" FLASH - msg 88 was stealing its own announcement. ***
      Aces now accumulate and display correctly, but the yellow on-screen message never fired. RE
      explains it exactly.
      msg 88's handler (FUN_004f4120) is a PURE SETTER:
            found:  [eax+0x50] = byte[edi+5]   ; aces
                    [eax+0x30] = byte[edi+6]   ; rank
                    ret                        ; <- that's all. No event, no message.
      THE FLASH LIVES IN msg 25's HANDLER (FUN_004f65a0), which has TWO PATHS:
            [0xc6eb98] -> the local player's plane -> +0x128 -> their score object.
            If that score object's PlayerIndex == the packet's, jump to 0x4f6637 = the ANNOUNCING
            path; otherwise take the silent write path used for remote players.
      On the announcing path it compares the INCOMING value with what is ALREADY in the score object
      and only announces on an INCREASE:
            aces:  byte[payload+0x13] > score+0x50  -> message 0x4b, 3000ms   ("you are an Ace")
            rank:  byte[payload+0x05] > score+0x30  -> message 0x4c, 3000ms   (promotion)
            ...and only THEN writes the stat block (call 0x4f4570 at 0x4f66ca).
      (payload+5 = block[0] = f0 = rank; payload+0x13 = block[0x0e] = f8 = aces. Our own field map.)
      SO: msg 88, arriving at the OWNER, silently bumped score+0x50/+0x30 to the new value - and msg
      25 then found nothing left to announce. jle -> no flash. We were overwriting the very delta the
      client needed to see.
      FIX: send_ace_rank_88 now goes to PEERS ONLY, never to the player it is about. Peers still need
      it (they never receive a msg 25 about somebody else), and the owner's update + announcement is
      handled entirely by msg 25.
      NOTE the flash only fires while FLYING (the announcing path needs a live plane at [0xc6eb98]).
      That is exactly what was asked for - and it is also why the HQ push is harmless: at HQ there is
      no plane, so msg 25 takes the silent path, priming the score object with the true rank/aces so
      that the first in-flight push has nothing spurious to announce.
v244: *** BAILOUT KILLS - the killer got nothing. Two bugs, both fixed. ***
      Test2 bailed out under Bigalon's guns. Test2's client registered the kill in Bigalon's name and
      announced it ("AC2E_Bigalon has destroyed You"), but Bigalon got NOTHING - not in the DB, not
      on his screen. Run 075246, 08:02:11:
            exit=0x50 -> MEC&0xf=5 SE=0, tb=0x42 (SHORT form)
            -> "Test2 died (solo crash/crashland)"     ... with Bigalon 3 feet behind him.
      A BAILOUT IS A NEW EXIT FORM: MEC nibble 5 says SHOT DOWN, but ScoreEvent is 0 (not 3), which
      means a 3-BYTE entry - so unlike a normal kill (exit 0x53) it carries NO HUNTER FIELD. The wire
      never names the killer.
      BUG 1 - NO ATTRIBUTION. The victim's client knows exactly who did it (its log shows
        "HitFrom(Number=256...)"), and THAT SAME HIT PASSED THROUGH US as msg 28, whose record is
        [VictimNumber][HunterNumber][count]. We were parsing the victim and THROWING THE HUNTER AWAY.
        Now stored as last_hit_by/last_hit_at, and used as attribution step 2 (still EXACT, not a
        guess). The old "most recent shooter" fallback is now step 3 - and is no longer gated on
        `scored`, which had made it unreachable for any short-form death in the first place.
        Cleared on every spawn so a hunter from the previous life can never be credited.
      BUG 2 - THE KILLER'S CLIENT WAS NEVER TOLD. The non-scored death branch DISCARDED
        score_on_death()'s return value, so `_killer` stayed None and SEND_SCORED_DELETE_TO_KILLER
        never fired. Even with a killer correctly identified, their client would still have seen
        nothing. Now captured.
      EXIT-CODE TABLE (all observed live):
            0x53  MEC 5|SE 3   shot down by a player (long form, HUNTER present)
            0x50  MEC 5|SE 0   BAILOUT - shot down, SHORT form, NO hunter          <-- NEW
            0x2d  MEC 2|SE 13  shot down, other form
            0x63  MEC 6|SE 3   killed by AA / AI (hunter=0xffff)
            0xa0  MEC 26|SE 0  crash AND clean exit (told apart by v243's movement test)
            0x90 / 0x11        re-fly / plane-swap
v243: DEATHS BY AA/AI AND UNDAMAGED CRASHES NOW REGISTER.
      (1) *** KILLED BY AA -> "Planes Lost to AI". *** Run 230703 gave us a NEW exit code straight
          off the wire when flak got the user:
                23:26:16  exit=0x63 -> MEC&0xf=6, SE=3, hunter=0xffff (no player)
          The death itself already counted (deaths 29 -> 30, via the `scored` long-form path), but it
          was booked against "Planes Lost" (f4) - the PLAYER column. MEC nibble 6 = killed by AA / AI
          ground fire, so it belongs in "Planes Lost to AI" (f13). Added AI_KILL_MEC_NIBBLES = {6};
          db_credit_kill(lost_to_ai=) picks the column. The HQ screen shows f4 + f13, so the TOTAL
          was always right - but the breakdown is what the game actually tracks, and now it matches.
      (2) *** THE UNDAMAGED CRASH FINALLY COUNTS. *** This was the known gap from v232: a crash and a
          clean parked exit are BYTE-IDENTICAL (both MissExitCode 26 -> exit 0xa0) and neither emits
          a msg 28, so the damage rule was blind to a plane flown into the ground with no enemy fire.
          THE MISSING SIGNAL was in the telemetry all along: body[0:6] is a quantised world position
          (3x u16). From run 230703, the last 4 seconds before each removal:
                23:08:17  (4526, 64457, 3906) x8 samples, delta EXACTLY 0  -> parked on the runway
                23:21:07  deltas +551 +572 +633 +647 +712 +791 per sample  -> IN FLIGHT = THE CRASH
                23:29:08  (34787, 53731, 62007) x8 samples, delta 0        -> landed, parked
          A parked plane reports movement of EXACTLY ZERO, sample after sample; a flying one moves by
          hundreds per tick. Four orders of magnitude apart - a robust test, not a fudge.
          relay_telemetry now keeps a CRASH_MOVEMENT_WINDOW_S (3s) position history per session, and
          a removal counts as a death if the plane was DAMAGED **or** was still MOVING
          (>= CRASH_MOVEMENT_MIN). The measured movement is LOGGED on every removal, so the threshold
          can be tuned from real numbers if a slow taxi ever trips it. History is cleared on every
          spawn so the previous sortie can't leak into the next one.
v242: BOMBER SCORING + the duplicate-assist fix.
      (1) *** FIGHTER SCORE vs BOMBER SCORE. *** FA splits the scoreboard two ways, and they key off
          DIFFERENT aircraft:
              what YOU were FLYING   -> Fighter Score  vs Bomber Score   (where the points land)
              what you SHOT DOWN     -> Kills>Fighters vs Kills>Bombers  (the kill breakdown)
          We were dumping everything into Fighter Score and kills_fighters, so a Lancaster sortie
          scored as a fighter. The server already knew the aircraft - s.plane_type is the
          PLANE_ROSTER id straight out of the spawn packet (out-4 byte[8]) - it just wasn't used.
          NEW: BOMBER_PLANE_NAMES -> BOMBER_PLANE_IDS (resolved against PLANE_ROSTER at import, so a
          typo is caught at startup rather than silently misclassifying), and is_bomber_plane().
          db_apply_score_delta(bomber=) now picks the score column by the KILLER's aircraft, and
          db_credit_kill(victim_is_bomber=) picks the kill column by the VICTIM's. RANK still comes
          from the COMBINED total - it is one ladder. The death penalty comes off whichever score the
          victim was flying for. Every kill now logs both classes and both aircraft names.
      (2) *** "Fighters Assists" exactly tracked "Fighters Destroyed" - a DUPLICATE credit. ***
          We were sending the killer TWO credit events for one kill: the exit-tail delete (which
          carries the real HUNTER since v229 and credits the kill by itself) AND a separate msg-33
          ScoreEvent. msg 33 was added in v203 when the kill wasn't registering at all; it has been
          redundant ever since v229, and the client was almost certainly scoring the duplicate as an
          ASSIST. An assist should only count when you damaged a target that SOMEONE ELSE killed.
          SEND_SCORE_EVENT_33 = False. (Flip back to True if kill credit regresses.)
v241: ACE NEVER FIRED - the streak had TWO sources of truth and we read the wrong one.
      The ace rule counted a PER-SESSION `kills_since_death` that resets to 0 on every login, while
      db_credit_kill (v240) maintains the real streak in the DB's `kills_in_a_row` column (+1 per
      kill, 0 on death). So a streak already IN the DB - seeded by the admin, or carried over from an
      earlier session - was silently ignored:
            admin seeds kills_in_a_row = 3
            two more kills -> DB goes 3 -> 4 -> 5   (correct)
            session counter goes        0 -> 1 -> 2 (what the ace check actually looked at)
            5 % 5 == 0 never tested -> NO ACE, no announcement, HUD stays "Ace: 0"
      FIX: the DB column IS the streak. score_on_death now reads kills_in_a_row back out of the DB
      (db_credit_kill has already incremented it by then) and awards the ace on THAT; the session
      counter is demoted to a mirror kept in sync for logging. send_stat_block_25's session override
      is removed for the same reason - it would report a LOWER streak than the truth and hide any
      admin-seeded value. One source of truth.
      Every kill now logs the running streak and when the next ace lands:
            [ACE] AC2E_Bigalon kills in a row: 4 (next ace at 5)
            [ACE] AC2E_Bigalon earned an ACE (5 kills in a row without dying) -> aces 0 -> 1
      The new ace is pushed straight out on msg 88 (AceOrRankChangedCB) by the existing post-kill
      re-state, so the in-game HUD "Ace:" counter updates and the client fires its announcement.
      NOTE the in-flight screen's own "Kills In a Row" / "Aces" rows render BLANK - those are
      client-session values it never populates. They are NOT what drives the ace: the server owns
      that rule end to end, so the HUD/HQ figures are the ones to watch.
v240: WEB ADMIN - every HQ Scores field is now editable (end-to-end test harness for msg 25).
      The stat block is fully mapped, so each row the HQ career screen renders gets its own DB
      column, and send_stat_block_25 is now a straight DB -> wire copy: whatever the admin saves is
      exactly what the client renders.
      NEW pilots columns (ALTER TABLE migration in init_db, same pattern as `aces`):
        kills_fighters  kills_bombers  planes_lost  planes_lost_ai  kills_in_a_row
        bomber_score    ai_fighters    ai_bombers   ai_ships  ai_tanks  ai_ground  ai_buildings
      (existing rank / score / kills / deaths / aces keep their meaning; `score` IS the Fighter Score)
      COLUMN -> msg-25 SLOT -> HQ ROW:
        rank f0 u8 Rank | deaths f1 u16 Lost Pilots | kills_fighters f2 | kills_bombers f3
        planes_lost f4 | kills f5 Kills | kills_in_a_row f7 u8 | aces f8 u8
        score f9 FLOAT Fighter Score | bomber_score f10 FLOAT | ai_fighters f11 | ai_bombers f12
        planes_lost_ai f13 | ai_ships f16 | ai_tanks f17 | ai_ground f18 | ai_buildings f19
        (HQ's "Planes Lost" row shows f4 + f13.)
      db_get_pilot_stat25() reads them all; db_credit_kill() keeps kills_fighters / planes_lost /
      kills_in_a_row consistent automatically on every kill and death (dying resets the streak).
      The web editor groups the fields exactly like the in-game screen (Overall Scores / Record vs.
      Other Players / AI Units Destroyed) and prints each one's slot + wire type under the box; every
      input is bounded to its slot's width so a typo cannot corrupt the packet.
v239: *** THE HQ CAREER SCREEN IS DONE. Full field map, real stats, probe off. ***
      Probe #2 answered the last two questions outright:
        * Fighter Score read 1234 and Bomber Score read 5678 when we sent the FLOAT bit-patterns for
          1234.0 / 5678.0 -> *** f9 and f10 are IEEE FLOATS, not ints. *** That is why probe #1's
          ints 9/10 rendered as 0: int 9 reinterpreted as a float is 1.26e-44. build_stat_block_25
          now packs those two slots with '<f'.
        * "Planes Lost" read 184 - not any single marker. 184 = 91 + 93 = f4 + f13, the ONLY pair of
          our six markers that sums to it. So the HQ "Planes Lost" row is a SUM: planes lost to
          PLAYERS (f4, in the player region) + planes lost to AI (f13, in the AI region). That is
          exactly why the in-flight screen carries both rows separately.
      FINAL MAP of the msg-25 block (score+0x30, 20 dwords, FUN_004f4570):
            f0  u8     Rank                    f1  u16   Lost Pilots  (deaths)
            f2  u16    Kills > Fighters        f3  u16   Kills > Bombers
            f4  u16    Planes Lost (players)   f5  u16   Kills (total)
            f6  u16    ? (assists - not on HQ) f7  u8    Kills In A Row
            f8  u8     Aces                    f9  FLOAT Fighter Score
            f10 FLOAT  Bomber Score            f11 u16   AI Fighters
            f12 u16    AI Bombers              f13 u16   Planes Lost to AI
            f14 u16    ? (assists)             f15 u16   ? (assists)
            f16 u16    Ships                   f17 u16   Tanks
            f18 u16    Ground Units            f19 u16   Buildings
      (f6/f14/f15 show nothing on the HQ screen - almost certainly the Assists rows that only appear
      in-flight. Left at 0.)
      STAT25_PROBE is now OFF and every mapped slot carries the pilot's REAL career from the DB:
      rank, kills, deaths ("Lost Pilots"), planes lost, fighter score, aces, and the live
      kills-in-a-row streak. The HQ Scores screen is now a true career screen.
v238: *** THE HQ CAREER SCREEN IS MAPPED. msg 25 DRIVES IT. ***
      With v237 pushing msg 25 when the HQ screen opens, the probe finally ran - and the HQ SCORES
      screen's CAREER column came back FULL of our probe values. Sent f_i = i (f0=rank=5, f8=aces=0)
      and read the mapping straight off the screen:
            Rank              -> f0   (u8)    Lost Pilots      -> f1   (u16)
            Kills > Fighters  -> f2   (u16)   Kills > Bombers  -> f3   (u16)
            Kills             -> f5   (u16)   Kills In A Row   -> f7   (u8)
            Aces              -> f8   (u8)    AI Fighters      -> f11  (u16)
            AI Bombers        -> f12  (u16)   AI Ships         -> f16  (u16)
            AI Tanks          -> f17  (u16)   AI Ground Units  -> f18  (u16)
            AI Buildings      -> f19  (u16)
      13 of 20 fields in one shot. The "Latest" column stayed 0 -> it is a SEPARATE block
      (last-mission stats) that we do not set.
      STAT25_MAP is now filled in, so the CONFIRMED slots carry the pilot's REAL career from the DB -
      kills, deaths ("Lost Pilots"), rank, aces and the live kills-in-a-row streak now appear on the
      HQ Scores screen for the first time.
      TWO LOOSE ENDS, and probe #2 settles both in one pass (only the unknown slots carry markers):
        * Fighter/Bomber Score read 0 even though ints 9/10 went into the two 32-bit slots (f9,f10).
          int 9 reinterpreted as a FLOAT is 1.26e-44 -> renders as 0, which is exactly what we saw.
          So f9/f10 are almost certainly FLOATS: probe #2 sends float bit patterns 1234.0 / 5678.0.
        * "Planes Lost" showed 17 - the same value as AI Tanks (f17), so it is ambiguous. Probe #2
          sets f17=97 and puts distinct markers in the remaining unknowns (f4=91 f6=92 f13=93 f14=94
          f15=95); whichever number turns up in "Planes Lost" identifies its field.
v237: *** THE "ALL 0" PROBE RESULT WAS A BROKEN TEST - msg 25 WAS NEVER SENT. ***
      send_stat_block_25 / send_ace_rank_88 were only ever called from the SPAWN-INIT path (after a
      plane's ServerConfirm). But the HQ SCORES screen is read AT HQ, BEFORE flying - the user's
      screenshot even shows the "FLY LANCASTER" button. Checked both test runs:
            run 112558 (v235):  CONFIRM5 = 0   STAT25 = 0   ACE88 = 0
            run 113555 (v236):  CONFIRM5 = 0   STAT25 = 0   ACE88 = 0
      NOT ONE PLANE SPAWN in either, so msg 25 never went on the wire and every row was 0 BY
      CONSTRUCTION. The probe proved nothing; it never ran. (Same trap as v231, one level up: that
      time I read the wrong screen, this time the message wasn't even sent.)
      FIX: push_career_stats() - msg 88 (rank/aces) + msg 25 (stat block) - is now ALSO fired when
      the client opens the HQ / hangar screen, which it announces with its 0x3a plane-catalog
      request (SEND_CAREER_ON_HQ, debounced by CAREER_PUSH_DEBOUNCE_S). So the HQ Scores screen now
      has the data BEFORE you fly. New CAREER log channel; STAT25/ACE88 lines will finally appear.
v236: TWO THINGS, BOTH FROM THE USER'S HQ SCREENSHOT.
      (1) *** msg 88 WAS UNICAST - peers never learned each other's rank. ***
          Every client keeps a GamerClientScore for EVERY player (Test2's own log: "Create client 0,
          (AC2E_Bigalon), PlayerIndex=0") and the msg-88 payload CARRIES the PlayerIndex, so the same
          packet updates that player's record on ANY client. We only ever sent it to the owner
          (send_rel(s, ...)), so every peer's copy stayed at rank 0. Hence "Bigalon's rank isn't
          displayed correctly on Test2's screen - it loads rank 0, not 3", and the kill announcement
          reading "GBR Cdt Test2" (rank 0). FIX: send_ace_rank_88 now BROADCASTS to every client in
          the room, and a fresh spawn also (re)states every OTHER player's rank/aces so a joining
          client doesn't show everyone as rank 0.
      (2) *** I PROBED THE WRONG SCREEN. msg 25 is back on. ***
          v231's probe was read on the IN-FLIGHT screen (Current Life / Current Game) - which is
          session state the CLIENT computes - so it showed nothing and v233 wrote msg 25 off. The HQ
          SCORES screen is a DIFFERENT consumer: it has "Latest | Career" columns, and it DISPLAYS
          THE RANK. Rank is score+0x30 = exactly f0 of the msg-25 block, so that screen provably
          reads the very structure msg 25 writes, and the other 19 fields should fill its rows.
          The field WIDTHS from FUN_004f4570 line up with it almost row-for-row:
              f0  u8      = Rank                      (CONFIRMED)
              f7  u8      = small counter             (Kills In A Row?)
              f8  u8      = Aces                      (CONFIRMED)
              f9,f10 u32  = the ONLY 32-bit slots     -> Fighter Score / Bomber Score
              f1..f6, f11..f19 u16 = Planes Lost, Lost Pilots, Kills/Fighters/Bombers, AI section
          SEND_STAT_BLOCK_25=True, STAT25_PROBE=True (f_i = i; f0/f8 keep the real rank/aces).
          *** READ THE HQ SCORES SCREEN, NOT THE IN-FLIGHT ONE: whichever row shows N is field N. ***
v235: *** WE TOLD THE PEER TO DELETE THE VERY PLANE THAT VANISHED. ***
      The msg-3 delete-notify is [.. sub=0x03][ONumber u16 LE][exit][tail...] - and
      _ingame_own_object_removed NEVER CHECKED which object it names. It just assumed the sender's
      own plane. Live proof (run 095012), 3 seconds after Test2 respawned from the kill:
          Test2 -> [00320000|030101]   = "delete object 0x0101"
      In that run Test2 was object 0x0100 and AC2E_Bigalon was 0x0101 - so this is TEST2'S CLIENT
      DROPPING BIGALON'S PLANE from its own world (a routine peer-view cleanup). We read it as
      Test2's own plane removal and:
         1. broadcast DELETE3 for TEST2's object (0x0100) to Bigalon -> Bigalon's client dutifully
            deleted Test2 -> *** TEST2 DISAPPEARED FROM THE GAME WORLD ***
         2. cleared Test2's `flying` flag -> the telemetry relay stopped as well.
      The real kill's delete 3s earlier correctly named 0x0100 (Test2's own), which is why the
      handler had always seemed to work - it was right by luck whenever the client only ever deleted
      its own plane.
      FIX: read the ONumber at stored[5:7] and compare with s.my_obj_number BEFORE doing anything.
        * matches  -> the sender's own plane: existing death/exit path, unchanged.
        * a PEER's -> the sender dropped that peer from its world. Do NOT touch the sender's plane.
                      Discard the sender's addr from that peer's _created_peers so the relay
                      RE-CREATES the peer's object on it (otherwise the sender would never see that
                      peer again). New PEERDEL log channel.
        * nobody's -> swallow and log.
      This also fixes the mirror bug nobody had noticed: a client dropping a peer used to silently
      never get that peer re-created.
v234: *** TELEMETRY OPCODE 0x08 - the 'remote plane disappeared' bug. ***
      The flying-state update is [bc][T][00][00][OPCODE][tick u16][ONumber u16][state...] and the
      client emits TWO forms with an IDENTICAL header:
            0x07 -> one position sample            (sz 98)
            0x08 -> the same + one extra 9B sample (sz 107)
      relay_telemetry only ever matched 0x07. Live proof (run 092257) - the exact moment it broke:
            09:35:52.845   05 62 00 00 07 f1c4 0101 ...   <- relayed
            09:35:53.387   05 f2 00 00 08 6bc4 0101 ...   <- SILENTLY DROPPED
      From that instant AC2E_Bigalon's telemetry was not recognised at all, and TWO things failed -
      together they are exactly the reported symptom:
        1. His updates stopped reaching Test2.
        2. Worse: we harvest each player's CONDUCTOR TICK from their telemetry and use it to
           re-stamp what we relay TO them. Bigalon's tick FROZE at 13868 and never advanced, so we
           kept relaying Test2's telemetry stamped with a DEAD tick. Bigalon's client saw Test2's
           updates as ever-more-stale and dropped them -> TEST2 VANISHED FROM HIS WORLD, ~3 minutes
           after the freeze, with nothing in the log saying a word.
      This was NOT a v233 regression - the 0x07-only filter is old; it just needed the client to
      switch forms mid-flight to expose it. Both forms have the tick at [5:7] and ONumber at [7:9],
      so 0x08 relays exactly like 0x07 and the extra block is forwarded verbatim.
      FIX: TELEM_OPCODES = (0x07, 0x08).
      HARDENING: never re-stamp with a stale tick. If a peer's last_telem_time is older than
      STALE_TICK_WARN_S (3s) we log a loud STALE-TICK warning and leave the sender's own tick in
      place rather than poisoning the packet. A frozen conductor tick can never again fail silently.
v233: SCORING SUBSYSTEM FINALISED. Cleanup + the one improvement the RE handed us for free.
      (1) EXACT KILL ATTRIBUTION. The victim's own client NAMES ITS KILLER: the delete-notify exit
          entry carries the HUNTER object number at entry+3 (proven live - Test2's shot-down entry
          `01 01 | 53 | 00 01 ...` -> hunter 0x0100 = 256 = Bigalon). score_on_death now credits the
          pilot who owns that object, which is correct for ANY number of players. The old
          'most-recent shooter within KILL_CREDIT_WINDOW' guess survives only as a fallback for when
          no hunter is present. Both paths are logged (attribution: EXACT / FALLBACK).
      (2) msg 25 + PROBE OFF (SEND_STAT_BLOCK_25=False, STAT25_PROBE=False). The probe did its job:
          it PROVED the scores screen consumes only f0 (rank, score+0x30) and f8 (aces, score+0x50)
          from the 20-dword block; f1..f19 display nothing. So msg 25 cannot drive the per-life
          counters, and sending it would only zero 18 score fields we never identified, for no gain
          (msg 88 already sets rank+aces). Code + findings kept, disabled.
      (3) took_damage is now cleared on EVERY spawn unconditionally. It was nested inside the
          SEND_ACE_RANK_88 block, so turning that flag off would have latched the damage flag and
          made every clean exit count as a death again.

      WHERE THE SUBSYSTEM LANDED (honest):
        WORKS - DB career scoring (kills/deaths/score), the 13-rank ladder (rank displays and updates
                in-game), server-authoritative live aces (5 kills without dying; death wipes them),
                correct death counting (damaged exit = death, clean ground exit = not), and the
                in-game KILL ANNOUNCEMENT by name ('AC2E_Bigalon destroyed GBR Cdt Test2').
        KNOWN LIMITATION - the numeric per-life 'Current Life / Current Game' HUD counters. Full RE
                established these are computed by the CLIENT's mission-scoring code from its own
                damage bookkeeping. No server->client message sets them: msg 25 does rank+aces only,
                and both ExitDataArrive (MEC=5) and ScoreEvent (MEC=1) route to FUN_00478640, which
                is announcement-only. The victim's hit list IS populated (its client logs
                'HitFrom(Number=256 ... Value=425)') but its exit serialises Hits=0 after the
                damage-share/age filter. Under the server-only constraint these counters appear
                genuinely unreachable. Documented, not worked around.
        ALSO KNOWN - a solo crash of an UNDAMAGED plane emits no msg 28, so the server can't see it
                and won't count it. Closing that needs the telemetry damage-percentage field.
v232: FALSE DEATHS ON A CLEAN EXIT - fixed properly, and an admission about the previous approach.
      *** A CRASH AND A CLEAN GROUND EXIT ARE IDENTICAL ON THE WIRE. *** Proven from the logs:
        - Both send MissExitCode 26 (the client's OWN untruncated log says so for both), and MEC is
          truncated to 4 bits in (MEC<<4)|SE anyway, so 26 and 10 collapse to the same nibble.
        - Both are followed 1ms later by the same sub=0x3a plane-catalog request.
        - NEITHER produces a leave-arena event: exit-to-HQ sends NO msg 64. Run 081106 contains ZERO
          back-to-lobby events.
      So v225-v231's "defer the death 4s and cancel if they leave the arena" could NEVER cancel -
      there was no leave to observe. Every exit confirmed as a death and the count climbed forever.
      That heuristic was wrong from the start; it only ever appeared to work by luck.
      THE REAL RULE (as the user described it, and as the client implements it) is about DAMAGE, not
      the exit code: exit while DAMAGED and it counts as a death - the game even warns you - while
      sitting undamaged on the ground and exiting is clean and silent.
      FIX: track damage from the one signal we actually have. msg 28's record is
      [VictimNumber i16][HunterNumber i16][count u8]+count*9B (HitToPlaneCB, FUN_004f3820), so the
      relay now marks the VICTIM's session took_damage=True; it is cleared on every fresh spawn. A
      solo MEC-26 exit then counts as a death only if the plane was damaged. A SHOT-DOWN (the long
      form, which names the HUNTER outright) is unambiguous and still always counts.
      The DEATH_CONFIRM_DELAY deferral is removed entirely.
      KNOWN GAP (stated honestly): a solo crash of an UNDAMAGED plane - flying into the ground with
      no enemy fire - produces no msg 28, so the server cannot see it and will not count it. Closing
      that needs the plane's damage percentage out of the telemetry stream (the HUD's
      "Approx.Damage"), which is the next thing to decode.
v231: CALIBRATING THE STAT BLOCK + two fixes from the v230 probe run.
      (1) *** f0 IS THE RANK. *** FUN_004f65a0 does `lea ebx,[ebp+0x30]` before calling FUN_004f4570,
          so the 20 fields are the dwords at score+0x30 .. score+0x7c. msg 88 (FUN_004f4120) writes
          score+0x30 = rank and score+0x50 = aces, therefore:
                f0 -> score+0x30 == RANK   (CONFIRMED the hard way: v230 put deaths=22 into f0 and
                                            the client announced the highest rank - it clamps >12)
                f8 -> score+0x50 == ACES   (0x30 + 8*4 = 0x50)
          Two slots down, eighteen to go - so v231 adds a PROBE mode (STAT25_PROBE): every unmapped
          slot is sent the value of its own index (f1=1, f2=2 ... f19=19) while f0/f8 keep the pilot's
          REAL rank/aces. One look at the scoreboard then maps the entire block: whichever row reads
          N is field N. Set STAT25_PROBE=False once STAT25_MAP is filled in.
      (2) FALSE 'lost plane' on EXIT-TO-HQ: v229 added MEC nibble 0x2 to DEATH_MEC_NIBBLES on a guess
          (it appeared in the 0x2d exit of a kill). But EXIT-TO-HQ also uses MEC 2, so parking an
          undamaged plane and leaving was logged as a lost plane. REMOVED - the 0x2d kill is caught
          by the `scored` (>=14B) check before that set is ever consulted, so nothing is lost.
v230: *** FOUND THE SCOREBOARD SETTER - msg 25 (0x19), server->client. ***
      The killer's client log (messages94) proved every earlier piece works: on a kill it logs
      "ExitDataArrive. Number=257. MEC=5, EEC=3. (Test2)", then "AC2E_Bigalon destroyed ... Test2"
      (kill recognised + announced by name), then "ScoreEvent. Number=0. MEC=1, EEC=3." (v224 msg-33
      decoding correctly). BUT the counters never moved - because BOTH the ExitDataArrive MEC=5 branch
      AND the ScoreEvent MEC=1 branch only call FUN_00478640 (the ANNOUNCEMENT). Neither writes a
      displayed counter.
      THE ACTUAL SETTER is dispatch slot 25 (0x19) -> FUN_004f65a0 (registered at 0x4f14bd:
      mov [0xc81f3c],0x4f65a0; (0xc81f3c-0xc81ed8)/4 = 25). It matches the GamerClientScore by
      PlayerIndex, then FUN_004f4570(score+0x30, payload+5) unpacks 20 FIELDS straight into the score
      object - THE Current Life / Current Game stat table. We never sent it, so the columns were
      always blank no matter what else we fixed.
      Wire: [0x19][PlayerIndex u32 LE] + 41-byte packed block (u8,6xu16,2xu8,2xu32,9xu16).
      v230 adds build_stat_block_25 / send_stat_block_25 (DB-backed) and sends it at spawn and after
      each kill/death, alongside msg 88. Reconciles with v220: the client's inbound 'out 25' is a
      SHORT 7-byte notify (still swallowed - echoing it caused the garbage-ace announcements); the
      41-byte SERVER->CLIENT msg 25 is the setter, a different direction of the same id.
      The exact slot->stat mapping (STAT25_MAP) is a first guess from the manual's row order; the plan
      is to read the HUD and correct it from what actually moves.
v229: *** THE EXIT TAIL IS NOT FILLER - it carries the HUNTER. This is why kills never registered. ***
      Live capture of Test2 being shot down by Bigalon (run 073215):
          [00e20000|03010153] +00010000000000000c00
            03 | 01 01 | 53 | 00 01 | 00 00 | 00 00 00 00 | 0c
           sub   id=257  exit  ^^^^^                         PPT type
                                HUNTER = 0x0100 = 256 = Bigalon's object!
      The victim's client TELLS US who killed it, at entry+3. And ExitDataArrive calls FUN_004f8d10
      on EVERY 12-byte form BEFORE the MEC switch, and that parser READS the tail:
          entry+0 u16 id | entry+2 u8 exit | entry+3 u16 HUNTER | entry+5 u16 | entry+7 u32 |
          entry+11 u8 PPT type
      v228 (and build_scored_delete_object_3 long before it) ZERO-FILLED those 9 bytes, on the false
      claim that "the tail isn't read on the MEC=5 path". So the killer's client received hunter=0
      and had nothing to credit. The kill was announced at best, never counted.
      FIX: relay the victim's ORIGINAL entry VERBATIM. It sits at stored[5:5+size] in the client's own
      delete-notify ([sub 0x03][id u16][exit][tail...]), and now goes to EVERY peer including the
      killer - the special zero-filled 'scored delete' is demoted to a fallback for when no real entry
      is available. Entry length still comes from EXIT_EEC_ENTRY_SIZE so the parse loop can't desync.
      ALSO: the real SHOT-DOWN exit codes are finally known - 0x53 (MEC 5 | EEC 3) and 0x2d (MEC 2 |
      EEC 0xd) - so MEC nibbles 5 and 2 join 0xa (crash) in DEATH_MEC_NIBBLES. The EXITTAIL/POST-AUTH
      logs now print the decoded hunter id.
v228: *** EXIT-TAIL DELETE - the in-game statistics feed. ***
      Decoded ExitDataArrive (FUN_004f8f20, the object's vtable+0x10). Two facts settle everything:
        1. The type-3 handler (FUN_007e3bb0) only CALLS ExitDataArrive when the entry carries MORE
           THAN 2 BYTES after the object id. Our peer delete was a BARE [id:2] - so the method was
           SKIPPED, the plane silently vanished, and NO statistics were ever touched. That is why
           kills, deaths and planes-lost all stayed 0 in the HUD / Current Life / Current Game.
        2. ExitDataArrive decodes EEC = b & 0xf, MEC = b >> 4, and RETURNS THE ENTRY SIZE, chosen
           by EEC:  0/1 -> 3,  2 -> 4,  3/4/5/7/8/9 -> 12,  0xc -> 4,  0xd -> 13,  0xe -> 6.
           The size we send MUST match or its parse loop desyncs and walks off the entry (peer CTD).
           On the 12-byte forms MEC then selects: 4 -> kill announcement (with names);
           5/6/0xb -> FUN_00478640, the MISSION EVENT that drives scoring.
      FIX: build_exit_delete_object_3() emits [03][X f32=0][Z f32=0][id u16][EXIT byte][filler], with
      the length taken from EXIT_EEC_ENTRY_SIZE (the handler's own table). The victim's REAL exit
      byte - (MissExitCode << 4) | ScoreEvent, straight off its own delete-notify - is threaded from
      _ingame_own_object_removed into broadcast_object_delete_3 and sent to ALL peers.
      Broadcast to everyone (not just a guessed killer) is deliberate: on the MEC 5/6/0xb branch each
      client credits the kill from its OWN local damage list, so every peer must see the exit.
      The killer still gets the proven 0x53 SCORED delete; an unknown EEC falls back to the bare
      delete rather than risk a desync. New knob EXIT_TAIL_DELETE_TO_PEERS, new EXITTAIL log channel.
v227: DECODED the delete-notify's trailing byte properly. It is NOT a bitfield - it is exactly the
      byte Msn_Exit.cpp (FUN_0045d930) builds:   EXIT = (MissExitCode << 4) | ScoreEvent
      (MEC is truncated to 4 bits on the wire, so the nibble is MissExitCode & 0xf.)
        0xa0 -> MEC&0xf=0xa, SE=0 : MissExitCode 26 = CRASH. (26<<4)&0xff == 0xa0, an exact match
                                    for the client's own "MissExitCode=26, ScoreEvent=0" log. DEATH.
        0x11 -> MEC&0xf=0x1, SE=1 : re-fly / plane swap. PROVEN in run 070240 - the player was ALONE
                                    in the arena (so it cannot be a shot-down) and the StartPlace
                                    request arrives 22ms BEFORE the removal.          NOT a death.
      v225 gated on "bit 0x80 set", which gave the right answer for a crash but only by coincidence
      (0xa0/0x80 happen to have bit 7). v227 classifies on the MEC nibble (DEATH_MEC_NIBBLES) and
      LOGS the decode for every removal, so unseen codes - notably a real SHOT-DOWN MEC, still never
      observed - can be read straight out of the logs and added.
      The 4s deferral stays: a crash and an EXIT-TO-HQ carry the SAME byte (both MEC 26) and differ
      only by what follows, so the solo death is confirmed only if the player stays in the arena.
      ALSO CONFIRMED (Msn_Exit.cpp): when IsDelete=1 the client does NOT send msg 33 at all - the
      exit data is stored via NetworkBody::SetBody (FUN_0045caf0) and rides as the AddData BODY of
      the DELETE message. That is why run 070240 contains ZERO type=0x21 messages: msg 33 only goes
      on the wire when IsDelete==0. So the v226 ExitEvent relay will rarely/never fire for crashes,
      and the in-game stat feed must instead come from the exit tail carried on the DELETE.
v226: *** RELAY THE EXIT-EVENT (msg 33) - why NOTHING (kills, deaths, planes lost) ever ticked. ***
      Found the client's OWN sender for msg 33: Msn_Exit.cpp, FUN_0045d930. It emits
        DAT_00c82350 = 0x21 -> [0x21][AddData][Number u16][(MissExitCode << 4)|ScoreEvent][nHits +
        8-byte hit records: [u16][u32][i16 damage share]]
      Two consequences:
        (a) It packs the type byte as (MEC << 4) | ScoreEvent - INDEPENDENTLY CONFIRMING the v224
            nibble order (MEC high, EEC low). v224 was right.
        (b) msg 33 IS THE EXIT-EVENT, and it carries a HITS LIST: the dying plane reports who hit it
            and each hitter's damage share. That list is FA's kill-attribution mechanism, and the
            receiving handler (0x004f9ae0) is what ticks each client's Current Life / Current Game
            statistics.
      v222 added 0x21 to NO_ECHO_TYPES to stop it being blind-ECHOED to the SENDER (that echo fed the
      client its own 0xFFFF object index -> ARR<NET::OBJECT*,2048>[65535] bounds CTD). That was
      right - but "don't echo to the sender" is NOT "don't relay to the peers", and we were dropping
      it entirely. So NO client ever received an ExitEvent and NO stat pipeline ever ran, which is
      exactly why kills, deaths AND planes-lost were all stuck at 0 in the HUD and session stats.
      FIX: RELAY_EXIT_EVENT_33 - relay the message VERBATIM to every other player in the room (never
      back to the sender). New EXIT33 log channel dumps the raw bytes so the exact field layout can
      be confirmed from the next run.
v225: FALSE DEATHS - one crash was being counted THREE times. v222 made every own-plane removal a
      death; it isn't. The msg-3 delete-notify payload ends in a REASON byte
      ([.. 0x03][ONumber u16 LE][REASON]) and run 004058 shows three distinct cases for what the
      user reported as a SINGLE crash:
        00:42:19  reason=0xa0  -> the real crash                                    (count it)
        00:44:07  reason=0x11  -> RESPAWN handoff: the client drops its old plane as it takes a
                                  new one. The StartPlace GRANT lands in the SAME MILLISECOND
                                  (log lines 1146 -> 1148).                          (NOT a death)
        00:44:24  reason=0xa0  -> EXIT-TO-HQ: identical on the wire to a crash, but followed ~3s
                                  later by 'back to lobby' (00:44:27.756).           (NOT a death)
      FIX: bit 0x80 of the reason byte = plane DESTROYED (0xa0/0x80 set; 0x11/0x22 clear), so the
      respawn handoff is now never a death. A solo DESTROY is still ambiguous (crash vs exit-to-HQ
      look the same at that instant and differ only by what FOLLOWS), so its death credit is
      DEFERRED by DEATH_CONFIRM_DELAY (4s) and CANCELLED if the player leaves the arena in that
      window. A respawn does NOT cancel it - a genuine death respawns ~2s later, so cancelling on
      respawn would erase every real death. A SHOT-DOWN (long >=14B scored form) is unambiguous and
      is still credited immediately. New knobs: DEATH_DESTROY_BIT, COUNT_EXIT_TO_HQ_AS_DEATH,
      DEATH_CONFIRM_DELAY. New DEATH log channel shows deferred / CONFIRMED / CANCELLED.
v224: *** msg-33 ScoreEvent NIBBLES WERE SWAPPED - this is why kills never showed in the HUD /
      in-game statistics. *** Decoded the handler (0x004f9ae0, VNet_Rcv.cpp; it logs
      "ScoreEvent. Number=%i. MEC=%i, EEC=%i."):
          [0]=0x21  [2:4]=u16 PlayerIndex  [4]=TYPE byte: HIGH nibble = MEC, LOW nibble = EEC
      We were emitting ((eec<<4)|mec), so MEC=1/EEC=3 went out as 0x31 and the client decoded it as
      MEC=3, EEC=1 - the exact swap. EEC==1 is the ANNOUNCE-ONLY branch: it asserts MEC in {2,3}
      (which 3 satisfied, so it never even errored), prints the kill message via string 0x83, then
      JUMPS PAST the scoring code. So every kill produced at most a chat announcement and NEVER
      reached the mission-event/stat path - kills stayed 0 in the HUD forever.
      FIX: emit ((mec<<4)|eec). With MEC=1/EEC=3 the type byte is now 0x13, which takes EEC!=1 ->
      FUN_004f8d10 -> MEC==1 -> FUN_00478640(mission event 0x26) + score_obj+0x2fc=1. MEC=1 matches
      the client's own scored exit ("MissExitCode=1, ScoreEvent=1" for a shot-down vs 26 for a solo
      crash). New tunables SCORE33_MEC / SCORE33_EEC, and both the log line and the TX label now
      print the resulting type byte so the wire value can be checked at a glance.
      VERIFY IN THE CLIENT LOG: the killer's messagesNN.log should now contain
      "ScoreEvent. Number=<PI>. MEC=1, EEC=3." - previously that line never appeared at all.
v223: RANK LADDER (score -> rank) + death score penalty. Kills add points, deaths subtract them, and
      the RANK is recomputed from the new score and re-stated to the client via msg 88.
      RESEARCH (FA.exe + the official Fighter Ace manual, "The Scores Screen" p64):
        * POINTS PER ACTION already come from msg 96 SCORE_TABLE
          (ARR<FA3::SCORE::DYNAMIC_OBJECT_SCORE_DEF,256>, records [obj_type][score][kills][?]) which
          the SERVER supplies - the manual confirms the mission log "details the number of points you
          received for each action". So per-target point values are ours (build_score_table_96).
        * RANK IS SERVER-AUTHORITATIVE. Rank is an INDEX 0..12 (13 ranks); the client hard-clamps it
          (FUN_00428770: `if (0xc < rank) rank = 0xc`) and renders the NAME ITSELF from its own
          localized string array (table 0xbf666c, stride 8 -> string index 0x303 + 2*i, via
          PARR<char const*>::operator[]); those strings aren't even in FA.exe. An exhaustive scan of
          .data/.rdata found NO score->rank threshold table in the client - the original VR-1 host
          computed rank and pushed it in msg 88's rank byte. So WE define the ladder and only ever
          send the INDEX. RANK_NAMES here are cosmetic (logs/web admin) only.
        * The manual CONFIRMS the v222 ace rule verbatim: "Kills In A Row - enemy planes destroyed in
          secession without having your pilot killed or captured" and "Aces - For each five 'Kills In
          A Row', you are awarded one 'Ace'."
      NEW: RANK_THRESHOLDS[13] (min career score per rank), RANK_NAMES[13] (cosmetic),
      DEATH_SCORE_PENALTY (default 50), rank_for_score(score) -> 0..12, and db_apply_score_delta()
      which adds/subtracts points (floored at 0), recomputes the rank and persists both. score_on_death
      now calls db_credit_kill with points=0 (counters only) and routes ALL score changes through
      db_apply_score_delta, so points are never double-added. Promotions/demotions are logged (RANK).
v222: DEATHS NOW COUNT + SERVER-AUTHORITATIVE LIVE ACE RULE.
      (1) THE BUG: score_on_death() opened with `if len(death_payload) < 14: return`. A SOLO CRASH
          arrives as the SHORT 8-byte delete-notify (tb=0x42 sub=0x03, [00420000|030001a0]) - only
          a shot-down-by-someone death uses the 14-byte form. So every self-crash was DISCARDED:
          no death counted, ace status untouched ('I crashed, it should have taken my ace - it
          didn't'). Now BOTH forms count as a death for the victim; only the KILLER-attribution
          needs the long form.
      (2) LIVE ACE RULE, server-authoritative (LIVE_ACE_TRACKING): FA awards an ace for
          ACE_KILLS_PER (5) kills WITHOUT dying, and DYING WIPES YOUR ACES. The server now owns
          this end-to-end: the DB `aces` column is the single source of truth (seeded by the web
          admin editor), a per-session `kills_since_death` streak counter drives the awards
          (db_set_pilot_aces), and every change is re-stated to the client via msg 88 - pushed on
          daemon threads so the blocking reliable send never stalls the RX path.
      (3) NO_ECHO_TYPES: msg 33 (0x21) SCORE-EVENT arrives with its id in the TYPE byte and
          sub=0x00, so the sub-byte NO_ECHO_SUBS check never matched it and it was being
          BLIND-ECHOED ('cmd=0 type=0x21 sub=0x00 -> echo', run 104546) despite 0x21 already being
          listed there. Added a TYPE-byte guard; the client's own score report is now consumed, not
          reflected (same class of bug as msg 25 in v220).
      STILL OPEN: kills/deaths/planes-lost are not yet STATED to the client's score object (msg 88
      carries only aces+rank), so those scoreboard columns remain blank - the setter for the score
      object's kill/death counters is the remaining Project A item.
v221: STORED ACE STATUS. Added an `aces` column to the pilots table (INTEGER, default 0, with an
      ALTER-TABLE migration for existing DBs) and exposed it in the web admin Pilot Stats editor.
      db_get_pilot_career() now returns (score, kills, deaths, rank, aces) and send_ace_rank_88()
      pushes the STORED ace value instead of deriving it from kills (pilot_aces()). Rationale: FA's
      LIVE ace status is a CLIENT-side session rule - 5 kills without dying, reset on death - which
      the server must not try to compute or persist. What the server owns is the pilot's PERSISTENT
      career ace standing, which msg 88 states authoritatively (score obj +0x50, a u8; rank is +0x30).
      pilot_aces()/ACE_KILLS_PER are retained but no longer used by the 88 sender.
v220: SCORING - fix the bogus 'new Ace Status'/'new Rank' announcements on team-change reentry, by
      NOT echoing msg 25 (0x19). Root cause found from Test2's client log (messages46) + our server
      log: the client sends msg 25 (0x19) = an ace/rank/score STATE REPORT (client->server, fire-and-
      forget). It arrives compound-wrapped (and sometimes direct); msg 25 was NOT in the no-echo set,
      so it fell through to the 'unknown inner -> echo inner' default. The echoed 'in 25'7' made the
      client re-ingest its OWN report as authoritative and re-evaluate ace/rank against its current
      (garbage/stale at a team-change spawn) stat state -> the bogus announcements. The EVENT fires on
      the same log line as the echoed 'in 25'7', only when it lands right after InsertPlayer (spawn) -
      exactly the 'sometimes garbage, sometimes clean' the user reported. Fix: add 0x19 to BOTH the
      compound no-echo set and the direct-path NO_ECHO_SUBS. msg 25 is consumed, never echoed.
      This is the culmination of Project A (Steps 1-3): the two scoreboards were identified
      (GAMER_CLIENT personal + CAMP_SCORE_PRODUCTION_DATA[8] nation), the score object was found to
      be zeroed at creation (so garbage was NOT uninitialised memory), and the true trigger was our
      own echo of the client's msg-25 report. Also retained: v218/v219 spawn-time msg 88 (sets
      aces/rank once the object exists) + DB career plumbing.
v219:
v219: SCORING - push the pilot's REAL career aces/rank from the DB, at the TEAM/ROOM change (not just
      at spawn), and never zero it. v218 proved msg 88 works (it reset Test2's aces to 0), but the
      garbage + the client's 'new ace status' announcement (29 aces) fire AT THE TEAM CHANGE, before
      the spawn-time 88 lands. The client's GamerClientScore object PERSISTS across a team change and
      its aces (+0x50) / rank (+0x30) are written ONLY by msg 88, so unless the server states them at
      the transition the client announces whatever uninitialised memory it holds.
      v219: (a) new db_get_pilot_career() -> (score, kills, deaths, rank) + pilot_aces() (career
      kills // ACE_KILLS_PER); (b) send_ace_rank_88 now RE-READS the DB career values every send
      instead of taking hardcoded zeros - a team or room change RESTORES the pilot's real standing
      rather than wiping it; (c) new _push_career_stats_88() fired on BOTH team-change branches (join
      and leave) as well as the existing spawn hook.
      STILL OPEN: kills / deaths / lost-planes / lost-pilots garbage. Those are NOT simple score-
      object fields (they're computed via score-object methods FUN_004269a0 / FUN_00428360), so msg 88
      does not touch them. Re-test to see whether fixing the aces/rank timing also settles them, or
      whether they need their own authoritative setter (deeper RE - scope before committing).
v218:
v218: SCORING - fix the garbage aces/rank on the scoreboard (msg 88 AceOrRankChangedCB). Test2
      swapping USA->GBR and re-entering showed garbage stats (e.g. '96 Aces', bogus rank). Root
      cause (decompiled FA.exe FUN_004f4120): the score object's aces (score+0x50) and rank
      (score+0x30) fields are written ONLY by msg 88 (VNET table 0xc81ed8 slot 88), which we never
      sent - so they held whatever the freshly-allocated GamerClientScore object had. Added
      build_ace_rank_88 / send_ace_rank_88 (wire: [0x58][PlayerIndex u32][aces u8][rank u8], wrapped
      in a msg-13 batch) and send an authoritative 88 (aces=0, rank=0) on each spawn from
      _fire_server_confirm (after the score station exists). Toggle SEND_ACE_RANK_88. NOTE: this
      fixes ACES/RANK only; the kills / lost-planes / lost-pilots garbage (other score-object
      offsets) is a separate init still to be traced (step 2b) if the test shows it persists.
v217.2:
v217.2 (STEP 2 of 2): with the SYNACK cap fix (step 1) confirmed stable, flip RTT_SAMPLING=True to
      re-enable client-side RTT sampling. The ring is now genuinely bounded at 32 (cfg[0x40] finally
      delivered at packet byte 88), so next_exp=seq+1 samples RTT each ACK safely and the System
      Status / HUD latency becomes a live moving average over the last 32 samples (jitters like 2009)
      instead of frozen at the connect value. This is what v216 attempted; it crashed only because
      the cap wasn't reaching the client (the byte-88 misalignment fixed in step 1). TEST FOCUS:
      multiple game-world reentries (the old CTD trigger) - confirm NO CTD while latency now moves.
      Instant revert available: RTT_SAMPLING=False falls back to the stable frozen-latency behavior.
v217:
v217 (STEP 1 of 2): FIX the SYNACK config byte-alignment so the RTT ring cap actually reaches the
      client. Root cause of the re-entry CTD (and of v216's immediate crash): the client copies its
      68-byte net-config from SYN-section+0x10 = WIRE BYTE 24, so it reads the RTT-ring CAPACITY from
      cfg[0x40] = packet BYTE 88. Our config block is written at byte 16 (8 bytes early) and the
      packet was only 84 bytes, so byte 88 was OUT OF BOUNDS -> the client used 0/garbage as the cap
      -> the RTT sample ring was unbounded and, once a sample was taken, overran the 32-slot region
      into the delivery-callback pointer (ring index 64 == struct+0xcc) -> CTD. v215 avoided it only
      by suppressing sampling (next_exp=seq+2); v216 re-enabled sampling onto the unbounded ring and
      crashed on the first sample.
      FIX (minimal, protects the v215 baseline): extend the SYNACK 84 -> 92 bytes and write the RTT
      cap (32) at the TRUE location, packet byte 88 == cfg[0x40]. The existing config block at byte
      16 is left BYTE-FOR-BYTE UNCHANGED, so the only value the client now sees differently is the
      cap (out-of-bounds 0 -> 32). STEP 1 keeps RTT_SAMPLING=False, so this change is INERT (the ring
      never advances) - its sole purpose is to confirm the 92-byte SYNACK doesn't disturb connect and
      the game stays as stable as v215. STEP 2 will flip RTT_SAMPLING=True now that the ring is truly
      bounded, to get real-time latency without the CTD.
v216.1:
v216.1: REVERTED v216's RTT-sampling attempt (RTT_SAMPLING=False). Re-enabling sampling via
      next_exp=seq+1 REGRESSED: CTD on the 4th respawn AND latency still L:0.00 on both machines - so
      it re-armed the RTT-ring overflow without even producing live latency. The RTT_RING_CAP=32 in
      the SYNACK config does not bound the sampler ring the way the isolated FUN_10006f55 index-wrap
      implied. Back to the stable v215 behavior: latency frozen (cosmetic) but NO CTD. Real-time
      latency will need a route that does NOT advance that ring. Baseline restored = v215/v216.1.
v216:
v216: REAL-TIME LATENCY - re-enabled RTT sampling (was frozen since the CTD fix). The System Status
      'latency' had been fixed at its connect-time value because our build_rel_ack used next_exp=seq+2,
      which deliberately SUPPRESSED the client's RTT sampling to avoid the old 3rd-reentry CTD (the
      RTT ring overflowing at index 64 into the delivery-callback pointer at +0x2042c). That CTD is
      now structurally impossible: v209's RTT_RING_CAP=32 (SYNACK config) makes the sampler
      (FUN_10006f55) wrap the ring index at 32, so ring writes stay in struct 0x4c..0x8c, far below
      the index-64 callback slot. With sampling safe, next_exp=seq+1 lets the client take an RTT
      sample per ACK; the displayed latency is a moving average over the last 32 samples, so it
      JITTERS in real time like 2009 (instead of a frozen number). Single toggle RTT_SAMPLING=True;
      set False for an instant revert to the frozen-but-safe v215 behavior. Everything else is
      identical to the stable v215 baseline. TEST FOCUS: multiple game-world reentries (the old CTD
      trigger) - confirm NO CTD returns while latency now moves.
v215:
v215: THE REAL IN-GAME TIME KEEPER - STATUS packets (found via the user's session-timer clue). The
      System Status window's session clock was stuck at 0:00; that window (bytes/sec, loss%, latency,
      SESSION TIME) is fed by a two-way 'Game Status Message' STATUS exchange SEPARATE from the NTP
      time sync, which WE NEVER DROVE (so all its fields read 0). Decoding it revealed the missing
      mechanism: when the client processes a STATUS request it calls FUN_10007d13 ('STATUS Update
      server base time'), which ADDS the packet's base-time increment to the NET-time BASE
      (DAT_1001d0b0) via FUN_100079c4. That base is the value we'd PROVEN was otherwise connect-only
      (set-base is gated behind a state-1 SYN the in-game dispatcher rejects). So the STATUS packet
      is how the server ADVANCES the client's base mid-game - which defeats the 262s wrap of the
      18-bit A field (base advances -> base+A tracks real time -> A's wrap stops mattering). This is
      almost certainly how the 2009 server kept in-game time; our one-way NTP beacon was a wrong
      substitute that wrapped and, during a resync, impersonated a ping reply (v214's freeze).
      v215 adds build_status_request (DATA section, sub_type=4, base-increment @ wire 8, status
      counters, seq) and sends one every STATUS_INTERVAL_S (2s) in-game with base-increment = elapsed
      ms since the last STATUS. connid captured from the client's own packets (STATUS/CONNID log).
      Beacon kept ON for now (belt-and-suspenders while we confirm STATUS works). SUCCESS SIGNAL:
      client logs 'New server base time', the System Status session timer counts up (was 0:00), and
      the flight survives past the old 262s wrap point. If confirmed, the beacon can be retired.
v214:
v214: TIME-SYNC PROTOCOL REWORK (full vcncNet decode). Built a complete model of the client's
      time/heartbeat/connection layer from Ghidra:
      - recv-thread loop (proc @0x10006357, spawned by FUN_1000630c): every ~125ms it runs the
        time-sync scheduler FUN_100091b7(now), then recvfrom -> dispatcher FUN_100032da.
      - CONNECT sync: vcncConnect (FUN_1000b084) calls IOCInitializeTimeSynchronization(level=2)
        (FUN_10009407): a BLOCKING two-way sync - it sends 12-byte pings (FUN_100090e4, flag 0x40 ->
        wire byte[2]=0x80) and needs 4 valid replies (d664=4); 33 pings w/ 0 replies -> d660=5 (FAIL)
        -> then it REBINDS to a 'unique port' (FUN_100032b2) and retries. level 0 would instead set
        d660=3, offset=0 (trust local clock) and never ping - but that's a client-side vcncOpen value
        (DAT_1001f85c=2), not server-settable.
      - IN-GAME: the scheduler resyncs (state 3->2, pings every 2s) whenever the last time sample
        (d630) is staler than the drift window (d65c, 8s..17min). The two-way ping/reply is the
        client's intended in-game time source AND its latency measurement (HUD 'L:').
      - Our one-way beacon both (a) SUPPRESSED that resync (kept d630 fresh) and (b) wrapped at 262s.
        v213 (no beacon) let the client resync, but its pings 'weren't received' -> sync FAIL -> -2
        freeze.
      ROOT-CAUSE CANDIDATE now fixed: on_pkt DROPPED packets from any addr not already in sadrs
      (get_s -> None -> return, SILENTLY). If the client moved its source port (the sync-fail
      'unique port' rebind, or NAT), its time pings arrived from an unknown addr and were dropped ->
      no reply -> 33 pings/0 valid -> d660=5 -> freeze. v214 adds: (1) RAW_RX_LOG to log EVERY inbound
      packet incl. unknown-addr ones, (2) _match_session_by_ip + port-move adoption so a 12-byte TIME
      ping from a moved port is matched to its session by IP, adopted, and ANSWERED. Beacons kept ON
      (IN_GAME_BEACON=True) for this diagnostic pass so we get a safe baseline while we see the raw
      inbound stream. Next: with the port-drop fixed, retry no-beacon so the client self-resyncs.
v213.1:
v213.1: REVERTED v213's no-beacon experiment. It froze on the FIRST game entry (run_220823):
      stopping the in-game beacons made the client's time sample go stale; it entered resync (sync
      state 2) and sent its own pings, but those pings NEVER reached the server (zero 12-byte
      data[2]&0x80 packets logged) and our sentinel keepalives weren't valid samples, so after ~33
      pings/~66s the client hit 'No response from server' -> sync state 5 -> vcncGetTimeState -2 ->
      game spun and froze. LESSON: the one-way TIME beacon is LOAD-BEARING - it is the client's sole
      in-game time source; the client does NOT self-resync via raw two-way pings the way v213 assumed.
      Back to IN_GAME_BEACON=True (v212 behaviour: survives to the 262s wrap). The wrap is still the
      real problem; the resync path is not the answer. Kept the RX/TIMEPING ping-logging for future
      diagnosis. build_keepalive/KEEPALIVE_S retained but dormant.
v213:
v213: NET-TIME FREEZE - the REAL fix (pure server-side), found via full Ghidra decode + the user's
      key observation that the game transmits constantly but receives almost nothing in-game. The
      client has a self-healing clock RESYNC (FUN_100091b7): when its last time sample (DAT_1001d630)
      goes staler than its drift window (DAT_1001d65c), it drops to sync state 2 and sends 12-byte
      two-way TIME PINGS (flag 0x40 -> wire byte[2]=0x80), and on the reply it CLEARS its sample ring
      (FUN_10007c9c) and RE-BASELINES the offset from scratch (first sample accepted unconditionally,
      FUN_100081be) - which absorbs ANY discontinuity (incl. the 262s A wrap) with no >32s slew, and
      the round trip MEASURES latency (the HUD 'L:'). Our 1s one-way beacons kept DAT_1001d630 fresh,
      so the client NEVER resynced -> the beacon's 18-bit A field wrapped at 262s as a raw step ->
      'CRAP backward NET Time' freeze (confirmed on CLOUD too, ~10min/2 wraps in run 180604); and
      one-way beacons have no round trip -> L:0.00/DL:0 even on cloud. FIX: IN_GAME_BEACON=False -
      stop the one-way beacons entirely. No beacon => no A field => no 262s wrap; and the client's
      native resync runs, re-baselining cleanly and measuring real latency. We already answer the
      0x40 pings (on_pkt sz==12 & data[2]&0x80 -> build_time_reply; format verified vs FUN_10007f06:
      A@8, STATUS_INDEX@12, echoed time-index@14). New RX/TIMEPING log marks in-game resync pings.
      Also confirmed via Ghidra: the base (DAT_1001d0b0) is set ONLY by set-base (connect config),
      and the in-game dispatcher (state 2) REJECTS SYN packets (the SYN flag bit IS the reject bit),
      so a mid-session base re-anchor is impossible - the resync path is the client's intended way.
v212:
v212: NET-time - v211 core fix CONFIRMED WORKING, harmful re-anchor removed. run_192643 proved
      v211 dropped the NTP clock offset from +245.8s to +0.75s (the client's 'Base' readout) and
      the client now SLEWS small steps ('Slewed? YES') instead of hard-failing. The residual freeze
      was v211's own 180s re-anchor: the mid-session SYNACK does NOT re-run the client's set-base
      (that path is connect-only), so resetting beacon A->0 while the base stayed fixed dropped
      server_time by ~elapsed and the client slewed ~100-180s and froze mid-slew (~57s after the
      re-anchor). FIX: disable the re-anchor (NTP_REANCHOR_S huge). Beacon A now climbs as
      elapsed-since-connect with offset ~0; sessions up to the 262s A-field wrap are clean. TODO:
      the 262s wrap for longer continuous sessions still needs the correct mid-session base-update
      mechanism (2009 ran for hours, so one exists - likely tied to the in-game WORLD_TIME re-init).
v211:
v211: NET-TIME NTP FIX (found via the HUD lag readout + full vcncNet disassembly). The 2009 HUD
      showed 'L:0.19' (real lag); ours shows 'L:0.00, DL:0' - the client can't measure latency, and
      the same broken time exchange causes the freeze. Disassembled the client's NTP path
      (FUN_10007fc0 decode -> tSyncAddMeasurement offset calc @0x1000833d): the client anchors its
      clock BASE from the SYNACK fa_s:fa_frac (set-base FUN_10007cef, ONCE), reconstructs
      server_time = base + beaconA/1000 - beaconB/1000, and computes offset = ((pT2-pT1)+(pT3-pT4))/2,
      lag = (pT4-pT1)-(pT3-pT2). We sent A as an ABSOLUTE phase (v207: (unix-FA_EPOCH)ms & 0x3FFFF),
      so base+A did NOT equal server_now - it sat a constant ~246s off (the +245.8 'Base' in the
      logs), and when the 18-bit A wrapped (262.143s) in-game the client saw a 262s offset step and
      slewed to death (-261.76 'New offset' -> 'CRAP backward NET Time' -> freeze on first spawn).
      FIX: A = ms ELAPSED since a per-session base anchor (s._ntp_epoch), so base+A == server_now
      (offset ~0, real lag surfaces on the HUD), and re-anchor the base (resend SYNACK fa_s:fa_frac +
      reset epoch, A->0) every NTP_REANCHOR_S=180s < 262s so elapsed never reaches the wrap. New
      TX/REANCHOR log line marks each re-anchor. Supersedes the v205-210 phase/stamp attempts.
v210:
v210: THE NET-TIME FREEZE ROOT CAUSE - stale GAME_DEF CreationTime (found by comparing the
      client's game-clock derivation against the 2009 logs). The client seeds its clock from the
      GAME_DEF: WORLD_TIME::Init ss=CreationTimeSeconds, then each spawn Seconds = CreationTimeSeconds
      + (StartTime - CreationTime)/1000, with StartTime on the NET-ms clock our SYNACK fa_s anchors.
      In 2009 the arena's CreationTimeSeconds was contemporaneous with the session (~3 min old). OUR
      arenas are PERSISTED in the DB, so the served CreationTimeSeconds was ~7.9 DAYS stale
      (3991878344 vs connect fa_s ~3992558957, messages65). The client mixed a TODAY NET-ms clock
      with a 7.9-day-old CreationTime; the growing inconsistency is what the per-respawn time re-fit
      couldn't reconcile -> 'CRAP backward NET Time' -> freeze (the varying 262/392/544s jumps were
      the per-session staleness, never a fixed wrap). FIX: build_lz_gamedef now stamps a FRESH
      CreationTime(ms @off5)/CreationTimeSeconds(@off9) from fa_timestamp() at serve time, so every
      arena looks freshly created 'now' on the same fa_s timeline - exactly like a live host.
      Removed the v208/209 HQ-reentry SYNACK re-anchor (wrong cause). Kept v207 FA_EPOCH-phased A
      (correct) and v206 1s beacons (harmless belt-and-suspenders; 2009 tolerated long gaps).
v209:
v209: HQ re-anchor CORRECTNESS (found by comparing v208 against the 2009 host logs). The 2009
      base anchor (client 'CreationTimeSeconds') was IDENTICAL on connect (01:31) and on world
      re-entry (03:04) = 3451426175 - i.e. the NET-time base is a FIXED connect constant that the
      host replays verbatim, and the client derives elapsed time from its own clock on top of it.
      v208 re-sent build_synack() which computes a FRESH fa_s each call, so an HQ re-entry would
      have moved the base forward by the session-elapsed and jumped NET time. FIX: capture the
      connect SYNACK's (fa_s, fa_frac) on the session (s.synack_base) and REPLAY it on HQ re-entry
      via build_synack(fixed_fa=...). Also confirmed from 2009 that the client tolerates long
      dead-air (a ~48s world-load with zero inbound FA msgs did NOT freeze), so the freeze was
      never beacon-starvation - it was the phase/base anchoring (v207 + this). The 1s beacon
      cadence (v206) is kept as belt-and-suspenders but is not what 2009 relied on.
v208:
v208: HQ-REENTRY FREEZE (the remaining case after v207). v207 fixed the wrap-during-flight freeze
      - the client now flies THROUGH the 18-bit A_ms wrap during in-arena respawns (run_233934: it
      survived A_ms 261898->4757 mid-flight). The last freeze is specifically the crash -> exit-to-HQ
      -> change-plane -> re-fly path: the client tears down its world + NET-time state on the HQ
      round-trip but the server never re-anchors the client's time BASE (set only from a SYNACK).
      2009 ground truth: an HQ re-fly there produced a fresh 'Seconds=' time re-init (messages04);
      ours did not (messages64) -> stale base + post-teardown offset re-fit drifted to 'CRAP backward
      NET Time' ~40s after the re-fly (392s jump, tsBaseOffset drifting +80->+220 across sessions).
      FIX: on the HQ round-trip re-entry ONLY (detected by entered_game==False at the fly-grant),
      re-send the SYNACK base anchor + a fresh beacon so the client re-establishes NET time exactly
      as at connect. In-arena respawns (entered_game stays True) are untouched. Logged as
      TIME-REANCHOR. (Keeps v207 FA_EPOCH-phased A and v206 1s beacon cadence.)
v207:
v207: NET-TIME FREEZE - THE root-cause fix (phase alignment). v206 logging PROVED beacons flow
      at 1s and that the freeze coincides EXACTLY with the beacon A_ms field wrapping the 18-bit
      boundary (run_232813: A_ms 260529 -> 3389 on the ident=2 respawn = the 3rd re-entry the
      user saw freeze). Root cause: the client anchors its NET-time BASE from the SYNACK fa_s
      field, which is measured from FA_EPOCH (int(time.time())-FA_EPOCH), but v205/206 sent the
      beacon A field as unix-ms & 0x3FFFF. Those two have DIFFERENT zero points, off by a constant
      FA_EPOCH*1000 mod 2^18 = 121856 ms (~122s). The client computes NET time = base + A; the
      ~122s phase skew plus the 262s wrap made a respawn re-fit land on the wrong absolute second
      and snap time backward -> 'CRAP backward NET Time' -> freeze. FIX: A = (time.time()-FA_EPOCH)
      *1000 & 0x3FFFF, so A shares FA_EPOCH's zero point with the base. base + A is now correct at
      every sample and the 18-bit wrap is transparent across respawns. (v206's 1s beacon cadence
      and in-game beacon logging are kept.)
v206:
v206: NET-TIME FREEZE, likely root cause + diagnostics. run_230020 (the run that MATCHED the
      freeze test, same machine so no clock skew) logged only TWO time beacons the entire
      session - both from the connect handshake. The in-game 5s keepalive beacon had no log
      line, masking that the client got NO periodic NET-time correction while flying. The client
      holds NET time = own_clock + server_offset and re-fits the offset on each respawn; with no
      fresh beacon the 4th re-fly snapped the offset backward ~544s (client Time reverted to ~4s
      after the FIRST spawn) -> 'CRAP backward NET Time' -> freeze. FIX: beat the in-game TIME
      beacon every HEARTBEAT_INTERVAL=1s (was 5s) so the client re-anchors well inside the 18-bit
      A-field wrap (~262s), and LOG it 1-in-5 (seq + A_ms) so the next test proves the cadence and
      the values the client receives near any re-fit. Diagnostic-forward: if it still freezes, the
      beacon log will show whether beacons flow (encoding bug) or stop (thread/gating bug).
v205 (prior):
v205: NET-TIME FREEZE, real fix (reverts v204's rebase, which made it worse). The freeze is the
      client's 'CRAP!!! HUGE backward NET Time' meltdown: it anchors NET time at the SYNACK base
      and advances by the beacon's A field (dword & 0x3FFFF = 18-bit ms, A/1000 = seconds; decoded
      in vcncNet FUN_10007fc0). v202/203 sent A = (now - module_load_epoch)*1000, whose phase was
      UNRELATED to the SYNACK base (which uses fa_timestamp/FA_EPOCH); the phase mismatch surfaced
      as a ~262s backward jump each time A's 18-bit field wrapped -> freeze. v204 rebased A per
      arena entry, which only swapped the 262s wrap jump for a session-elapsed (~290-327s) jump
      (messages60) since it reset the counter mid-session. FIX: A = int(time.time()*1000) & 0x3FFFF
      - server WALL-CLOCK unix ms, low 18 bits, the SAME clock fa_timestamp() anchors the base to,
      so A and the base are phase-locked and the wrap is invisible to the client's high-order
      reconstruction. Inherently monotonic; no per-session state, no rebasing. Removed v204's
      per-session tsync_ms/tsync_rebase and the fly-grant rebase call.
v204: TWO FIXES for the exit-to-HQ -> change-plane -> re-fly freeze (messages58, AC2E_Bigalon).
      (1) NET-TIME WRAP FREEZE (the actual freeze). The beacon/time_reply A field is an 18-bit
      ms counter that WRAPS every 262.143s. The client re-bases its clock-drift regression on
      every arena (re-)entry; the wrap landed inside that fresh ~8-sample fit window on the second
      re-fly -> a ~260s BACKWARD NET-time jump ('CRAP!!! HUGE backward NET Time difference of
      260.324' in vcncnet...621.log) -> link death -> client froze at 09:28 while the time thread
      spun. FIX: the ms counter is now PER-SESSION (S.tsync_ms) with its origin RE-BASED to now on
      each arena entry (S.tsync_rebase, called from handle_fly_start_place), so it restarts near 0
      exactly when the client re-fits -> the wrap can never fall in the window. build_beacon/
      build_time_reply take the session; the module-global tsync_ms is the pre-session fallback.
      (2) msg 14 REASSIGN echo. On respawn the client sends 'out 14' (Reassign obj owner); FA has
      NO inbound in-game handler (slot 0xcbc1c8 unset), so our generic echo made it log 'Unsupported
      message 14' and corrupt its object list. 0x0e added to NO_ECHO_SUBS -> swallowed (the respawn
      CreateObject already re-binds the object on peers, so the reassign is redundant for us).
v203: REAL SCORING (msg 33 ScoreEvent) - grounded in the 2009 live-host logs (messages04).
      The kill flow there is: victim 'in 3'21' (MEC=5,EEC=3 = shot down by enemy) removes the
      plane, then the host sends the KILLER a separate 'in 33'14' ScoreEvent (MEC=1,EEC=3) that
      ticks its in-game scoreboard. Decoded FUN_004f9ad0/FUN_004f9b0f: payload
      [0x21][b1][killer PlayerIndex:u16][Type=(EEC<<4)|MEC][9B]; points are computed client-side
      from the local damage list (msg 33 is the trigger, not the amount). Added build_score_event_33
      + send_score_event_to_killer, fired from the death handler after the scored delete. Ground
      (PvE) score stays inline with the msg-36 scene-destroy ('You have destroyed X. Score:N',
      per-target value from the object-type score table). DB accumulation (db_credit_kill) unchanged.
v202: NAME TAGS + SCORE - object-record tag bit7 (0x80) = HUMAN-owned plane flag,
      decoded from FUN_004f26b0 (CreateObject dispatcher, case 1/8 PLANE, test @0x4f2714):
      bit7 SET -> lookup GamerClientScore[St] (FUN_004f2560 -> mgr@0xc822d8[St*4+0xc]) and
      bind it to the NetPlane (FUN_00427530 -> plane+0x128) = pilot name tag renders and
      kills attribute to the pilot's score. bit7 CLEAR (the pre-v202 bug) -> DRONE branch:
      plane+0x128=0, no owner binding, NO name tag, no score attribution. The score slot
      is created by the tag-0 client record leading the 83-byte first-spawn create and
      PERSISTS on the peer, so object-only re-creates with bit7 are safe as well.
      (Related, not yet wired: msg 88 AceOrRankChangedCB @0x4f4120 = [88][PlayerIndex u32]
      [b5][b6] -> client+0x50=b5, client+0x30=b6 (rank/aces for the tag) - next step.)
v201: remote plane TYPE fix - out-4 spawn byte[8] = selected plane ordinal, stored per
      session and forwarded in the msg-2 object record byte[1] (was hardcoded P-39D).
v200: PvE part 2 - SCENE-DESTROY (msg 36) builder + broadcast, and a live-validatable
      'destroy' console command. Grounded in the 2009 live-server logs (messages04): the
      real destroy loop is  out 28 (hit) + out 31 (ground-damage report) -> in 36 (server's
      authoritative SCENE DESTROY/STATE) -> client prints 'You have destroyed GER Birchwood'.
      msg 36 (0x24) handler LAB_004f9d90 decoded: wire = [0x24] then N x 7-byte records
      [sceneIdx u16 LE][camp/0xFF u8][progress f32]; camp 0xFF = neutralized/destroyed,
      progress <= 0 flips the scene to captured. It is delivered through the IN-GAME VNET
      dispatch (FUN_004f18a0) which passes the TRUE message length (not bc*16+1) - the live
      'in 36'8' = exactly one 7-byte record - so msg 36 is framed with build_ingame_pkt
      (Size == n), NOT the appspace bc*16+1 tiler.
        * build_scene_destroy_36(scene_idx, camp, progress) - the 8-byte-per-record builder.
        * broadcast_scene_36(room_id, ...) - reliable send to everyone in the room.
        * console 'destroy <sceneIdx> [camp] [progress]' - fire msg 36 at a KNOWN scene index
          (e.g. 30 = 'Bomber Airfield' on TRN02) to validate the wire format in isolation,
          with ZERO dependence on the still-unconfirmed msg-31 objidx->sceneIdx mapping.
      Per-scene HP store (SCENE_HP) + auto-destroy-on-depletion logic is implemented but
      GATED OFF (AUTO_SCENE_DESTROY=False): msg 31 reports a finer per-piece object index
      (129/130/376) whose relation to the 0-59 scene index is not yet confirmed, and sending
      msg 36 with an out-of-range sceneIdx trips the client's bounds assert. The gate stays
      off until the next live capture (v199 GROUND31 logs) pins the mapping.
v199: PvE groundwork, part 1 + 5-MINUTE SESSION-DEATH fix.
      (1) msg 31 (0x1f) = GROUND-OBJECT DAMAGE REPORT is now consumed and decoded, never
      echoed. The client has NO inbound handler for 31 (dispatch slot 0xc81f54 is set to 0
      unconditionally in FUN_004f1240), so v198's generic echo raised 'NET::MESSAGE with
      Unknown Type 31' on every strafing/bomb/crash report (messages17). Records are 6 bytes:
      [attacker ONumber u16 LE][target static-object idx u8][event u8, 0x05 seen][damage u16
      LE] - observed: strafing dmg 92..1239 on objs 129/130, bomb splash = two records in one
      msg, fuel-tank crash = obj 120 dmg 9976. Consumed in all three arrival forms (direct
      sub=0x1f, type-scan pl[8]=0x1f, compound inner). v199 logs + accumulates per-object HP
      server-side (GROUND_HP dict, no client notify yet - that's part 2).
      (2) THE 300s DEADLINE: the post-auth drain loop ran 'while time.time()<deadline' with
      deadline=login+300s, so five minutes after login the server silently stopped PROCESSING
      reliable messages (still ACKing them!) - all msg-31s of the second flight, the exit-
      appspace and the disconnect of session 01-Jul were RELRX-logged but never handled
      ('Can't exit AppSpace' / 'Can't disconnect server' client errors). Loop now runs until
      s.closing.
v198: BAIL-OUT respawn fix, part 3 (completes v196/v197). v197 kept the object NUMBER in
      lock-step by consuming one for the parachute, but did NOT advance the spawn IDENT -
      and the client's local object-registration ident advances for EVERY object it creates,
      parachute included (out-4 payloads: plane1=ident 0, parachute=ident 1, plane2=ident 2).
      The respawn's ServerConfirm therefore carried ident=1 while the fresh plane was
      registered under ident 2 -> FUN_007e5030 found no local object with ident 1 ->
      'Confirm object 258 not found in list, send delete' (messages08) -> fresh plane deleted,
      sim loop never started, dead engine. Fix: the ident is IN the client's out-4 payload
      (u16 LE right after the 0x04 msg-id: pl[5:7] direct, pl[9:11] on the type-scan
      double-wrapped re-spawn form) - parse and ECHO it instead of trusting a server-side
      counter; the counter remains only as a fallback and is resynced from the parachute's
      out-4 ident field too.
v197: BAIL-OUT respawn fix, part 2 (completes v196). v196 stopped echoing the parachute's
      msg-4 (killing the 'Unsupported message 4' error) but SWALLOWED it outright - and the
      client allocates a fresh object Number for the parachute, so the server's Number counter
      then ran one BEHIND. The next respawn's ServerConfirm carried the stale Number (259 vs the
      client's 260) -> 'Confirm object 259 not found in list -> send delete' -> fresh plane deleted,
      dead engine. Now the parachute out-4 (type=0xf2 sub=0x04) CONSUMES a Number to stay in
      lock-step with the client (still no echo, no confirm, no spawn-ident advance).
v196: BAIL-OUT respawn fix. On a bail the client spawns the parachute pilot and sends its
      object state as msg-4 wrapped type=0xf2 sub=0x04 (out 4'15). That fell through to the
      generic echo -> the client received an echoed msg-4 -> 'ERROR: Unsupported message 4',
      which CORRUPTED its object list, so the next spawn's ServerConfirm was refused ('Confirm
      object 260 not found in list -> send delete') and the fresh plane was deleted (dead engine,
      teardown). msg-4 is the client's OWN object state and must NEVER be echoed - the normal
      spawn out-4 (type=0x12) is ServerConfirmed; any other sub=0x04 is now swallowed.
v195: RESPAWN-AFTER-CRASHLAND fix, part 3 (the actual one). v193/v194 fixed the DIRECT msg-3
      death path, but the log showed the crashland delete arrives WRAPPED - outer type=0x06,
      inner sub=0x03 - which hit the type-scan 'notify -> swallow' branch and bypassed the death
      handler entirely, so obj_confirmed was never re-armed and the respawn's out 4 still got no
      ServerConfirm (Conductor error, dead engine, CTD). The in-arena own-plane-removal logic
      (drop plane + stay in arena + re-arm obj_confirmed/flying) is now a shared helper
      _ingame_own_object_removed, called from BOTH the direct tb=0x42/0x52/0x32 path and the
      wrapped scan-inner (outer 0x06) path.
v194: RESPAWN-AFTER-CRASHLAND fix, part 2 (completes v193). A crashland respawn does
      InsertPlayer + out 4 with NO fresh StartPlace (the plane is on the ground, client
      continues in place), so obj_confirmed stayed True from the prior spawn and
      _fire_server_confirm gated the out-4 out -> no ServerConfirm -> Conductor error ('Server
      sent client something it doesn't understand'), engine-start ignored, then CTD. Now the
      msg-3 death handler ALSO re-arms obj_confirmed/flying = False, so the next out 4 confirms
      a fresh object whether or not a StartPlace preceded it. (v193 kept entered_game=True so
      the out-4 handler still runs; both are required.)
v193: RESPAWN-AFTER-CRASHLAND fix - the msg-3 own-plane delete used s.flying to tell a death
      from an exit-to-HQ, but a CRASHLAND (off-runway, over-speed damage) sends no respawn
      StartPlace first, so flying stayed True and the death was mis-handled as an exit ->
      handle_leave_arena cleared entered_game / sent the 0xDA handoff and BROKE the next
      respawn (engine-start ignored, in-game base-switch gone, only a full rejoin recovered).
      Now ANY in-arena own-plane removal is treated as a death: drop the dead plane on peers
      and stay in the arena so respawns work in place. Real leave-to-lobby still comes as
      msg-64 and tears down normally.
v192: WEB ARENA SETTINGS EDITOR - '[gear] Edit Settings' button on each arena in the web /admin
      panel opens a per-arena editor (name, section-header/title, status + GAME_DEF settings).
      Wired settings so far: the 7 visual ranges (fighters/bombers/tanks/plane-tags/other-tags/
      padlock/chat) and the 2 oxygen ceilings (with/without mask), edited in feet. These live in
      the fixed 173-byte post-plane-block GAME_DEF tail (float32 metres), located per-arena via
      _gamedef_plane_block so offsets hold across arenas (verified byte-identical on TC/Nations/
      FFA). Edits are stored as {key:feet} JSON in a new rooms.settings_json column and APPLIED
      AT 212 SERVE TIME in build_lz_gamedef (in-place float writes - original blob never mutated,
      212 stays bc*16+1 aligned). Take effect on the next arena entry. Pre-block settings
      (checkboxes/dropdowns/physics/weather) are variable-offset and not yet wired.
v191: Arena-creation AUTO-JOIN fix - the CREATE flow sends no 0xc8 SendEnterToGame; the client
      drives entry off the 1-Hz 0x43 game-connect poll and waits for a JoinToGameAnswer 201 to
      clear it. We only echoed 'room confirm', so the poll never stopped -> ~15s soft timeout ->
      client exits. Now the creator's first post-create 0x43 poll grants the 201 (enter game
      mode, alloc ClientNumber/PlayerIndex, stand up player-object layer), same as the 0xc8
      path. Gated by a create-only flag; join/lobby polls untouched. (In-arena OPTIONS still
      read-only - that is FA's peer-host 'am I the arena host?' check, tracked separately.)
v190: Arena-list category grouping fix - the 0xd2 block-boundary pad was appended to the LAST
      record's name1 (the CATEGORY the client groups rows under), so a shared category split
      into a duplicate 'Dogfighting   Arenas' header. Pad now lands on name2 (display label,
      invisible), keeping every category byte-clean so same-category arenas group together.
v189: STABLE MILESTONE - 2-player flight + team changes + crash recovery.
      * Per-side plane catalog now echoed as 3-byte [planeID][ushort] records so the client's
        msg-58 reader (len-1)/3 ingests every kept plane (GE bombers no longer dropped).
      * Telemetry relay marker is size-independent (cmd==0, opcode 0x07, T&0x0f==2, scan off
        0/4) - fixes asymmetric visibility (both clients now see each other).
      * Team-change roster: broadcast on current_room (not entered_game) so switches made at
        team-select propagate; self-63 sent JOIN-only (neutral echo caused a lobby-bail loop);
        no-op dedup so reliable retransmits of the same side don't re-broadcast (flood/CTD).
      * Server crash-recovery: SIO_UDP_CONNRESET disabled on Windows (a client CTD no longer
        starves recvfrom -> reconnect gets a populated pilot/arena list without a restart);
        Linux is immune by default. Reconnect reaps the stale same-account ghost session.
      Known-rough (deferred, non-blocking): reliable-seq wrap wedge after a very long single
      segment (~250 pkts, no re-entry); exit-to-lobby re-entry reliable desync on that path.
v188: FFA neutral-team guard (camps AllianceVar collapse at serve time); GAMEDEF_DEBUG
      flag gates the per-build decompressed-hex dump (default off).

TODO list:
  [x] SYN structure mapped (offsets confirmed)
  [x] Pilot creation/rename/delete (0xe2/0xe7/0xe3) saved to DB
  [x] Ticket generation: gen <name> at server console -> ticket_<name>.vr1
  [x] Chat: broadcast as APPSPACE sub=0xcd with pilot name
  [x] Lobby UI List: 0xcc LmsChangePlayers mapped (join/leave broadcasts)
  [x] Room creation: compound cmd=18 inner type=0x92/sub=0xdc stored in DB
  [x] Room list (0xce): sends actual room data via build_ce_room_list
  [x] Room confirm (0x43): slot=room_slot player_count from DB
  [x] VNET::SendEnterToGame: bc=2 type=0x82 sub=0xc8 detected; not echoed (prevents crash)
  [x] Player-object layer (v182 -> fixed v183 -> fixed v184): msg 62 AddPlayer /
      63 ChangePlayerCB / 96 ScoreTable, decoded from VNet_Rcv.cpp (FUN_004fa5f0 /
      FUN_004fa9c0 / FUN_00629600). 62 creates REMOTE_PLAYER, 63 op=1 sets side
      (rp->Camp() @ player+0x2c). Side membership was msg 63 all along - NOT msg 58
      (v175's guess); msg 58 is a LobbyRcv list, not the arena side-setter.
      v183 FIX: v182 crashed on side-select (op=2 hit the DELETE path, not camp; and
      the 63 was sent to the player about itself). op=CAMP is 1; 63 is peers-only.
      v184 FIX: v183 crashed on arena-JOIN - it sent msg 96 (ScoreTable) on the 201
      grant, which frees+reallocates the host-side score-table object before the
      client's world exists (3s stall -> WinError 10054). 96 is now DEFERRED; the 62
      stand-up self-gates to no-ops when alone, so lone entry == known-good v182 path.
      v185: layer made REQUEST-DRIVEN. bare 0x60 after FLY grant = ScoreTable request
      -> answer msg 96 (v184 left it unanswered -> no launch timer, CTD ~20s).
      v186: INVARIANT added - 62 to client X never carries X's own index; 0x66
      swallowed; self-63 kept as the team-change mechanism.
      v187 ROOT CAUSE: every player-object CTD (v182 side-select, v183 join, v185/v186
      team) was ONE bug - the client delivers Length=bc*16+1 to handlers, NOT the
      datagram length (proven in vcncnet...510.log: our 8B msg 63 arrived as Size=17
      with 9B of stale-buffer garbage, parsed as phantom records -> ScoreTable/VNet_Rcv
      "Length>=0" fatal assert -> DLL_PROCESS_DETACH). build_appspace_pkt_exact was a
      fiction; the client ignores real length. FIX: 62/63/96 now TILE to bc*16+1 with
      parser-valid padding - 63 pads to a multiple of 16 dummy-index records, 62 pads
      the last record's unused trailing string, 96 appends one pad group (9+7N bytes).
      Also fixed a 96 count off-by-one (parser loops count+1). The v183 "premature
      world state" and v185 "use-after-free" theories were both wrong: it was framing.
  [x] LOBBY/ARENA SERVER COMPLETE (v187). Verified live: auth, pilot mgmt, rooms,
      arena list, 212 GAME_DEF, player-object layer (62/63/96), team select (chat
      line + side color), chat, the FLY StartPlace grant (msg 23). The client reaches
      the runway with a plane assigned. This is the milestone stopping point.

  -- BOUNDARY: entering the flyable world needs the GAME-SERVER CHANNEL (new work) --
  The FLY -> spawn path is NOT a packet bug. On fly, FUN_004f6320 passes the spawn
  gate (worldobj exists, -0x1700 "ready" flag set by arena entry) and calls
  FUN_004e9fa0, which invokes the SIM CONDUCTOR at worldobj+0x1800:
        (**(code**)(*(worldobj+0x1800)+0x6c))(...)   <- null-vtable CTD
  worldobj+0x1800 is null. Nothing in the lobby path (LobbyRcv.cpp / VNet_Rcv.cpp,
  incl. the 212 handler FUN_004ed9c0 which only PARSES the arena def) creates it.
  The conductor's users live in Sources\FA30\PLANES\plngroup.cpp - the flight-sim
  layer, a separate subsystem. Peer-hosted FA splits into two channels: the lobby/
  arena connection (this file) and a SEPARATE game-server VNET connection that runs
  gameplay and stands up the conductor. We don't serve that channel yet, so the
  client spawns into a sim that was never initialized -> null +0x1800.

  [ ] GAME-SERVER CHANNEL (separate VNET connection) - new design thread:
      [ ] First question: how is the client told to OPEN the 2nd connection? Trace the
          writer of worldobj+0x1800 back to its triggering network event; the connect
          address/port is likely already in something we send (201 JoinToGameAnswer
          payload, or a GAME_DEF field), since the client must learn where to dial.
      [ ] Reverse the sim-entry handshake that allocates the conductor (+0x1800).
      [ ] Then: position/state replication for actual flight.
  [ ] Multi-player (lobby): verify 62 AddPlayer on a real 2nd-player join (untested)
  [ ] Pilot stats: rank, score, kills, deaths, squadron (DB placeholders exist)
  [ ] PLANE FILTERING (deferred - "get flying" comes first):
      Current: all planes shown to all teams (DEFAULT_PLANESET=0 -> stock Planes.txt;
      msg 58 0x3a echoed in full). This is intentional for now.
      [ ] Per-arena pool (option 2, mechanism DONE/dormant): map an arena in
          ARENA_PLANESETS to a plane-set index N; REQUIRES authoring PLANES\Planes_N.txt
          into the client VFS (data.q6 ships only Planes.txt=0; v164 proved a missing
          file -> "No planes' definitions found!" abort). Open Q: can a loose
          PLANES\Planes_N.txt shadow the pack, or must it be repacked?
      [ ] Per-NATION within one arena (option 1): server replies to the client's
          'out 58'121' catalog (msg 58 / FUN_004eff50) with only the selected side's
          subset instead of echoing all. Needs: (a) decode the [byte][ushort] record
          -> plane mapping (grab US vs GE 'out 58' captures and diff), (b) a plane->nation
          table. Until then 0x3a stays echoed (the exemption in handle_post_auth/
          handle_compound keeps the hangar populated).
  [ ] Telemetry RELAY (multiplayer flight): forward each player's flight-state
      ('out 6' etc.) to OTHER players in the room (the 13/20/62 entity stream),
      never echo to the sender (sender-echo = Unknown Type crash). Currently in-game
      telemetry is swallowed (single-player stopgap).

bc formula: param_3 = bc x 16 + 1
appspace LENGTH RULE: client delivers Length = bc*16+1 to handlers, not the datagram
  length. Any length-driven message MUST tile to len == 1 (mod 16) with parser-valid
  padding. (Root cause of the v182-v186 crash series; see v187 note above.)
"""
import socket, struct, time, binascii, threading, ctypes, os, sqlite3, secrets, sys, itertools, re, json
from datetime import datetime
from collections import deque

# Force UTF-8 console output with replacement so a legacy cp1252 console can never crash a
# worker thread on a box-drawing/arrow/em-dash char in a log line (the login thread died on
# '== v187 AUTH ==' under Python 3.14's cp1252 stdout). errors='replace' degrades any
# unencodable glyph to '?' instead of raising UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HOST = "0.0.0.0"; PORT = 38999
FA_EPOCH = 0x7C558180; STATUS_INDEX = 0x1FF
HEARTBEAT_INTERVAL = 1.0   # v206: seconds between in-game keepalive/TIME beacons. Was 5s, but the
                           # client's NET-time offset drifts without a steady beacon stream (18-bit
                           # A field wraps ~262s) -> respawn re-fit snaps backward -> freeze. 1s
                           # keeps the client re-anchored well inside the wrap window.
NTP_REANCHOR_S = 999999.0   # v212: re-anchor DISABLED (set huge). v211's mid-session SYNACK
                           # re-anchor did not update the client base (set-base is connect-only), so
                           # it just reset A and dropped server_time ~elapsed -> froze mid-slew. A now
                           # climbs as elapsed-since-connect; the 262s wrap is a separate TODO. The
                           # core v211 fix (offset ~0, real lag, client slews small steps) stands.
IN_GAME_BEACON = True      # v213.1: REVERTED to True. v213's no-beacon experiment FAILED WORSE -
                           # the client does NOT self-resync via raw two-way pings in-game (the server
                           # received ZERO 12-byte data[2]&0x80 pings in run_220823). With beacons off,
                           # the client's in-game time sample went stale, it entered resync (sync
                           # state 2), sent its own pings that never reached us, got no valid reply,
                           # and after ~33 pings/~66s hit 'No response from server' -> sync state 5 ->
                           # vcncGetTimeState returns -2 -> the game spun on -2 and froze on the FIRST
                           # entry (worse than v212's 262s survival). So the one-way beacon IS load-
                           # bearing: it's the client's sole in-game time source. Back to beacons ON;
                           # the 262s wrap remains the real problem to solve via a different route.
KEEPALIVE_S = 20.0         # v213: kept for reference (unused while IN_GAME_BEACON=True).
RAW_RX_LOG = True          # v214 DIAGNOSTIC: log every raw inbound packet (addr + first 16 bytes),
                           # including packets from unknown addresses that on_pkt used to drop
                           # silently. Purpose: SEE whether the client's in-game time-sync pings
                           # arrive from an unexpected source port (which would explain why v213's
                           # no-beacon resync 'received nothing'). Verbose - turn off after diagnosis.
STATUS_PACKETS = True      # v215: send periodic 'Game Status Message' STATUS requests in-game. This
                           # is the REAL in-game time keeper (found via the session-timer-stuck-at-
                           # 0:00 clue): the client ADDs the packet's base-time increment to its NET
                           # base (FUN_10007d13), which ADVANCES the base mid-game and defeats the
                           # 262s wrap of the 18-bit A field; it also drives the System Status window
                           # (loss%, latency, SESSION TIME). Sent every STATUS_INTERVAL_S in-game.
STATUS_INTERVAL_S = 2.0    # v215: cadence of STATUS requests (base-increment = elapsed ms since last).
RTT_SAMPLING = True        # v217.2 (STEP 2): re-enable RTT sampling now that the SYNACK cap fix
                           # (v217 step 1) is confirmed stable - the RTT ring is finally bounded at 32
                           # (cfg[0x40] now correctly delivered at packet byte 88), so slot writes
                           # wrap at index 32, well before the index-64 delivery-callback slot that
                           # caused the CTD. build_rel_ack's next_exp = seq+1 lets the client's
                           # same-packet RTT lookup HIT -> a sample is taken each ACK -> the displayed
                           # latency becomes a moving average over the last 32 samples (FUN_10006f55)
                           # -> it jitters in real time like 2009 (instead of frozen at connect).
                           # This is exactly what v216 tried, but v216 crashed because the cap was
                           # never actually reaching the client (the byte-88 misalignment); with v217
                           # step 1 fixing that, sampling is now genuinely safe. Set False to instantly
                           # revert to the frozen-but-safe behavior if a CTD somehow recurs.
# Diagnostic: capture the UNRELIABLE in-game packet stream (flight telemetry) that the
# server otherwise drops. Rate-limited hex sample per session, so one flight reveals the
# entity/position format we need to relay between players. Set False to silence.
CAPTURE_UNREL = True
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fa_server.db')

TICKET_SIZE     = 2172
TICKET_AB_OFF   = 0x10
TICKET_F45_OFF  = 0x20
TICKET_PID_OFF  = 0x24
TICKET_ACCT_OFF = 0x30
TICKET_ACCT_LEN = 32

SYN_OFF_AUTH = 56; SYN_OFF_F45 = 72; SYN_OFF_PID = 76; SYN_OFF_ACCT = 88
TICKET_TEMPLATE = None

import fa_logging as _falog
_falog.init_logging(
    log_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs'),
    console_level=os.environ.get('FA_CONSOLE_LEVEL', 'INFO'),
    file_level=os.environ.get('FA_FILE_LEVEL', 'DEBUG'))
log  = _falog.log     # drop-in: same signature log(tag, msg[, level=...])
logx = _falog.logx    # log + traceback, for use inside except blocks

def hx(d, n=None): return binascii.hexlify(bytes(d) if n is None else bytes(d[:n])).decode()
def fa_timestamp():
    t = time.time()
    return ctypes.c_uint32(int(t)-FA_EPOCH).value, int((t%1)*1000*0x10000//1000)+0x800

# --- Database -----------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS accounts (
            account_name TEXT PRIMARY KEY,
            player_id    TEXT NOT NULL,
            field_45     TEXT NOT NULL DEFAULT "00000045",
            auth_block   TEXT NOT NULL DEFAULT "00000000000000000000000000000000"
        );
        CREATE TABLE IF NOT EXISTS pilots (
            pilot_name   TEXT PRIMARY KEY,
            account_name TEXT NOT NULL REFERENCES accounts(account_name),
            rank         INTEGER NOT NULL DEFAULT 0,
            score        INTEGER NOT NULL DEFAULT 0,
            kills        INTEGER NOT NULL DEFAULT 0,
            deaths       INTEGER NOT NULL DEFAULT 0,
            aces         INTEGER NOT NULL DEFAULT 0,
            squadron     TEXT    NOT NULL DEFAULT '',
            rights       INTEGER NOT NULL DEFAULT 1,
            slot_index   INTEGER NOT NULL DEFAULT 1
        );
    ''')
    # MIGRATION: CREATE TABLE IF NOT EXISTS won't add a column to a pre-existing pilots table,
    # so add `aces` explicitly if it's missing. Stored ace status is the value msg 88 puts in the
    # score object's aces field (+0x50, a u8). NOTE: the CLIENT also awards ace status live during
    # a session by its own rule (5 kills without dying, reset on death) - that's session state we
    # neither compute nor persist. This column is the pilot's PERSISTENT/career ace standing that
    # the server states authoritatively at spawn/transition.
    pcols = [r[1] for r in conn.execute("PRAGMA table_info(pilots)").fetchall()]
    if 'aces' not in pcols:
        conn.execute("ALTER TABLE pilots ADD COLUMN aces INTEGER NOT NULL DEFAULT 0")
        log('DB', 'pilots: added missing `aces` column (default 0)')
    # v240: one column per HQ Scores row. The msg-25 stat block (score+0x30) is now fully mapped
    # (see STAT25_MAP), so every row the HQ career screen renders gets its own column - which makes
    # the web admin editor a complete end-to-end test harness for the stat block.
    #    column           msg-25 field        HQ Scores row
    #    rank             f0   u8             Rank
    #    deaths           f1   u16            Lost Pilots
    #    kills_fighters   f2   u16            Kills > Fighters
    #    kills_bombers    f3   u16            Kills > Bombers
    #    planes_lost      f4   u16            Planes Lost (players)   [screen shows f4 + f13]
    #    kills            f5   u16            Kills (total)
    #    kills_in_a_row   f7   u8             Kills In A Row
    #    aces             f8   u8             Aces
    #    score            f9   FLOAT          Fighter Score
    #    bomber_score     f10  FLOAT          Bomber Score
    #    ai_fighters      f11  u16            AI Fighters
    #    ai_bombers       f12  u16            AI Bombers
    #    planes_lost_ai   f13  u16            Planes Lost to AI       [screen shows f4 + f13]
    #    ai_ships         f16  u16            Ships
    #    ai_tanks         f17  u16            Tanks
    #    ai_ground        f18  u16            Ground Units
    #    ai_buildings     f19  u16            Buildings
    for _c in ('kills_fighters', 'kills_bombers', 'planes_lost', 'planes_lost_ai',
               'kills_in_a_row', 'bomber_score', 'ai_fighters', 'ai_bombers',
               'ai_ships', 'ai_tanks', 'ai_ground', 'ai_buildings'):
        if _c not in pcols:
            conn.execute(f"ALTER TABLE pilots ADD COLUMN {_c} INTEGER NOT NULL DEFAULT 0")
            log('DB', f'pilots: added missing `{_c}` column (default 0) [msg-25 stat block]')
    conn.commit(); conn.close()

def db_upsert_account(acct, pid, f45, ab):
    conn = sqlite3.connect(DB_PATH)
    # Explicitly name the columns being inserted
    conn.execute('''INSERT INTO accounts (account_name, player_id, field_45, auth_block) VALUES(?,?,?,?)
        ON CONFLICT(account_name) DO UPDATE SET
        player_id=excluded.player_id,field_45=excluded.field_45,auth_block=excluded.auth_block''',
        (acct, pid, f45, ab))
    conn.commit(); conn.close()

def db_ensure_pilot(name, acct, slot):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO pilots(pilot_name,account_name,slot_index) VALUES(?,?,?)",
                 (name, acct, slot))
    conn.commit(); conn.close()

def db_get_account_by_pid(pid_hex):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT account_name,player_id,field_45,auth_block FROM accounts WHERE player_id=?",
                       (pid_hex.lower(),)).fetchone()
    conn.close(); return row

def db_get_all_accounts():
    conn = sqlite3.connect(DB_PATH)
    # Ensure you are explicitly selecting only these 4 columns
    rows = conn.execute("SELECT account_name, player_id, field_45, auth_block FROM accounts").fetchall()
    conn.close(); return rows

def db_get_pilots(acct):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT pilot_name,slot_index FROM pilots WHERE account_name=? ORDER BY slot_index",
                        (acct,)).fetchall()
    conn.close(); return rows

def db_delete_pilot(pilot_name, acct):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM pilots WHERE pilot_name=? AND account_name=?", (pilot_name, acct))
    conn.commit(); conn.close()

def db_rename_pilot(old_name, new_name, acct):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE pilots SET pilot_name=? WHERE pilot_name=? AND account_name=?",
                 (new_name, old_name, acct))
    conn.commit(); conn.close()

def db_get_pilot_slot(acct, name):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT slot_index FROM pilots WHERE account_name=? AND pilot_name=?",
                       (acct, name)).fetchone()
    conn.close(); return row[0] if row else None

def db_next_slot(acct):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT MAX(slot_index) FROM pilots WHERE account_name=?", (acct,)).fetchone()
    conn.close(); return (row[0] or 0) + 1

def db_credit_kill(killer_name, victim_name, points, victim_is_bomber=False, lost_to_ai=False):
    """Accumulate a combat result into persistent pilot stats (global scoring).

    v240: also maintains the columns the HQ Scores screen renders, so they stay consistent with
    kills/deaths automatically:
      killer -> kills_in_a_row +1
      victim -> deaths +1, a plane lost, kills_in_a_row reset to 0
    v242: the kill is broken down by WHAT WAS SHOT DOWN - `victim_is_bomber` picks kills_bombers vs
    kills_fighters, so "Kills > Fighters" + "Kills > Bombers" always adds up to "Kills".
    (Which SCORE the points land in is a separate question - that depends on what the KILLER was
    flying - and is handled by db_apply_score_delta(bomber=...).)
    v243: `lost_to_ai` sends the loss to planes_lost_ai (msg-25 f13, "Planes Lost to AI") instead of
    planes_lost (f4), which is where an AA/flak kill belongs. The HQ screen shows f4 + f13, so the
    total is right either way - but the breakdown is what the game actually tracks.
    Columns are added conditionally so an un-migrated DB still works.
    """
    conn = sqlite3.connect(DB_PATH)
    have = {r[1] for r in conn.execute("PRAGMA table_info(pilots)").fetchall()}
    if killer_name:
        sets, args = ['kills=kills+1', 'score=score+?'], [points]
        _kcol = 'kills_bombers' if victim_is_bomber else 'kills_fighters'
        if _kcol in have:
            sets.append(f'{_kcol}={_kcol}+1')
        if 'kills_in_a_row' in have:
            sets.append('kills_in_a_row=kills_in_a_row+1')
        args.append(killer_name)
        conn.execute(f"UPDATE pilots SET {', '.join(sets)} WHERE pilot_name=?", args)
    if victim_name:
        sets = ['deaths=deaths+1']
        _lcol = 'planes_lost_ai' if lost_to_ai else 'planes_lost'
        if _lcol in have:
            sets.append(f'{_lcol}={_lcol}+1')
        if 'kills_in_a_row' in have:
            sets.append('kills_in_a_row=0')          # dying breaks the streak
        conn.execute(f"UPDATE pilots SET {', '.join(sets)} WHERE pilot_name=?", (victim_name,))
    conn.commit(); conn.close()

def db_set_pilot_aces(name, aces):
    """v222: SET the pilot's ace status to an absolute value (not additive).

    Ace status is SERVER-AUTHORITATIVE and lives in the DB, which is the single source of truth the
    admin editor writes and msg 88 states to the client. FA's rule is a LIVE one - ACE_KILLS_PER
    (5) kills WITHOUT dying earns an ace, and DYING WIPES YOUR ACES - so this is called with 0 on
    death and with the incremented value when a kill completes a 5-kill streak.
    """
    if not name:
        return
    aces = min(max(int(aces), 0), 255)   # msg-88 aces field is a u8 (score obj +0x50)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE pilots SET aces=? WHERE pilot_name=?", (aces, name))
    conn.commit(); conn.close()

def db_get_pilot_stats(name):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT score,kills,deaths FROM pilots WHERE pilot_name=?",
                       (name,)).fetchone()
    conn.close(); return row   # (score,kills,deaths) or None

def db_get_pilot_career(name):
    """The pilot's PERSISTENT career stats for the in-game scoreboard.
    Returns (score, kills, deaths, rank, aces) - defaults to zeros for an unknown pilot.

    These are the AUTHORITATIVE values the server pushes to the client (msg 88 for aces/rank).
    `aces` is now STORED (v221) rather than derived from kills: FA's live ace status is a CLIENT-side
    session rule (5 kills without dying, reset on death) which the server must not try to compute -
    so the DB holds the pilot's persistent/career ace standing, which we state authoritatively.
    A team change or room change must NOT reset a pilot's real standing - it is RE-READ from the DB
    and re-pushed, so the career numbers survive the transition.
    """
    conn = sqlite3.connect(DB_PATH)
    pcols = [r[1] for r in conn.execute("PRAGMA table_info(pilots)").fetchall()]
    acol = 'aces' if 'aces' in pcols else '0'
    row = conn.execute(f"SELECT score,kills,deaths,rank,{acol} FROM pilots WHERE pilot_name=?",
                       (name,)).fetchone()
    conn.close()
    if not row:
        return (0, 0, 0, 0, 0)
    return (row[0] or 0, row[1] or 0, row[2] or 0, row[3] or 0, row[4] or 0)

def pilot_aces(kills):
    """v219: derive the ACE count from career kills. FA's 'ace' status is a kill milestone; the
    score object's aces field (score+0x50, set only by msg 88) is a small u8 counter. Until the
    exact 2009 rule is confirmed, use the classic threshold: 5 kills = 1 ace 'star', i.e. aces =
    kills // 5, clamped to a byte. Adjust ACE_KILLS_PER if the real rule turns out different."""
    return min(max(int(kills) // ACE_KILLS_PER, 0), 255) if ACE_KILLS_PER > 0 else 0


# --- Terrain table & GAME_DEF terrain extraction ------------------------------
#
# FA identifies each arena's map by a TERRAIN NUMBER (1..99, sparse). The number
# is asserted >=1 (FUN_00438e30 / Trn.hpp:437) and must exist in the client's
# locally-loaded set, or the engine aborts the moment the Arenas tab renders it.
# Each room's terrain is chosen by the creator and travels inside the GAME_DEF
# text blob the client sends at creation, as a "Terrain=N" key/value line - the
# same field the client prints when it parses a GAME_DEF. We extract it there,
# store it per-room, and emit it in the 0xd2 record. Names below are the FA stock
# set (from the production + client logs) and are only used for console display.
TERRAIN_NAMES = {
    1: 'Ocean', 2: 'Mediterrain', 3: 'Two Islands', 4: 'Germany', 5: 'Circle',
    6: 'English Channel', 7: 'Bowl', 8: 'Kursk', 9: 'Canyon', 10: 'Guadalcanal',
    11: 'North Africa', 12: 'Midway', 13: 'Big Circle', 14: 'Mountains',
    15: 'Volcano', 16: 'North Cape', 17: 'Western Desert', 19: 'Solomon Islands',
    22: 'Two Islands II', 23: 'Western Desert II', 24: 'Pacific Island', 29: 'NAW',
    30: 'Desert NAW', 38: 'Classic_II', 39: 'KOTS Arena', 45: 'Five Towers',
    48: 'MKOTS Arena', 49: 'Terra Nova', 50: 'Classic_III', 51: 'Classic_III_Snow',
    60: 'Korea', 61: 'Korea Snow',
}
DEFAULT_TERRAIN = 1   # Ocean - present in every stock install; safe fallback
FORCE_GAMEDEF_TERRAIN = 6  # English Channel - terrain to stamp into client-created
                           # GAME_DEFs that store terrain=0 (the user's TC rooms are
                           # English Channel; client loaded terrain 06 at startup)

# -- Per-arena PLANE SET (option 2: GAME_DEF word[0x23] -> PLANES\Planes_<N>.txt) --
# FA's plane POOL for an arena is selected by GAME_DEF word[0x23] (the first ushort
# after the camps block). The client feeds it to FUN_004c7cd0 which loads
#   word[0x23]==0  ->  PLANES\Planes.txt   (the full stock list - every plane, all nations)
#   word[0x23]==N  ->  PLANES\Planes_<N>.txt
# This is PER-ARENA (one value per room, same for everyone in it), NOT per-nation.
# WARNING (the v164 lesson): a nonzero N only works if PLANES\Planes_<N>.txt actually
# EXISTS in data.q6, else the client aborts at load with 'No planes' definitions found!'
# (Pln_Info.cpp:93). Stock data ships only Planes.txt (N=0). So this stays 0 unless a
# SPECIAL ARENA ships its own Planes_<N>.txt. Map arena name/creator (case-insensitive)
# to its plane-set index here; anything absent resolves to DEFAULT_PLANESET.
DEFAULT_PLANESET = 0
ARENA_PLANESETS = {
    # 'pacific theater': 7,   # example: requires PLANES\Planes_7.txt present in data.q6
}
# -- Per-arena GROUND START (StartGround flag in the GAME_DEF) ------------------
# The client spawns in the AIR (OnGround=0, at StartAlt) when the arena's StartGround
# flag is 0, and on the RUNWAY (OnGround=1) when it is 1. CONFIRMED via FA.exe:
#   * deserializer FUN_0057bee0 reads it as a single byte into arena+0xec (param[0x3b]),
#     positioned EXACTLY ONE BYTE after the terrain byte (param[0x39]/+0xe4);
#   * printer FUN_005796e0 prints arena+0xec as " StartGround=%s" (yes/no);
#   * AllowTerrainChange (arena+0xe8) is a separate packed flag bit far later in the
#     struct, so flipping this byte affects ONLY the spawn, nothing else.
# StartAirfield maps side->forced field; the user's rooms use -1 (no force) for all real
# sides, so the granted start place (AF from the FLY 23 grant) is used as-is - ground
# start needs no StartAirfield change. We stamp StartGround=1 into every served GAME_DEF.
FORCE_GROUND_START = False  # reverted 2026-06-28: serve each arena's GAME_DEF untouched; use a native ground-start arena. Set True to re-enable the StartGround rewrite.
GAMEDEF_DEBUG = False  # v188: gate the per-212-build decompressed-hex dump. Set True to re-enable when diffing GAME_DEF fields.

def planeset_for_room(room):
    """Resolve the plane-set index for a room (room[1]=name, room[2]=creator).
    Default DEFAULT_PLANESET (0 = stock Planes.txt). Override per special arena via
    ARENA_PLANESETS. Returns 0 on any error so the safe default is never bypassed."""
    try:
        name    = (room[1] or '') if len(room) > 1 else ''
        creator = (room[2] or '') if len(room) > 2 else ''
        for key, idx in ARENA_PLANESETS.items():
            k = key.lower()
            if k == name.lower() or k == creator.lower():
                return int(idx)
    except Exception:
        pass
    return DEFAULT_PLANESET

# --- FFA neutral-team guard ------------------------------------------------------------
# FFA vs TC is decided by the camps-block AllianceVar (leading cstring of the camps block;
# parsed by FA.exe FUN_0056ed90 -> FUN_0056e990, Camps.cpp). The ACTIVE-CAMP MASK
# (camps+0x60) is built from which hex DIGITS appear in the string (not the dashes); Neutral
# (camp 7) is ALWAYS force-added. KEY CONSTRAINT (found v188 via live test + server log):
# Neutral has NO aircraft, so the in-arena side picker will not let you fly it -- a
# Neutral-ONLY arena left the picker with nothing flyable and it fell back to US. So instead
# we keep ONE real, flyable camp active (FFA_FLYABLE_CAMP, default 0 = US slot, which has
# planes and is the picker default) plus the forced Neutral, and relabel BOTH name groups to
# "Neutral". Result: a 2-column all-Neutral arena the player can actually fly in (they join
# the flyable camp and show as Neutral). Verified against live rooms (round-trip, p-ptr==len,
# bc*16+1). NOTE: relabeling is display-only; flyability is gated by plane availability /
# camp index, not the label string, so camp 0 stays flyable even when shown as "Neutral".
def is_ffa_room(room):
    """True if the room is a Free-For-All arena (by NAME or web-editable CATEGORY)."""
    try:
        name = (room[1] or '') if len(room) > 1 else ''
        cat  = (room[8] if len(room) > 8 and room[8] else '')
        return 'free for all' in name.lower() or 'free for all' in cat.lower()
    except Exception:
        return False

def _camp_mask_from_av(av):
    """Active-camp mask the client's FUN_0056e990 computes from an AllianceVar: each hex
    digit sets its camp bit; Neutral (7) is always forced active. (An empty string would
    make the client activate ALL camps, so callers must never produce one.)"""
    mask = 0
    for ch in av:
        c = chr(ch).upper()
        if '0' <= c <= '9':   mask |= 1 << (ord(c) - 48)
        elif 'A' <= c <= 'F': mask |= 1 << (10 + ord(c) - 65)
    return (mask | 0x80) & 0xff

def _split_camp_groups(after_av, ngroups):
    """Split the post-AllianceVar camps bytes into ngroups groups of 4 NUL-terminated
    cstrings (code, abbrev, fullname, extra). Returns (groups, consumed_bytes)."""
    pos = 0; groups = []
    for _ in range(ngroups):
        start = pos
        for _f in range(4):
            pos = after_av.index(0, pos) + 1
        groups.append(bytes(after_av[start:pos]))
    return groups, pos

# Which real (flyable) camp index the (now-disabled) FFA camps rewrite would keep active.
FFA_FLYABLE_CAMP = 0

# FFA camps rewrite is DISABLED (v188, after live testing). Two findings killed it:
#  (1) The client's camp table is GLOBAL and last-write-wins. At lobby time the server
#      pushes a 212 GAME_DEF for EVERY room and the client parses each into one shared camp
#      table; the FFA room is parsed LAST, so its reduced camps ({0,7}) overwrote the table
#      for ALL arenas -> every other room showed only camp 0 selectable, 1-4 greyed.
#      Entering a room does not re-parse, so there is no per-room isolation to exploit.
#  (2) FFA is not 'one Neutral team' at all -- the arena's own Comment reads 'no teams just
#      you against everyone else'. Stock FFA legitimately lists all nations in the side
#      picker (you choose your aircraft's nation); the free-for-all (everyone hostile,
#      no teams) comes from the camps FFA flag that '01234' already sets. So the original
#      served camps were correct and need no rewrite. Leave this False; serve camps as-is.
FFA_NEUTRAL_GUARD = False

def force_ffa_two_col(d, flyable_camp=FFA_FLYABLE_CAMP):
    """Rewrite the camps block so the FFA arena has exactly the flyable camp (default 0)
    plus the always-forced Neutral camp (7) active, with BOTH name groups relabeled to the
    real Neutral cstrings. Mutates `d` in place and fixes block_len (d[13]). The player
    joins the flyable camp (picker default, has planes) and is shown as Neutral; the result
    is the 2-column all-Neutral layout. The strict Camps.cpp p-ptr==len assert still holds
    (we recompute the active mask exactly as the client does and emit one group per active
    bit). Returns (changed, info)."""
    try:
        block_len = d[13]
        camps = bytes(d[14:14 + block_len])
        av_end = camps.index(0)
        av = camps[:av_end]
        mask = _camp_mask_from_av(av)
        active = [i for i in range(8) if mask & (1 << i)]
        groups, consumed = _split_camp_groups(camps[av_end + 1:], len(active))
        if (av_end + 1) + consumed != block_len:     # must match the client's parser exactly
            return False, 'camps parse mismatch'
        if 7 not in active:
            return False, 'no Neutral camp'
        neutral = groups[active.index(7)]            # reuse the real Neutral cstrings (NU/NEU/Neutral)
        new_av = bytes(str(flyable_camp), 'ascii')   # e.g. b'0'
        if av == new_av:
            return False, 'already collapsed'
        new_mask = _camp_mask_from_av(new_av)        # {flyable_camp, 7}
        new_active = [i for i in range(8) if new_mask & (1 << i)]
        new_camps = new_av + b'\x00' + neutral * len(new_active)   # one Neutral group per active bit
        d[14:14 + block_len] = new_camps
        d[13] = len(new_camps)
        return True, {'old_av': av, 'new_av': new_av, 'active': new_active,
                      'old_block_len': block_len, 'new_block_len': len(new_camps)}
    except (ValueError, IndexError) as e:
        return False, f'error: {e}'

def extract_terrain_from_gamedef(game_def_raw):
    """Terrain = param[0x39] of the decompressed GAME_DEF (= arena_object+0xe4).

    CONFIRMED three ways: (1) contrast rooms - Territorial Combat/Mediterranean reads 2,
    MKOTS reads 48, matching FA's terrain table exactly; (2) FA.exe FUN_00702a40 reads the
    dialog terrain from arena+0xe4; (3) FUN_0076e690 / FUN_0076d6c0 validate arena+0xe4 via
    FUN_00438e30 (the _TrnNumber>=1 assert). It is the byte immediately after the 8 camp/
    team dwords. Layout from the version byte:
      [0]ver | [1:13]3 dwords | [13]block_len | camps(block_len) | [.]3 ushorts |
      NAME\\0 | COMMENT\\0 | PASSWORD\\0 | [.]Type | LobbyType\\0 | [.]2 ushorts |
      [.]8 dwords(32B) | [.]param[0x39]=TERRAIN
    Returns 1..99 or DEFAULT_TERRAIN.
    """
    if not game_def_raw:
        return DEFAULT_TERRAIN
    try:
        d = decompress_gamedef(game_def_raw)
        if not d or len(d) < 14:
            return DEFAULT_TERRAIN
        block_len = d[13]
        p = 20 + block_len                       # NAME start (ver+3dw+blen+camps+3ushort)
        for _ in range(3):                       # skip NAME, COMMENT, PASSWORD
            p = d.index(0, p) + 1
        p += 1                                   # param[0x2a] Type byte
        p = d.index(0, p) + 1                    # LobbyType string
        p += 4                                   # param[0x2f], param[0x30] ushorts
        p += 32                                  # 8 dwords param[0x31..0x38] (camp/team idx)
        t = d[p]                                 # param[0x39] = terrain
        if 1 <= t <= 99:
            return t
    except Exception:
        pass
    return DEFAULT_TERRAIN

def gamedef_startground_offset(d):
    """Byte offset of the StartGround flag within a DECOMPRESSED GAME_DEF struct `d`.
    It sits exactly ONE byte after the terrain byte (param[0x39]) - the same walk
    extract_terrain_from_gamedef uses to reach terrain, then +1. Returns None on any
    parse failure (caller then leaves the struct untouched)."""
    try:
        if not d or len(d) < 14:
            return None
        block_len = d[13]
        p = 20 + block_len
        for _ in range(3):                       # NAME, COMMENT, PASSWORD
            p = d.index(0, p) + 1
        p += 1                                   # Type byte
        p = d.index(0, p) + 1                    # LobbyType string
        p += 4                                   # 2 ushorts
        p += 32                                  # 8 dwords
        sg = p + 1                               # terrain byte is at p; StartGround is p+1
        if 0 <= sg < len(d):
            return sg
    except (ValueError, IndexError):
        pass
    return None

# -- Per-team AIRCRAFT assignment (which nation flies each plane) ----------------
# WHY: every stored GAME_DEF leaves all 121 planes with record BYTE 0 = 0x1f. That byte is
# PLANE.field[0], the CAMP BITMASK the flyability gate FUN_00438330 checks:
#     flyable(plane, camp) = field[0] & (1<<camp).   0x1f = bits 0..4 = all 5 camps may fly
# every plane (no per-nation restriction at all). FIX (apply_plane_teams): rewrite byte 0 to
# (1<<camp) so each plane admits ONLY its team; the wrong-nation planes then grey out per
# side. The record stays the 4-byte [mask][0xff][lim][lim] form.
# NOT the earlier 6-byte [attr][camp+0x7d][0][0][lim][lim] form: that set PLANE.hascamp,
# which (a) never touched byte 0 so it never actually filtered, and (b) put the plane into
# the client's camp-RESTRICTED hangar display -> the bogus 'max N / used N' line. (The side
# PICKER's camp enablement is a separate thing entirely: camp-active from airfields/camps,
# not plane records.)
#
# EVENTS / MIX-AND-MATCH: to move a plane to another team just edit the lists below. Anything
# not listed (incl. every US type) stays on camp 0 (USA). For a one-off event arena with a
# custom roster, add ROOM_PLANE_TEAMS[<room_id>] = {camp:[names], ...}; it overrides the
# global table for that room only. Camps: 0=USA 1=GB 2=USSR 3=Germany 4=Japan.
# Re-enabled 2026-06-29: build_lz_gamedef now emits a REAL LZ-compressed stream (fa_compress)
# instead of all-literals, which shrinks even teamed GAME_DEFs far under the client's per-packet
# MTU (TC 1585B -> 801B), so the oversized-packet stall that emptied the arena list is gone.
PLANE_TEAMS_ENABLED = True

# FILTER MECHANISM (2026-06-30). Two ways to make each side see only its own aircraft:
#   True  (catalog echo): leave every plane flyable by ALL camps in the GAME_DEF
#         (byte0 = 0x1f) and instead trim the per-side plane list the server ECHOES back on
#         the client's 0x3a catalog upload. The client's OWN flyable set never changes with
#         side, so switching teams stays a lightweight in-place swap and does NOT drop into
#         the leave/teardown path that wedges the HQ menu. This is the FA "option 1".
#   False (flyability gate): set byte0 = (1<<camp) so FUN_00438330 greys wrong-nation planes.
#         Correct teams + clean display, BUT the per-side flyable LIST shrinks/empties on a
#         side change, forcing the heavy leave/re-entry flow -> HQ menu hang.
# Flip to False to fall straight back to the byte0 build if the filtered echo doesn't take.
PLANE_FILTER_VIA_CATALOG = True
# The client's msg-58 DOWNLOAD decoder FUN_004eff50 (LobbyRcv.cpp:0x209) parses (Size-1)/3
# records of 3 BYTES each: [planeID:1][ushort LE:2]. The UPLOAD is flat 1-byte ids, but the
# ECHO must be 3-byte records or the count is read as (Size-1)/3 of garbage (1-byte GE echo
# Size=27 -> only 8 planes, dropping the bombers at the tail). Visibility is driven by planeID
# membership in the list (hangar consumer FUN_006de570 gates on the GAME_DEF plane-info array,
# not this ushort), so the ushort is ancillary; 0 is safe. Bump if planes show greyed.
CATALOG_RECORD_USHORT = 0

# Stock FA 4.20 plane roster in GAME_DEF SLOT/ID order (slot = list index = the plane ID the
# GAME_DEF plane block is keyed by). The serve-time rewrite is keyed by slot; this maps
# slot->name so the team tables below can read by name.
# CORRECTED 2026-06-30: the prior list was in the client's HANGAR DISPLAY order, not slot
# order, so name->slot put camp bits on the wrong planes (Germany showed allied bombers).
# Rebuilt into true ID order via the msg-58 catalog, which maps display-position->plane-ID.
# ID 107 is the only plane the client omits from its catalog (the L2D2 transport) -> never
# shown; placed here for completeness.
PLANE_ROSTER = [
    "F4F-3","P-39D","P-40C","P-40E-1","F4F-4","F4U-1a","P-38G","F6F-3","P-47D","F4U-1c",
    "P-51D","P-38L","F4U-4","Hurr-Ia","Spit-Ia","Spit-Vb_LF","Hurr-IIC","Spit-Vb_F","Typhoon","Spit-IXc",
    "Seafire","Spit-IXe","Spit-XIV","Tempest","I-16","LaGG-3","Hurr-IIb","Kittyhawk-Ia","Yak-1b","P-39Q",
    "La-5FN","Yak-3","Yak-9U","La-7","Bf-109E-4/B","Bf-109F-4/B","FW-190A-4/U3","FW-190A-8/R6","FW-190A-8/R3","Bf-109G-6/R2",
    "FW-190A-8/R2","Bf-109G-6/R6","FW-190D-9","Me-262A-1","Bf-109K-4","Ta-152H-1","HA-200","A6M2","Ki-44-IIc37","A6M5a",
    "Ki-61","J2M3","N1K2-J","Ki-84-1a","A6M7","Ki-100","B-25D","TBF-1c","A-20Gu","B-17G",
    "Dauntless","Mosquito_B_IV","Avenger_II","DB-7B","Mosquito_FB_VI","Mitchell_III","Pe-8","Pe-2","IL-2","A-20Gs",
    "Tu-2","Tu-4","Ju-88","Do-217E-2","He-111","Do-217J-1","Ju-87G-2","D3A","G5N1","G4M2",
    "Ju-87D-3","MiG-3","J9Y","C-47A","Dakota_Mk.II","Li-2","Ju-52/3m","Mosquito_B_IX",'Mosquito_"Tse-Tse"',"Mitchell_II",
    "B-29","Martlet_I","Ki-44-IIc","Ki-43-IIa","Tomahawk","Kittyhawk","Hurr-IID","Yak-9UT","Bf-109E-1/B","Ki-84-1c",
    "FW-190F-8","F4U-4C","Bf-110C-4","Bf-110G-2","SBD-2","Lancaster","B5N2","L2D2","Ki-67","MiG-15bis",
    "F-86E","Meteor_F1","Tunnan","Ouragan","B-25J","IL-10","MiG-9","DH.100","Me-163B","FH-1_Phantom",
    "Pulqui",
]

# Historical default. Edit freely for events; unlisted planes -> USA (camp 0).
# -- v242: AIRCRAFT CLASS (fighter vs bomber) ----------------------------------
# FA splits the scoreboard two ways, and they key off DIFFERENT aircraft:
#     Fighter Score / Bomber Score   -> what YOU were FLYING when you earned the points
#     Kills > Fighters / > Bombers   -> what you SHOT DOWN
# The server already knows both: s.plane_type is the PLANE_ROSTER id straight out of the spawn
# packet (out-4 byte[8]), so a kill can be attributed to the right pair of columns.
# Ids below are indices into PLANE_ROSTER. Bombers/attackers/transports cluster in blocks (56-80,
# 83-90, 104-108) with a few stragglers. EDIT FREELY - this is a judgement call on the borderline
# airframes and is meant to be tuned, not treated as gospel:
#   * Included as BOMBERS: level/dive/torpedo bombers, dedicated attackers (IL-2, IL-10, Ju-87,
#     FW-190F-8) and transports (C-47, Dakota, Li-2, Ju-52, L2D2).
#   * Left as FIGHTERS: fighter-bombers on fighter airframes (Bf-109 /B variants, Hurr-IID,
#     Typhoon) and heavy fighters (Bf-110).
# Anything not listed is a FIGHTER.
BOMBER_PLANE_NAMES = {
    # level / dive / torpedo bombers
    "B-25D", "B-25J", "TBF-1c", "A-20Gu", "A-20Gs", "B-17G", "B-29", "Dauntless", "SBD-2",
    "Mosquito_B_IV", "Mosquito_B_IX", "Mosquito_FB_VI", 'Mosquito_"Tse-Tse"',
    "Avenger_II", "DB-7B", "Mitchell_II", "Mitchell_III", "Lancaster",
    "Pe-8", "Pe-2", "Tu-2", "Tu-4",
    "Ju-88", "Do-217E-2", "Do-217J-1", "He-111",
    "D3A", "G5N1", "G4M2", "B5N2", "Ki-67",
    # dedicated ground-attack
    "IL-2", "IL-10", "Ju-87D-3", "Ju-87G-2", "FW-190F-8",
    # transports
    "C-47A", "Dakota_Mk.II", "Li-2", "Ju-52/3m", "L2D2",
}
# Resolve names -> PLANE_ROSTER ids once at import. Deriving from names (rather than hard-coding
# numbers) keeps this correct if the roster is ever reordered, and makes a typo obvious: any name
# that doesn't resolve is logged at startup instead of silently classing a bomber as a fighter.
BOMBER_PLANE_IDS = {i for i, n in enumerate(PLANE_ROSTER) if n in BOMBER_PLANE_NAMES}
_unmatched = BOMBER_PLANE_NAMES - set(PLANE_ROSTER)

def is_bomber_plane(plane_id):
    """v242: True if this PLANE_ROSTER id is a bomber / attacker / transport.
    Used twice per kill: the KILLER's aircraft picks Fighter Score vs Bomber Score, and the
    VICTIM's picks Kills>Fighters vs Kills>Bombers."""
    try:
        return int(plane_id) in BOMBER_PLANE_IDS
    except (TypeError, ValueError):
        return False

PLANE_TEAMS = {
    1: [  # Great Britain
        "Hurr-Ia","Spit-Ia","Martlet_I","Tomahawk","Hurr-IIC","Spit-Vb_F","Hurr-IID","Kittyhawk",
        "Spit-Vb_LF","Seafire","Spit-IXc","Spit-IXe","Typhoon","Spit-XIV","Tempest","Meteor_F1",
        "DH.100","Ouragan","Tunnan","Mosquito_B_IV","Lancaster","Mitchell_II","Avenger_II","DB-7B",
        "Mosquito_FB_VI",'Mosquito_"Tse-Tse"',"Mitchell_III","Mosquito_B_IX","Dakota_Mk.II",
    ],
    2: [  # USSR
        "I-16","MiG-3","LaGG-3","Hurr-IIb","Kittyhawk-Ia","Yak-1b","P-39Q","La-5FN","Yak-3",
        "Yak-9U","La-7","Yak-9UT","MiG-9","MiG-15bis","Pe-8","Pe-2","IL-2","A-20Gs","Tu-2",
        "IL-10","Tu-4","Li-2",
    ],
    3: [  # Germany
        "Bf-109E-1/B","Bf-109E-4/B","Bf-110C-4","Bf-109F-4/B","FW-190A-4/U3","Bf-110G-2",
        "Bf-109G-6/R2","FW-190A-8/R6","FW-190F-8","FW-190A-8/R3","Bf-109G-6/R6","FW-190A-8/R2",
        "FW-190D-9","Me-262A-1","Bf-109K-4","Ta-152H-1","Me-163B","Pulqui","HA-200","Ju-88",
        "Do-217E-2","Ju-87D-3","He-111","Do-217J-1","Ju-87G-2","Ju-52/3m",
    ],
    4: [  # Japan
        "A6M2","Ki-43-IIa","Ki-44-IIc","Ki-44-IIc37","A6M5a","Ki-61","J2M3","N1K2-J","Ki-84-1a",
        "Ki-84-1c","A6M7","Ki-100","D3A","B5N2","G5N1","G4M2","Ki-67","J9Y","L2D2",
    ],
}

# Optional per-room override: {room_id: {camp:[names], ...}}. Falls back to PLANE_TEAMS.
ROOM_PLANE_TEAMS = {}

def _slot_camp_map(teams):
    """{camp:[names]} -> {slot:camp} against PLANE_ROSTER. Unlisted slots -> 0 (USA)."""
    name_camp = {}
    for camp, names in teams.items():
        for nm in names:
            name_camp[nm] = camp
    return {i: name_camp.get(nm, 0) for i, nm in enumerate(PLANE_ROSTER)}

def plane_camp_for_room(room):
    """slot->camp map for this room (per-room override else global), or None if disabled."""
    if not PLANE_TEAMS_ENABLED:
        return None
    teams = ROOM_PLANE_TEAMS.get(room[0], PLANE_TEAMS) if room else PLANE_TEAMS
    return _slot_camp_map(teams)

def _session_slot_camp(s):
    """slot->camp map for the session's current room (per-room override else global table).
    Used by the 0x3a catalog-echo filter to keep only the player's current side's plane IDs."""
    rid = getattr(s, 'current_room', None)
    teams = ROOM_PLANE_TEAMS.get(rid, PLANE_TEAMS) if rid is not None else PLANE_TEAMS
    return _slot_camp_map(teams)

def _gamedef_plane_block(d):
    """Locate the plane block in a DECOMPRESSED GAME_DEF: returns (start, count, blen) where
    d[start]=count, d[start+1:start+3]=u16 block_len, d[start+3:start+3+blen]=records. Anchored
    on the same walk extract_terrain_from_gamedef uses (to the terrain byte), then scans for the
    count/length-prefixed record list that consumes exactly. Stock rooms store every plane in the
    4-byte [attr][0xff][lim][lim] form (blen == 4*(count+1)); that exact signature is required so
    we never lock onto a look-alike region. Returns None if not found."""
    try:
        block_len = d[13]
        p = 20 + block_len
        for _ in range(3):
            p = d.index(0, p) + 1
        p += 1
        p = d.index(0, p) + 1
        p += 4 + 32                              # 2 ushorts + 8 dwords; terrain byte at p
        for s in range(p, len(d) - 3):
            count = d[s]
            if count == 0 or count > 128:
                continue
            blen = struct.unpack_from('<H', d, s + 1)[0]
            if blen != 4 * (count + 1) or s + 3 + blen > len(d):
                continue
            rec = d[s + 3:s + 3 + blen]
            if all(rec[i + 1] == 0xff for i in range(0, blen, 4)):
                return s, count, blen
    except (ValueError, IndexError):
        pass
    return None

def apply_plane_teams(d, slot_camp):
    """Rewrite the plane block of bytearray `d` in place so each plane is flyable ONLY by
    its assigned nation. The flyability gate is FA.exe FUN_00438330:
        flyable(plane, camp) = PLANE.field[0] & (1 << camp)
    where PLANE.field[0] is record BYTE 0 (stock 0x1f = bits 0..4 = all 5 camps). We set
    byte 0 to (1<<camp) so a plane admits only its team; the record STAYS the 4-byte
    [mask][0xff][l1][l2] no-nation form (marker 0xff, both limit bytes preserved).
    WHY this and not the 6-byte [attr][camp+0x7d][..] form: that form set PLANE.hascamp,
    which (a) never touched byte 0 so it never actually filtered, and (b) dropped the plane
    into the client's camp-RESTRICTED hangar display -> the bogus 'max/used' line. Byte-0
    masking greys wrong-nation planes through FUN_00438330 with NO hascamp (no 'max/used')
    and does not grow the block (no MTU pressure). Returns (start, blen, blen) or None."""
    loc = _gamedef_plane_block(d)
    if not loc:
        return None
    s, count, blen = loc
    rec = bytearray(d[s + 3:s + 3 + blen])
    for slot in range(count + 1):
        if PLANE_FILTER_VIA_CATALOG:
            rec[slot * 4] = 0x1f                  # all camps flyable; per-side filter is the 0x3a echo
        else:
            camp = slot_camp.get(slot, 0) & 7
            rec[slot * 4] = 1 << camp             # byte0 = camp bitmask (US=0x01 ... JP=0x10)
        # marker rec[+1] stays 0xff (no-hascamp form); limits rec[+2],rec[+3] preserved
    d[s + 3:s + 3 + blen] = rec
    return s, blen, blen

# --- Binary GAME_DEF layout (from FA.exe FUN_0057bee0 / FUN_0056ed90) ----------
#
# The GAME_DEF is NOT text - it's a packed binary struct. The "Terrain=N" lines we
# used to grep are FA.exe PRETTY-PRINTING its parsed struct, not the wire format.
# The stored blob carries a 14-byte prefix (LobbyIndex/flags, zero for a new room)
# BEFORE the deserialisable GAME_DEF, whose first byte is the VERSION 0x8a (138).
# The deserialiser (FUN_0057bee0) requires byte[0]==0x8a, then reads:
#   version(1) | 3 dwords(12) | block_len(1) | camps-block(block_len) | 3 ushorts(6)
#   | NAME (null-term) | ... | Comment | ... many scalar/string/array fields ...
# FUN_0056ed90 (camps) asserts it consumes EXACTLY block_len bytes (Camps.cpp p-ptr==len),
# so NAME starts at  gamedef_start + 1+12+1 + block_len + 6  =  gamedef_start+20+block_len.
# --- FA Mix LZ codec (vcncNet/FA.exe FUN_007d68f0) ----------------------------
# The GAME_DEF carried by the 212 message is LZ-COMPRESSED. The decompressor reads
# exactly `size` input bytes and produces a variable-size output; the deserialiser's
# end assert (GameDef.cpp:2076 "Source.End()") requires it to consume the WHOLE
# decompressed buffer. Echoing the client's compressed blob fails because its size
# (740 ==4 mod16) can't land on the bc*16+1 appspace grid, so the client over-reads 8
# stale bytes that decompress into extra output -> Source.End.
#
# Fix: DECOMPRESS the stored blob, then re-send it via the decompressor's STORED mode
# (first byte 0x01 -> copies size-4 bytes verbatim). We pad a string field so the
# decompressed size ==8 mod16, which makes [0xd4][id:4][0x01][3][struct] land EXACTLY
# on bc*16+1 (payload = D+9). Validated against db_id=24: 732 compressed -> 1183 bytes,
# clean camps/name/comment.
_NEG_1A1 = -0x1a1
def _fa_hash(b0, b1, b2):
    v = ((((b0 << 4) ^ b1) << 4) ^ b2) & 0xffffffff
    prod = (v * _NEG_1A1) & 0xffffffff
    if prod & 0x80000000:
        prod -= 0x100000000
    return (prod >> 4) & 0x1ff

def fa_decompress(data, size=None):
    """Reimplementation of FUN_007d68f0. data[0]==0x01 -> STORED (copy data[4:size]);
    else LZ. Returns the decompressed bytes."""
    data = bytes(data)
    if size is None:
        size = len(data)
    if size < 4:
        raise ValueError('compressed input too small')
    if data[0] == 0x01:
        return data[4:size]
    # FA's decompressor (FUN_007d68f0) pre-initialises EVERY dictionary slot to point at
    # the 18-byte constant "123456789012345678", so a MATCH emitted before that slot was
    # populated by literals copies from THAT string - not from output offset 0. Model it
    # as an 18-byte PREFIX on the output buffer with all dict slots = offset 0; the real
    # output is out[18:]. Without this, a blob whose early op is such a match (the trn5
    # 'Circle' GAME_DEF) decompresses to garbage -> client GAME_DEF parser over-read CTD.
    out = bytearray(b"123456789012345678")
    dict_pos = [0] * 4096       # every slot points at the init string (offset 0 in `out`)
    ring = 0
    lit_run = 0
    ctrl = 1
    ip = 4                       # skip 4-byte header
    end = size
    while ip < end:
        if ctrl == 1:
            if ip + 1 >= end:
                break
            ctrl = data[ip] | 0x10000 | (data[ip + 1] << 8)
            ip += 2
        nops = 1 if (end - 0x20) < ip else 16
        for _ in range(nops):
            if ip >= end:
                break
            if (ctrl & 1) == 0:                      # LITERAL
                out.append(data[ip]); ip += 1
                lit_run += 1
                if lit_run == 3:
                    p = len(out) - 1
                    slot = (ring + _fa_hash(out[p-2], out[p-1], out[p]) * 8) & 0xfff
                    dict_pos[slot] = p - 2
                    lit_run = 2
                    ring = (ring + 1) & 7
            else:                                    # MATCH
                if ip + 1 >= end:
                    ip = end; break
                b0 = data[ip]; b1 = data[ip + 1]; ip += 2
                hi = (b0 & 0xf0) << 4
                src = dict_pos[(hi | b1) & 0xfff]
                n = 3 + (b0 & 0xf)
                for k in range(n):
                    out.append(out[src + k])
                start = len(out) - n
                if lit_run == 0:
                    dict_pos[((hi | (b1 & 0xfffffff8)) + ring) & 0xfff] = start
                else:
                    s = start - lit_run
                    slot = (ring + _fa_hash(out[s], out[s+1], out[s+2]) * 8) & 0xfff
                    dict_pos[slot] = s
                    ring = (ring + 1) & 7
                    if lit_run == 2:
                        slot = (ring + _fa_hash(out[s+1], out[s+2], out[s+3]) * 8) & 0xfff
                        dict_pos[slot] = s + 1
                        ring = (ring + 1) & 7
                    lit_run = 0
                    dict_pos[((hi | (b1 & 0xfffffff8)) + ring) & 0xfff] = start
                ring = (ring + 1) & 7
            ctrl >>= 1
            if ctrl == 1:
                break
    return bytes(out[18:])   # strip the 18-byte dictionary-init prefix

def _lz_comp_size(n):
    """Size of the all-literals LZ stream for an n-byte struct:
    4-byte header + one 2-byte control word per 16 literals + n literal bytes."""
    return 4 + 2 * ((n + 15) // 16) + n

def encode_all_literals(struct):
    """Encode `struct` as a valid FA LZ stream using ONLY literals: a 4-byte header
    (mode byte 0x00 = LZ, NOT 0x01/STORED) followed by [ctrl=0x0000][<=16 literal bytes]
    groups. ctrl=0x0000 -> the decompressor reads 16 literal bits (each copies 1 byte),
    so the stream decompresses to `struct` verbatim (no matches -> dictionary unused).
    We use this instead of STORED mode: FUN_007d68f0's 0x01 branch reads from the
    (uninitialised) output buffer, yielding a garbage version byte (v161: 'get 64')."""
    out = bytearray([0x00, 0x00, 0x00, 0x00])
    i = 0
    while i < len(struct):
        out += b'\x00\x00'
        out += struct[i:i + 16]
        i += 16
    return bytes(out)

def fa_compress(d, flo=-1, fhi=-1):
    """Encode `d` as a real FA LZ stream (the inverse of fa_decompress): literals plus 3-18
    byte dictionary matches, emitted by CO-SIMULATING the decompressor's exact dictionary
    state (18-byte init prefix, hash/ring/lit_run, slot writes) so every match resolves to the
    correct source at decode time. Repetitive GAME_DEFs (the plane block especially) shrink
    dramatically vs encode_all_literals, keeping the 212 payload under the client's MTU.
    Positions in [flo,fhi) are forced to literals (byte-granular alignment padding: a run of
    spaces would otherwise collapse to one fixed-size match and never move the size residue).
    The caller MUST verify the result via fa_decompress before serving."""
    d = bytes(d)
    out = bytearray(b"123456789012345678")     # decompressor's dictionary-init prefix
    dict_pos = [0] * 4096; ring = 0; lit_run = 0
    content_map = {}                            # 3-byte content -> {slots currently holding it}
    slot_content = {}                           # slot -> its indexed 3-byte content
    def set_slot(slot, pos):
        old = slot_content.get(slot)
        if old is not None:
            s = content_map.get(old)
            if s is not None: s.discard(slot)
        dict_pos[slot] = pos; c = bytes(out[pos:pos + 3])
        if len(c) == 3:
            content_map.setdefault(c, set()).add(slot); slot_content[slot] = c
        else:
            slot_content.pop(slot, None)
    ops = []; q = 0; N = len(d)
    while q < N:
        best_n = 0; best_slot = -1; best_src = -1
        if not (flo <= q < fhi) and q + 3 <= N:
            cand = content_map.get(d[q:q + 3])
            if cand:
                for S in cand:
                    src = dict_pos[S]; n = 0; lim = min(18, N - q)
                    while n < lim:
                        pos = src + n
                        pb = out[pos] if pos < len(out) else d[q + (pos - len(out))]
                        if pb != d[q + n]: break
                        n += 1
                    if n > best_n: best_n = n; best_slot = S; best_src = src
                    if best_n == lim: break
        if best_n >= 3:
            S = best_slot; n = best_n; src = best_src
            b0 = (((S >> 8) & 0xf) << 4) | (n - 3); b1 = S & 0xff; hi = (b0 & 0xf0) << 4
            for k in range(n): out.append(out[src + k])
            start = len(out) - n
            if lit_run == 0:
                set_slot(((hi | (b1 & 0xfffffff8)) + ring) & 0xfff, start)
            else:
                s = start - lit_run
                set_slot((ring + _fa_hash(out[s], out[s + 1], out[s + 2]) * 8) & 0xfff, s); ring = (ring + 1) & 7
                if lit_run == 2:
                    set_slot((ring + _fa_hash(out[s + 1], out[s + 2], out[s + 3]) * 8) & 0xfff, s + 1); ring = (ring + 1) & 7
                lit_run = 0
                set_slot(((hi | (b1 & 0xfffffff8)) + ring) & 0xfff, start)
            ring = (ring + 1) & 7; ops.append((1, b0, b1)); q += n
        else:
            ch = d[q]; out.append(ch); q += 1; lit_run += 1
            if lit_run == 3:
                p = len(out) - 1
                set_slot((ring + _fa_hash(out[p - 2], out[p - 1], out[p]) * 8) & 0xfff, p - 2)
                lit_run = 2; ring = (ring + 1) & 7
            ops.append((0, ch))
    # serialize: 4-byte header (byte0=0x00 => LZ mode) + groups of 16 ops, each preceded by its
    # 2-byte control word (bit set = match, LSB = first op of the group).
    s = bytearray([0, 0, 0, 0]); i = 0
    while i < len(ops):
        grp = ops[i:i + 16]; ctrl = 0
        for j, op in enumerate(grp):
            if op[0] == 1: ctrl |= (1 << j)
        s.append(ctrl & 0xff); s.append((ctrl >> 8) & 0xff)
        for op in grp:
            if op[0] == 0: s.append(op[1])
            else: s.append(op[1]); s.append(op[2])
        i += 16
    return bytes(s)

# -- EDITABLE ARENA SETTINGS (post-block GAME_DEF tail) --------------------------
# The 173-byte region AFTER the plane-team block is a FIXED-layout struct (verified
# byte-identical across TC / Nations at war / Free For All except the actual values).
# It is located per-arena via _gamedef_plane_block(d) -> block_end = start + blen, so
# these offsets are robust across arenas even though absolute offsets shift with the
# variable name/hash before the block. Each field is a float32 in METRES; the game UI
# shows/edits them in FEET, so we convert on read/write. Verified against the in-arena
# OPTIONS screenshots (13000 m = 42651 ft fighters, 4876 m = 15997 ft no-mask ceiling,
# 9296 m = 30499 ft mask ceiling) and read-tested on all three live arenas.
_M2FT = 3.280839895
ARENA_TAIL_FIELDS = [
    # key,             delta, label
    ('vr_fighters',     31, 'Visual range - fighters (ft)'),
    ('vr_bombers',      27, 'Visual range - bombers (ft)'),
    ('vr_tanks',        39, 'Visual range - tanks (ft)'),
    ('vr_plane_tags',   43, 'Visual range - plane tags (ft)'),
    ('vr_other_tags',   47, 'Visual range - other tags (ft)'),
    ('vr_padlock',      51, 'Visual range - padlock (ft)'),
    ('vr_chat',         63, 'Chat range (ft)'),
    ('height_no_mask',  90, 'Oxygen ceiling - without mask (ft)'),
    ('height_mask',     94, 'Oxygen ceiling - with mask (ft)'),
]

def _arena_tail_base(d):
    """Offset of the post-block settings tail in a DECOMPRESSED GAME_DEF, or None.
    Anchored to the plane-team block so it is correct for any arena."""
    try:
        start, cnt, blen = _gamedef_plane_block(d)
    except Exception:
        return None
    if start is None:
        return None
    return start + blen

def arena_settings_read(blob):
    """Read the editable post-block settings from a stored (compressed) GAME_DEF blob.
    Returns {key: value_in_feet(int)}; empty dict if the blob can't be parsed."""
    d = decompress_gamedef(blob)
    if not d:
        return {}
    bend = _arena_tail_base(d)
    if bend is None:
        return {}
    out = {}
    for key, delta, _label in ARENA_TAIL_FIELDS:
        off = bend + delta
        if off + 4 <= len(d):
            try:
                m = struct.unpack_from('<f', d, off)[0]
                if m == m:                       # not NaN
                    out[key] = int(round(m * _M2FT))
            except Exception:
                pass
    return out

def arena_settings_apply(d, settings):
    """In-place patch the post-block settings of a DECOMPRESSED GAME_DEF bytearray from a
    {key: feet} override dict. Each patch is a same-length float32 write, so it never
    shifts the struct or the 212 pad alignment. No-op for missing/blank keys."""
    if not settings:
        return
    bend = _arena_tail_base(d)
    if bend is None:
        return
    for key, delta, _label in ARENA_TAIL_FIELDS:
        v = settings.get(key)
        if v is None or v == '':
            continue
        off = bend + delta
        if off + 4 <= len(d):
            try:
                struct.pack_into('<f', d, off, float(v) / _M2FT)   # feet -> metres
            except (ValueError, TypeError):
                pass

# --- EvP: enemy anti-aircraft / flak (client-side, driven by GAME_DEF AA quality) ---------
# EvP flak is simulated CLIENT-SIDE: the AA batteries loaded with the terrain fire at the
# player when the arena's GAME_DEF sets the [AI] quality fields non-zero. The stock TC.gdf /
# FFA.gdf templates ship these at 0, so the guns are inert; the 2009 live arenas used
# AAquality=6, FlakQuality=1, BomberGunnerQuality=3, ShipAAQuality=1, TankAAQuality=1 and the
# world actively shot players ("GER Anti-Aircraft has damaged your fuselage"). We restore that
# by patching the 5 AA-quality bytes at 212-serve time - no protocol work, no new message.
#
# Field order + wire position CONFIRMED by decompiling the GAME_DEF parser FUN_0057bee0:
# the client reads AAquality from struct byte +0x418 (== dword field param_1[0x106]), and the
# 5 quality fields are 5 CONSECUTIVE single bytes on the wire. _gamedef_aa_offset replays the
# parser's variable-length walk to find them for any arena/terrain.
EVP_AA_ENABLED = True             # EvP is now always on; per-arena AA/Flak come from the web
                                  # settings (the `evp` console command still forces/overrides).
EVP_AA_QUALITY = (6, 1, 3, 1, 1)  # AAquality, FlakQuality, BomberGunnerQuality, ShipAA, TankAA
                                  # - the DEFAULT when an arena has no web-set AA/Flak sliders.

# The 5 web slider keys (0..6 each) that map 1:1 onto the AA-quality bytes, in wire order.
# Stored per-arena in rooms.settings_json and read at 212-serve time. Missing keys fall back
# to the corresponding EVP_AA_QUALITY default so old arenas behave exactly as before.
EVP_AA_SETTING_KEYS = ('aa_quality', 'flak_quality', 'bomber_gunner', 'ship_aa', 'tank_aa')

def evp_quality_from_settings(arena_settings):
    """Return the 5-tuple of AA-quality bytes for an arena, taking each value from the web
    slider (arena_settings[key], clamped 0..6) when present, else the EVP_AA_QUALITY default."""
    vals = list(EVP_AA_QUALITY)
    if isinstance(arena_settings, dict):
        for i, key in enumerate(EVP_AA_SETTING_KEYS):
            if key in arena_settings:
                try:
                    vals[i] = max(0, min(6, int(arena_settings[key])))
                except (ValueError, TypeError):
                    pass
    return tuple(vals)

def _gamedef_aa_offset(d):
    """Offset of the 5 consecutive AA-quality bytes in a DECOMPRESSED GAME_DEF, or None.
    Replays FUN_0057bee0's field walk up to param_1[0x106] (byte +0x418 = AAquality)."""
    try:
        n = len(d)
        p = 0
        if n < 1 or d[p] != 0x8a:
            return None
        p += 1
        def adv(k):
            nonlocal p
            p += k
            if p > n:
                raise ValueError('overrun')
        def cstr():
            nonlocal p
            while p < n and d[p] != 0:
                p += 1
            p += 1
            if p > n:
                raise ValueError('overrun')
        adv(4); adv(4); adv(4)               # 3 dwords param_1[0..2]
        blen = d[p]; adv(1); adv(blen)       # len byte + variable blob (FUN_0056ed90)
        adv(2); adv(2); adv(2)               # words 0x23,0x24,0x25
        cstr(); cstr(); cstr()               # 3 cstrings
        adv(1)                               # byte 0x2a
        cstr()                               # cstring
        adv(2); adv(2)                       # words 0x2f,0x30
        adv(0x20)                            # 0x20 block 0x31..38
        adv(1)                               # byte 0x39 TERRAIN
        adv(1)                               # byte 0x3b
        adv(4)                               # dword 0x3c
        adv(0x24)                            # 0x24 block 0x3d..45
        adv(1); adv(1); adv(1); adv(1); adv(1)          # bytes 0x47..0x4b
        cstr()                               # cstring5
        adv(1); adv(1); adv(2); adv(1); adv(1)          # 0x57,0x58,word 0x59,0x5a,0x5b
        adv(2); adv(4); adv(4); adv(4); adv(4)          # word 0x5c, dwords 0x5d..60
        cstr(); cstr()                       # cstring6,7
        adv(1); adv(1); adv(2); adv(2)       # 0x63,0x64,word 0x65,word 0x66
        adv(1); adv(1); adv(1); adv(1)       # 0x75,0x77,0x78,0x7a
        adv(1); adv(1); adv(1); adv(1); adv(1); adv(1)              # 0xf2..0xf7
        adv(1); adv(1); adv(1); adv(1); adv(1); adv(1); adv(1)      # 0xfb..0x101
        if p + 5 > n:
            return None
        return p                             # param_1[0x106] = AAquality
    except Exception:
        return None

def apply_aa_quality(d, values=EVP_AA_QUALITY):
    """In-place set the 5 AA-quality bytes in a DECOMPRESSED GAME_DEF. Same-length byte
    writes (no struct shift). SAFETY: only patches if the located bytes currently look like
    AA quality (all 0..10); otherwise no-ops so a parser desync can never corrupt the blob.
    Returns (offset, old_values) on success, None on no-op."""
    off = _gamedef_aa_offset(d)
    if off is None:
        return None
    old = list(d[off:off + 5])
    if not all(0 <= x <= 10 for x in old):     # doesn't look like the AA block - refuse
        return None
    for i, v in enumerate(values[:5]):
        d[off + i] = max(0, min(255, int(v)))
    return off, old

def build_lz_gamedef(blob, planeset=0, force_ffa=False, plane_camp=None, arena_settings=None):
    """Decompress the stored (LZ) GAME_DEF, pad a string field so the re-encoded
    all-literals stream lands EXACTLY on bc*16+1 (payload = 5 + comp_size(N') == 1 mod16),
    then re-encode. Returns (compressed_bytes, decompressed_size, pad) or (None,0,0)."""
    b = bytes(blob)
    v = gamedef_start(b)
    if not b or b[v] != 0x8a:
        return None, 0, 0
    comp = b[v - 6:]                 # compressed stream begins 6 bytes before the 0x8a
    if len(comp) < 4:
        return None, 0, 0
    try:
        d = bytearray(fa_decompress(comp, len(comp)))
    except Exception as e:
        log('GAMEDEF212', f'decompress failed: {e}')
        return None, 0, 0
    if not d or d[0] != 0x8a:
        log('GAMEDEF212', f'decompressed version=0x{(d[0] if d else 0):02x} (expected 0x8a)')
        return None, 0, 0
    # v210: FRESH CREATION-TIME STAMP - the real fix for the 'CRAP backward NET Time' freeze.
    # The GAME_DEF carries CreationTime (LE u32 ms @offset 5) and CreationTimeSeconds (LE u32 s
    # @offset 9). The client seeds its game clock as WORLD_TIME::Init ss=CreationTimeSeconds, then
    # every spawn computes Seconds = CreationTimeSeconds + (StartTime - CreationTime)/1000 where
    # StartTime runs on the NET-ms clock our SYNACK fa_s anchors. For that to stay consistent the
    # GAME_DEF's creation time MUST lie on the SAME live timeline as fa_s - which it did in 2009
    # (messages04: the arena's CreationTimeSeconds was contemporaneous, ~3 min before the session).
    # OUR arenas are PERSISTED in the DB, so the stored CreationTimeSeconds was ~7.9 DAYS stale
    # (3991878344 vs a connect fa_s of ~3992558957). The client mixed a TODAY NET-ms clock with a
    # 7.9-day-old CreationTime; the growing inconsistency is what the client's per-respawn time
    # re-fit eventually couldn't reconcile -> the backward-NET-time jump -> freeze (varying jump
    # sizes across sessions = the per-session stale-ness). fa_timestamp() already returns exactly
    # this pair on the fa_s/FA_EPOCH timeline, so stamp it in so every served arena looks freshly
    # created 'now', matching a live host. (Supersedes the v208/209 SYNACK re-anchor guesswork.)
    _ct_s, _ct_frac = fa_timestamp()
    # CreationTime(ms) = CreationTimeSeconds*1000 + fractional-ms, on the same fa_s timeline.
    # fa_frac encodes the sub-second as (t%1)*0x10000 + 0x800, so ms_frac = (fa_frac-0x800)/0x10000*1000.
    _ct_ms = (_ct_s * 1000 + int((_ct_frac - 0x800) / 0x10000 * 1000)) & 0xFFFFFFFF
    if len(d) >= 13:
        struct.pack_into('<I', d, 5, _ct_ms)     # CreationTime  (ms)
        struct.pack_into('<I', d, 9, _ct_s)      # CreationTimeSeconds
    # FFA neutral-team guard: for Free-For-All rooms, rewrite the camps block to a 2-column
    # all-Neutral set (one flyable camp + forced Neutral, both labeled "Neutral") so the
    # side picker / 213 Nations box / roster show Neutral AND the player can still fly
    # (Neutral itself has no planes; the flyable camp does). Runs BEFORE pad alignment /
    # plane-set patch so d[13] and the word[0x23] offset (14+d[13]) stay consistent.
    if force_ffa:
        changed, info = force_ffa_two_col(d)
        if changed:
            log('GAMEDEF212', f"FFA guard: camps -> 2-col Neutral "
                              f"(AllianceVar {info['old_av']!r} -> {info['new_av']!r}, "
                              f"active camps {info['active']}, "
                              f"block_len {info['old_block_len']} -> {info['new_block_len']})")
        elif info != 'already collapsed':
            log('GAMEDEF212', f'FFA guard: camps unchanged ({info})')
    # v166 DEBUG: dump the pristine decompressed GAME_DEF struct so a terrain-contrast
    # room (Ocean=1 vs English Channel=6) can be diffed field-by-field to pin the terrain
    # byte. Harmless; remove once the terrain field is located.
    if GAMEDEF_DEBUG:
        log('GAMEDEF212', f'decompressed hex ({len(d)}B): {bytes(d).hex()}')
    # v165: CORRECTION - the ushort at 14+camps_block_len (param_1[0x23]) is NOT the
    # terrain. It is the PLANE-SET id: FUN_0057bee0 feeds it straight to FUN_004c7cd0,
    # which loads "PLANES\Planes_%d.txt" (or "Planes.txt" when 0). v164 stamped 6 here,
    # so the client tried to load the nonexistent "Planes_6.txt" and aborted with
    # "No planes' definitions found!" (Pln_Info.cpp:93). 0 => default Planes.txt, which
    # the real 2009 session also used (it loaded SPIT/B17 fine). So we LEAVE 0x23 alone.
    #
    # The real terrain field lives at desc+0x1c of the 0xd2 arena descriptor and is the
    # value FUN_00438e30(N) asserts (N>=1, Trn.hpp:437). Full traces of FUN_0057bee0 (the
    # GAME_DEF deserializer) and FUN_004efda0 (the 0xd2 list parser) show NEITHER message
    # carries it: the deserializer parses to an exact Source.End() with no terrain field,
    # and the list parser reads only GameIndex(+4)+2 names, skipping the 12-byte header.
    # desc+0x1c is therefore set from FUN_004ed040's param_8 (source still being pinned),
    # not from anything we currently send. Patching the blob cannot fix it - see notes
    # below. We do NOT touch the plane-set ushort here.
    # OPT-IN per-arena plane set (option 2): stamp the plane-set id into word[0x23]
    # (first ushort after the camps block, at +14+block_len) so the client loads
    # PLANES\Planes_<planeset>.txt. planeset==0 leaves the stock selector untouched
    # (default, current behaviour). NONZERO REQUIRES PLANES\Planes_<planeset>.txt to
    # exist in data.q6 or the client aborts 'No planes' definitions found!' (v164 lesson).
    if planeset:
        try:
            ps_off = 14 + d[13]                 # word[0x23] = first ushort after camps
            struct.pack_into('<H', d, ps_off, planeset & 0xFFFF)
            log('GAMEDEF212', f"plane-set word[0x23] @+{ps_off} = {planeset} "
                              f"(client loads PLANES\\Planes_{planeset}.txt; must exist in data.q6)")
        except Exception as e:
            log('GAMEDEF212', f'plane-set patch failed ({e}); leaving word[0x23] as-is')
    # GROUND START: rewrite the StartGround byte (terrain+1) so the client spawns on the
    # runway (OnGround=1) instead of in the air. Single byte, isolated from every other
    # field (confirmed in FA.exe FUN_0057bee0/FUN_005796e0). No-op if already 1 or if the
    # offset can't be resolved.
    if FORCE_GROUND_START:
        sg = gamedef_startground_offset(d)
        if sg is not None:
            old = d[sg]
            if old != 1:
                d[sg] = 1
                log('GAMEDEF212', f'StartGround @+{sg} {old} -> 1 (runway spawn)')
        else:
            log('GAMEDEF212', 'StartGround offset unresolved; leaving spawn as-is')
    # PER-TEAM PLANES: rewrite each plane's nation marker so every active camp owns aircraft
    # (else all planes default to camp 0/USA and GB/SU/GE/JP grey out in the side picker).
    # Runs after the camps/plane-set/StartGround patches (their offsets precede the plane
    # block) and before pad alignment so the pad accounts for the grown block.
    if plane_camp:
        pinfo = apply_plane_teams(d, plane_camp)
        if pinfo:
            ps, ob, nb = pinfo
            c = {}
            for v in plane_camp.values():
                c[v] = c.get(v, 0) + 1
            log('GAMEDEF212', f"plane-teams @+{ps}: block {ob}->{nb}B  "
                              f"US={c.get(0,0)} GB={c.get(1,0)} SU={c.get(2,0)} "
                              f"GE={c.get(3,0)} JP={c.get(4,0)}")
        else:
            log('GAMEDEF212', 'plane-teams: plane block not located; planes left on USA')
    # WEB-EDITED SETTINGS: patch the post-block tail (visual ranges, oxygen ceilings) from the
    # per-room override dict. In-place float32 writes, so no struct shift / pad-alignment change.
    if arena_settings:
        arena_settings_apply(d, arena_settings)
    # EvP: enable client-side enemy flak by setting the [AI] AA-quality bytes non-zero.
    # Per-arena AA/Flak come from the web sliders (arena_settings), falling back to the
    # EVP_AA_QUALITY defaults for any slider not set. In-place same-length byte writes.
    if EVP_AA_ENABLED:
        _q = evp_quality_from_settings(arena_settings)
        _aa = apply_aa_quality(d, _q)
        if _aa:
            _off, _old = _aa
            log('GAMEDEF212', f'EvP AA quality @+{_off}: {_old} -> {list(_q)} '
                              f'(AAquality/Flak/BomberGunner/ShipAA/TankAA)')
        else:
            log('GAMEDEF212', 'EvP AA: quality bytes not located/verified; left as-is')
    D_orig = len(d)
    # REAL-LZ encode with bc*16+1 alignment. Real compression keeps even teamed GAME_DEFs far
    # under the client's per-packet MTU ceiling (the all-literals encoder INFLATES the struct
    # and overflowed it -> the oversized 212 stalled the in-order reliable channel -> the 0xd2
    # arena list queued behind it never arrived -> empty lobby). There is no closed-form size,
    # so we pad the COMMENT and recompress until 5+len(comp) == 1 (mod 16); the pad bytes are
    # FORCED to literals (flo..fhi) so each adds exactly one byte (a run of spaces would else
    # collapse to one fixed-size match and never move the residue). The chosen stream is
    # round-trip verified before use; any miss falls back to the all-literals encoder.
    try:
        p = 1 + 12
        block_len = d[p]; p += 1
        p += block_len + 6
        name_end = d.index(0, p)
        comment_end = d.index(0, name_end + 1)
    except (ValueError, IndexError):
        comment_end = None
    if comment_end is not None:
        for pad in range(0, 48):
            dp = bytes(d[:comment_end]) + b' ' * pad + bytes(d[comment_end:])
            comp = fa_compress(dp, comment_end, comment_end + pad)
            if (5 + len(comp)) % 16 == 1:
                if fa_decompress(comp, len(comp)) == dp:
                    return comp, len(dp), pad
                log('GAMEDEF212', f'real-LZ round-trip mismatch at pad={pad}; using all-literals')
                break
        else:
            log('GAMEDEF212', 'real-LZ could not align within 48; using all-literals')
    # FALLBACK: all-literals encoder with closed-form pad (original behaviour).
    pad = 0
    while (5 + _lz_comp_size(D_orig + pad)) % 16 != 1:
        pad += 1
        if pad > 64:
            log('GAMEDEF212', 'could not align (pad>64)')
            return None, 0, 0
    if pad:
        # insert `pad` spaces before the COMMENT's null terminator (cosmetic, the parser
        # reads it null-terminated). Falls back to the NAME terminator if parsing fails.
        try:
            p = 1 + 12
            block_len = d[p]; p += 1
            p += block_len + 6
            name_end = d.index(0, p)
            comment_end = d.index(0, name_end + 1)
            d[comment_end:comment_end] = b' ' * pad
        except (ValueError, IndexError) as e:
            log('GAMEDEF212', f'comment-pad failed ({e}); padding NAME')
            try:
                name_end = d.index(0, 13 + 1 + d[13] + 6)
                d[name_end:name_end] = b' ' * pad
            except Exception:
                return None, 0, 0
    return encode_all_literals(bytes(d)), D_orig, pad

def decompress_gamedef(blob):
    """Return the decompressed GAME_DEF struct (starts with version 0x8a) from a stored
    blob, or None. The stored blob is LZ-compressed beginning 6 bytes before the 0x8a."""
    try:
        b = bytes(blob)
        if not b:
            return None
        v = gamedef_start(b)
        if b[v] != 0x8a:
            return None
        d = fa_decompress(b[v - 6:], len(b) - (v - 6))
        return d if d and d[0] == 0x8a else None
    except Exception:
        return None

def gamedef_start(blob):
    """Offset of the GAME_DEF VERSION byte (0x8a) within the stored blob.
    Used for NAME extraction (fields are positioned relative to the version)."""
    if not blob:
        return 0
    b = bytes(blob)
    i = b.find(0x8a)
    return i if i >= 0 else 0

def gamedef_212_start(blob):
    """Offset where the 212 GAME_DEF must BEGIN = 6 bytes before the 0x8a version.
    The deserialiser (FUN_0057bee0) consumes a 6-byte GAME_DEF header (FUN_007cc610 +
    a 1-byte advance) BEFORE reading the version, so the stream we push must include
    those 6 bytes. Proven empirically: v158 started at the 0x8a and the client read
    version blob[ver+6]=0x90 ('get 144'); starting at ver-6 lands the 0x8a where the
    deserialiser looks. It also makes [0xd4][id:4][gdef] land exactly on bc*16+1
    (e.g. 5+732=737), so no pad/over-read. Blob layout:
      [8-byte outer prefix][6-byte gd header][0x8a version][body...]"""
    v = gamedef_start(blob)
    return max(0, v - 6)

def extract_name_from_gamedef(game_def_raw):
    """Room NAME from the DECOMPRESSED GAME_DEF (the stored blob is LZ-compressed, so the
    raw bytes look mangled e.g. 'TerHorial C'; decompressing yields the real name). Name
    sits at struct offset 20+block_len (version+3dwords+block_len byte+camps+3 ushorts)."""
    if not game_def_raw:
        return ''
    try:
        d = decompress_gamedef(game_def_raw)
        if not d or len(d) < 14:
            return ''
        block_len = d[13]
        off = 20 + block_len
        if off >= len(d):
            return ''
        end = d.find(0, off)
        if end < 0:
            end = len(d)
        raw = d[off:end]
        name = ''.join(chr(c) for c in raw if 0x20 <= c <= 0x7e).strip()
        return name[:31]
    except Exception:
        return ''

# --- Room DB ------------------------------------------------------------------

def init_rooms_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS rooms (
            room_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            room_name     TEXT    NOT NULL DEFAULT 'Unnamed',
            creator_pilot TEXT    NOT NULL DEFAULT '',
            account_name  TEXT    NOT NULL DEFAULT '',
            room_slot     INTEGER NOT NULL DEFAULT 35,
            game_def_raw  BLOB,
            terrain       INTEGER NOT NULL DEFAULT 1,
            status        TEXT    NOT NULL DEFAULT 'open',
            created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS room_players (
            room_id      INTEGER NOT NULL,
            pilot_name   TEXT    NOT NULL,
            account_name TEXT    NOT NULL DEFAULT '',
            joined_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (room_id, pilot_name)
        );
    ''')
    # Migration: add room_slot if DB was created before this column was introduced
    try:
        conn.execute("ALTER TABLE rooms ADD COLUMN room_slot INTEGER DEFAULT 35")
        conn.commit()
        log('DB', 'Migration: added room_slot column to rooms table')
    except Exception:
        pass  # column already exists - expected on every normal startup
    # Migration: add terrain column + backfill from each room's stored GAME_DEF text.
    try:
        conn.execute("ALTER TABLE rooms ADD COLUMN terrain INTEGER DEFAULT 1")
        conn.commit()
        log('DB', 'Migration: added terrain column to rooms table')
        for rid, gdef in conn.execute("SELECT room_id, game_def_raw FROM rooms").fetchall():
            t = extract_terrain_from_gamedef(gdef)
            conn.execute("UPDATE rooms SET terrain=? WHERE room_id=?", (t, rid))
        conn.commit()
        log('DB', 'Migration: backfilled terrain from stored GAME_DEFs')
    except Exception:
        pass  # column already exists - expected on every normal startup
    # Migration: add the arena-list SECTION HEADER / category (name1) column. Editable
    # from the web admin Arena Management panel; default 'Custom Arenas' = the value
    # build_arenalist hardcoded before this was made per-room.
    try:
        conn.execute("ALTER TABLE rooms ADD COLUMN category TEXT NOT NULL DEFAULT 'Custom Arenas'")
        conn.commit()
        log('DB', 'Migration: added category column to rooms table')
    except Exception:
        pass  # column already exists - expected on every normal startup
    # Migration: add settings_json - per-room web-edited GAME_DEF setting overrides (visual
    # ranges, oxygen ceilings, ...). Stored as JSON {key: feet}; applied at 212 serve time in
    # build_lz_gamedef so the original game_def_raw blob is never mutated/recompressed on save.
    try:
        conn.execute("ALTER TABLE rooms ADD COLUMN settings_json TEXT NOT NULL DEFAULT '{}'")
        conn.commit()
        log('DB', 'Migration: added settings_json column to rooms table')
    except Exception:
        pass  # column already exists - expected on every normal startup
    # Always re-derive room_name from the binary GAME_DEF (the old text-regex path
    # left every room 'Unnamed' since the blob is binary, not INI text). Cheap, and
    # corrects rooms created before binary name extraction existed.
    try:
        fixed = 0
        for rid, gdef, cur_name in conn.execute(
                "SELECT room_id, game_def_raw, room_name FROM rooms WHERE status='open'").fetchall():
            nm = extract_name_from_gamedef(gdef)
            if nm and nm != cur_name:
                conn.execute("UPDATE rooms SET room_name=? WHERE room_id=?", (nm, rid))
                fixed += 1
        if fixed:
            conn.commit()
            log('DB', f'Migration: re-derived room_name for {fixed} room(s) from binary GAME_DEF')
    except Exception as e:
        log('DB', f'name re-derive skipped: {e}')
    conn.commit(); conn.close()

def db_create_room(creator_pilot, account, game_def_raw, room_slot=35, terrain=None):
    if terrain is None:
        terrain = extract_terrain_from_gamedef(game_def_raw)
    room_name = extract_name_from_gamedef(game_def_raw) or 'Unnamed'
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO rooms(room_name, creator_pilot, account_name, game_def_raw, room_slot, terrain) "
        "VALUES(?,?,?,?,?,?)",
        (room_name, creator_pilot, account, game_def_raw, room_slot, terrain))
    room_id = cur.lastrowid
    conn.commit(); conn.close()
    return room_id

def db_get_room_settings(room_id):
    """Return the web-edited GAME_DEF setting overrides for a room as a {key: feet} dict
    (empty if none/invalid). Applied at 212 serve time by build_lz_gamedef."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT settings_json FROM rooms WHERE room_id=?", (room_id,)).fetchone()
        conn.close()
        if row and row[0]:
            d = json.loads(row[0])
            return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}

def db_get_open_rooms():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT room_id, room_name, creator_pilot, account_name, created_at, room_slot, "
        "game_def_raw, terrain, category "
        "FROM rooms WHERE status='open' ORDER BY created_at DESC").fetchall()
    conn.close(); return rows

# 2026-06-29: keep rooms listed even after they empty out (or when their creator opens a
# new room), so e.g. a Territorial Combat ground room and a Free For All air room coexist
# instead of the second one reaping the first. With this True, db_close_room only VACATES
# the room (clears its players) and leaves status='open'. Manual cleanup is still available
# via the console 'clearrooms' command. Set False to restore auto-close-on-empty.
PERSIST_ROOMS = True

def db_close_room(room_id):
    conn = sqlite3.connect(DB_PATH)
    if not PERSIST_ROOMS:
        conn.execute("UPDATE rooms SET status='closed' WHERE room_id=?", (room_id,))
    conn.execute("DELETE FROM room_players WHERE room_id=?", (room_id,))
    conn.commit(); conn.close()

def db_room_join(room_id, pilot, account):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO room_players(room_id,pilot_name,account_name) VALUES(?,?,?)",
                 (room_id, pilot, account))
    conn.commit(); conn.close()

def db_room_leave(pilot):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM room_players WHERE pilot_name=?", (pilot,))
    conn.commit(); conn.close()

def db_get_pilots_in_room(room_id):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT pilot_name, joined_at FROM room_players WHERE room_id=? ORDER BY joined_at",
        (room_id,)).fetchall()
    conn.close(); return rows

def db_get_room_for_pilot(pilot_name):
    """Return (room_id, room_slot) if pilot has an open room, else None.
    Checks by creator_pilot first (most common), then room_players membership.
    Logs the result explicitly so connection drops are diagnosable.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT room_id, room_slot FROM rooms "
            "WHERE status='open' AND creator_pilot=? "
            "ORDER BY created_at DESC LIMIT 1", (pilot_name,)).fetchone()
        if not row:
            row = conn.execute(
                "SELECT r.room_id, r.room_slot FROM rooms r "
                "JOIN room_players p ON r.room_id=p.room_id "
                "WHERE r.status='open' AND p.pilot_name=? "
                "ORDER BY r.created_at DESC LIMIT 1", (pilot_name,)).fetchone()
        conn.close()
        if row:
            log('DB', f'db_get_room_for_pilot("{pilot_name}") -> room_id={row[0]} slot=0x{row[1]:02x}')
        else:
            log('DB', f'db_get_room_for_pilot("{pilot_name}") -> None (no open room)')
        return (row[0], row[1]) if row else None
    except Exception as e:
        log('DB', f'db_get_room_for_pilot error: {e}')
        return None

def db_room_player_count(room_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT COUNT(*) FROM room_players WHERE room_id=?", (room_id,)).fetchone()
    conn.close(); return row[0] if row else 0

# --- Ticket template ----------------------------------------------------------

TICKET_PATHS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ticket_base.vr1'),
    r"C:\games\FA\ticket.vr1", r"C:\Games\FA\ticket.vr1", "ticket.vr1",
]

def load_ticket_template():
    global TICKET_TEMPLATE
    for path in TICKET_PATHS:
        if not os.path.exists(path): continue
        data = open(path, 'rb').read()
        if len(data) != TICKET_SIZE:
            log('TICKET', f'Skipping {path}: size {len(data)} != {TICKET_SIZE}'); continue
        TICKET_TEMPLATE = bytearray(data)
        base_acct = data[TICKET_ACCT_OFF:TICKET_ACCT_OFF+TICKET_ACCT_LEN].split(b'\x00')[0].decode(errors='replace')
        base_pid  = hx(data[TICKET_PID_OFF:TICKET_PID_OFF+4])
        log('TICKET', f'Template loaded: {path} ({TICKET_SIZE}b) base_acct="{base_acct}" base_pid={base_pid}')
        return True
    log('TICKET', 'No base ticket found - ticket generation unavailable')
    return False

def generate_ticket(account_name: str) -> tuple:
    if TICKET_TEMPLATE is None: raise RuntimeError("No ticket template loaded")
    account_name = account_name.strip()
    if not account_name: raise ValueError("Account name cannot be empty")
    if len(account_name) > TICKET_ACCT_LEN - 1: raise ValueError(f"Account name too long")
    if not all(0x20 <= ord(c) <= 0x7e for c in account_name): raise ValueError("Must be printable ASCII")
    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute("SELECT player_id FROM accounts WHERE account_name=?", (account_name,)).fetchone()
    conn.close()
    if existing: raise ValueError(f'Account "{account_name}" already exists (pid={existing[0]})')
    pid_bytes = pid_hex = None
    for _ in range(200):
        candidate = secrets.token_bytes(4)
        if db_get_account_by_pid(candidate.hex()) is None:
            pid_bytes = candidate; pid_hex = candidate.hex(); break
    if pid_bytes is None: raise RuntimeError("Could not generate unique PID")
    ab_hex  = hx(TICKET_TEMPLATE[TICKET_AB_OFF:TICKET_AB_OFF+16])
    f45_hex = hx(TICKET_TEMPLATE[TICKET_F45_OFF:TICKET_F45_OFF+4])
    ticket = bytearray(TICKET_TEMPLATE)
    ticket[TICKET_PID_OFF:TICKET_PID_OFF+4] = pid_bytes
    acct_field = account_name.encode('ascii') + b'\x00' * (TICKET_ACCT_LEN - len(account_name))
    ticket[TICKET_ACCT_OFF:TICKET_ACCT_OFF+TICKET_ACCT_LEN] = acct_field
    assert len(ticket) == TICKET_SIZE
    db_upsert_account(account_name, pid_hex, f45_hex, ab_hex)
    log('TICKET_GEN', f'Created account="{account_name}" pid={pid_hex}')
    return bytes(ticket), pid_hex

def cmd_gen_ticket(account_name: str):
    try: ticket_bytes, pid_hex = generate_ticket(account_name)
    except Exception as e: log('TICKET_GEN', f'ERROR: {e}'); return
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f'ticket_{account_name}.vr1')
    with open(out_path, 'wb') as f: f.write(ticket_bytes)
    saved = open(out_path, 'rb').read()
    acct_rb = saved[TICKET_ACCT_OFF:TICKET_ACCT_OFF+TICKET_ACCT_LEN].split(b'\x00')[0].decode()
    pid_rb  = hx(saved[TICKET_PID_OFF:TICKET_PID_OFF+4])
    log('TICKET_GEN', f'Saved: {out_path}')
    log('TICKET_GEN', f'  Verify: acct="{acct_rb}" pid={pid_rb} size={len(saved)}b')

def console_handler():
    log('CONSOLE', 'Ready. Commands: gen | list | destroy | loglevel | logmute | logtags | help')
    while running:
        try:
            raw_line = sys.stdin.readline()
        except Exception:
            break
        if raw_line == '':          # EOF (stdin closed / piped / detached)
            log('CONSOLE', 'stdin closed - console commands disabled (server still running)')
            return
        line = raw_line.strip()
        if not line: continue
        try:
            parts = line.split(None, 1); cmd = parts[0].lower()
            if cmd == 'gen':
                if len(parts) < 2: log('CONSOLE', 'Usage: gen <account_name>')
                else: cmd_gen_ticket(parts[1].strip())
            elif cmd == 'list':
                accounts = db_get_all_accounts()
                if not accounts: log('CONSOLE', 'No accounts in DB')
                for a, p, f45, ab in accounts:
                    log('CONSOLE', f'  {a}  pid={p}  pilots={[n for n,_ in db_get_pilots(a)]}')
                rooms = db_get_open_rooms()
                log('CONSOLE', f'Open rooms: {len(rooms)}')
                for r in rooms:
                    rid, rname, creator = r[0], r[1], r[2]
                    trn = r[7] if len(r) > 7 else DEFAULT_TERRAIN
                    pcount = db_room_player_count(rid)
                    tname = TERRAIN_NAMES.get(trn, '?')
                    log('CONSOLE', f'  room {rid}: name={rname!r} creator={creator} '
                                   f'terrain={trn} ({tname}) players={pcount}')
            elif cmd == 'clearrooms':
                conn = sqlite3.connect(DB_PATH)
                conn.execute("UPDATE rooms SET status='closed'")
                conn.execute('DELETE FROM room_players')
                conn.commit(); conn.close()
                log('CONSOLE', 'All rooms cleared')
            elif cmd == 'reopen':
                conn = sqlite3.connect(DB_PATH)
                cur = conn.execute("UPDATE rooms SET status='open' WHERE status='closed'")
                n = cur.rowcount
                conn.commit(); conn.close()
                log('CONSOLE', f'Re-opened {n} closed room(s) (now visible in the arena list)')
            elif cmd == 'destroy':
                # destroy <sceneIdx> [camp] [progress]  - fire msg 36 SCENE DESTROY/STATE at a
                # KNOWN scene index, to validate the msg-36 wire format live (independent of the
                # unconfirmed msg-31 objidx->sceneIdx mapping). Defaults: camp=0xff (neutralized),
                # progress=0.0 (captured/destroyed). Targets every in-game room that has players.
                args = (parts[1].split() if len(parts) > 1 else [])
                if not args:
                    log('CONSOLE', 'Usage: destroy <sceneIdx> [camp=255] [progress=0]')
                else:
                    try:
                        sidx = int(args[0], 0)
                        # default camp = the scene's REAL owning camp so the client names the
                        # target ('You have destroyed <owner> <SceneName>') instead of the
                        # generic 'a bridge' that camp=0xFF forces. Pass an explicit 2nd arg
                        # (e.g. 255) to override.
                        prog = float(args[2]) if len(args) > 2 else 0.0
                    except ValueError:
                        log('CONSOLE', 'destroy: sceneIdx/camp must be ints, progress a float')
                    else:
                        rooms = {x.current_room for x in get_all_sessions()
                                 if getattr(x, 'entered_game', False) and x.current_room is not None}
                        if not rooms:
                            log('CONSOLE', 'destroy: no in-game players to send to')
                        for rid in rooms:
                            if len(args) > 1:
                                camp = int(args[1], 0)
                            else:
                                camp = scene_camp(_probe_terrain_for_room(rid), sidx)
                            broadcast_scene_36(rid, [(sidx, camp, prog)], reason='(console destroy)')
            elif cmd == 'resupply':
                # resupply [flags] [amount] [amount2] [b1] [b2]  - v266: send msg 60 (0x3c) SUPPLY
                # GRANT to trigger the client's in-world REARM/REFUEL (no despawn). Defaults:
                # flags=0x04 (the rearm/refuel path in the handler), amounts=0xffff (max fuel/ammo).
                # The rearm is CLIENT-LOCAL and the client doesn't send msg 59 in our setup, so we
                # push msg 60 proactively. TEST: park + fire some ammo + engine off, then run
                # `resupply` -> the client should refuel/rearm in place. If nothing happens, iterate
                # the framing (b1/b2 bytes, flags bits) from the client log - the exact header bytes
                # between the type and the flags aren't pinned yet.
                #  (v265 note: msg-36 was the WRONG vehicle - it destroyed a scene + docked score.
                #   msg-60 flags&4 is the actual rearm path, RE'd from handler 0x5581c0.)
                args = (parts[1].split() if len(parts) > 1 else [])
                try:
                    flags = int(args[0], 0) if len(args) > 0 else 0x04
                    amount = int(args[1], 0) if len(args) > 1 else 0xffff
                    amount2 = int(args[2], 0) if len(args) > 2 else 0xffff
                    b1 = int(args[3], 0) if len(args) > 3 else 0
                    b2 = int(args[4], 0) if len(args) > 4 else 0
                except ValueError:
                    log('CONSOLE', 'resupply: all args must be ints. '
                                   'Usage: resupply [flags=4] [amount=65535] [amount2=65535] [b1=0] [b2=0]')
                else:
                    rooms = {x.current_room for x in get_all_sessions()
                             if getattr(x, 'entered_game', False) and x.current_room is not None}
                    if not rooms:
                        log('CONSOLE', 'resupply: no in-game players to send to')
                    for rid in rooms:
                        n = broadcast_supply_grant_60(rid, flags=flags, amount=amount,
                                                      amount2=amount2, b1=b1, b2=b2,
                                                      reason='(console resupply - rearm/refuel)')
                        log('CONSOLE', f'resupply: sent msg 60 (flags=0x{flags:02x} amt={amount} '
                                       f'amt2={amount2} b1={b1} b2={b2}) to {n} player(s) in room {rid}. '
                                       f'Park + deplete + engine off -> watch for in-place rearm.')
            elif cmd == 'probe':
                # probe <sceneIdx>            fire one destroy + capture ev=0x00 reconciliation
                # probe sweep [lo] [hi] [gap]  walk a scene range, building the whole map
                # probe save | show | stop
                pa = (parts[1].split() if len(parts) > 1 else [])
                rooms = {x.current_room for x in get_all_sessions()
                         if getattr(x, 'entered_game', False) and x.current_room is not None}
                if not pa:
                    log('CONSOLE', 'Usage: probe <sceneIdx> | probe sweep [lo hi gap] | probe save | show | stop')
                elif pa[0] == 'sweep':
                    if not rooms:
                        log('CONSOLE', 'probe: no in-game players to probe')
                    else:
                        lo = int(pa[1], 0) if len(pa) > 1 else 0
                        hi = int(pa[2], 0) if len(pa) > 2 else 59
                        gap = float(pa[3]) if len(pa) > 3 else 3.0
                        for rid in rooms:
                            probe_sweep(rid, lo, hi, gap)
                        log('CONSOLE', f'probe sweep {lo}..{hi} gap={gap}s started on {len(rooms)} room(s)')
                elif pa[0] == 'stop':
                    with PROBE_LOCK: PROBE['stop'] = True
                    log('CONSOLE', 'probe sweep stop requested')
                elif pa[0] == 'save':
                    n, path = probe_save(); log('CONSOLE', f'probe: {n} objIdx->sceneIdx entries saved to {path}')
                elif pa[0] == 'show':
                    with PROBE_LOCK:
                        for sc in sorted(PROBE['map']):
                            log('CONSOLE', f'  scene {sc}: objs {sorted(PROBE["map"][sc])}')
                        if not PROBE['map']: log('CONSOLE', '  (no captures yet)')
                else:
                    try:
                        sc = int(pa[0], 0)
                    except ValueError:
                        log('CONSOLE', 'probe: sceneIdx must be an int'); sc = None
                    if sc is not None:
                        if not rooms:
                            log('CONSOLE', 'probe: no in-game players to probe')
                        for rid in rooms:
                            probe_fire(rid, sc)
                        log('CONSOLE', f'probe scene {sc} fired; ev=0x00 objects will be captured (probe show to view)')
            elif cmd == 'corr':
                # corr watch | show | stop | map <obj> <scene> | find <obj> [lo hi gap]
                ca = (parts[1].split() if len(parts) > 1 else [])
                rooms = {x.current_room for x in get_all_sessions()
                         if getattr(x, 'entered_game', False) and x.current_room is not None}
                if not ca:
                    log('CONSOLE', 'Usage: corr watch | show | stop | map <obj> <scene> | find <obj> [lo hi gap]')
                elif ca[0] == 'watch':
                    with CORR_LOCK:
                        CORR['watch'] = True; CORR['weapon'].clear(); CORR['last05'].clear()
                    log('CONSOLE', 'corr: watching ev=0x05 weapon targets. Strafe ONE building, then `corr show`.')
                elif ca[0] == 'stop':
                    with CORR_LOCK: CORR['watch'] = False; CORR['stop'] = True
                    log('CONSOLE', 'corr: stopped watching / sweep cancelled')
                elif ca[0] == 'show':
                    with CORR_LOCK:
                        items = sorted(CORR['weapon'].items(), key=lambda kv: -kv[1]['dmg'])
                        if not items: log('CONSOLE', '  (no ev=0x05 weapon hits captured yet)')
                        for o, w in items:
                            log('CONSOLE', f'  obj {o}: {w["hits"]} hits, total dmg {w["dmg"]}')
                elif ca[0] == 'map':
                    if len(ca) >= 3:
                        try:
                            o = int(ca[1], 0); sc = int(ca[2], 0)
                            p = corr_map_save(o, sc)
                            log('CONSOLE', f'corr: recorded weapon obj {o} -> scene {sc} in {p}')
                        except ValueError:
                            log('CONSOLE', 'corr map: obj and scene must be ints')
                    else:
                        log('CONSOLE', 'Usage: corr map <obj> <scene>')
                elif ca[0] == 'find':
                    if len(ca) >= 2 and rooms:
                        try:
                            o = int(ca[1], 0)
                            lo = int(ca[2], 0) if len(ca) > 2 else 0
                            hi = int(ca[3], 0) if len(ca) > 3 else 59
                            gap = float(ca[4]) if len(ca) > 4 else 4.0
                            for rid in rooms:
                                corr_find(rid, o, lo, hi, gap)
                            log('CONSOLE', f'corr find obj {o} started (keep strafing it!)')
                        except ValueError:
                            log('CONSOLE', 'corr find: obj must be an int')
                    elif not rooms:
                        log('CONSOLE', 'corr find: no in-game players')
                    else:
                        log('CONSOLE', 'Usage: corr find <obj> [lo hi gap]')
                else:
                    log('CONSOLE', f'corr: unknown subcommand {ca[0]!r}')
            elif cmd == 'autopve':
                # autopve on|off|status|hp <n>  - live control of weapon-damage auto-destroy
                aa = (parts[1].split() if len(parts) > 1 else [])
                global AUTO_SCENE_DESTROY, SCENE_DEFAULT_HP
                if not aa or aa[0] == 'status':
                    log('CONSOLE', f'autopve: {"ON" if AUTO_SCENE_DESTROY else "OFF"}, '
                                   f'scene HP threshold={SCENE_DEFAULT_HP}, tracked scenes={len(SCENE_HP)}')
                elif aa[0] == 'on':
                    AUTO_SCENE_DESTROY = True
                    log('CONSOLE', 'autopve ON - weapon damage now auto-destroys scenes (obj==sceneIdx)')
                elif aa[0] == 'off':
                    AUTO_SCENE_DESTROY = False
                    log('CONSOLE', 'autopve OFF')
                elif aa[0] == 'hp' and len(aa) > 1:
                    try:
                        SCENE_DEFAULT_HP = int(aa[1], 0)
                        log('CONSOLE', f'autopve: scene HP threshold set to {SCENE_DEFAULT_HP}')
                    except ValueError:
                        log('CONSOLE', 'autopve hp: value must be an int')
                elif aa[0] == 'reset':
                    SCENE_HP.clear()
                    for x in get_all_sessions():
                        x.__dict__.pop('_scene_destroyed', None)
                    log('CONSOLE', 'autopve: scene HP + destroyed-set reset')
                else:
                    log('CONSOLE', 'Usage: autopve on | off | status | hp <n> | reset')
            elif cmd == 'evp':
                # evp on|off|status|set <a> <f> <bg> <s> <t>  - enemy flak (AA quality in GAME_DEF)
                ea = (parts[1].split() if len(parts) > 1 else [])
                global EVP_AA_ENABLED, EVP_AA_QUALITY
                if not ea or ea[0] == 'status':
                    log('CONSOLE', f'evp: {"ON" if EVP_AA_ENABLED else "OFF"}, AA quality='
                                   f'{EVP_AA_QUALITY} (AAquality/Flak/BomberGunner/ShipAA/TankAA). '
                                   f'Re-enter the arena to apply.')
                elif ea[0] == 'on':
                    EVP_AA_ENABLED = True
                    log('CONSOLE', 'evp ON - enemy flak enabled; re-enter the arena so the '
                                   'GAME_DEF re-serves with AA quality set')
                elif ea[0] == 'off':
                    EVP_AA_ENABLED = False
                    log('CONSOLE', 'evp OFF - re-enter the arena to silence the guns')
                elif ea[0] == 'set' and len(ea) >= 6:
                    try:
                        EVP_AA_QUALITY = tuple(max(0, min(10, int(x))) for x in ea[1:6])
                        log('CONSOLE', f'evp: AA quality set to {EVP_AA_QUALITY}')
                    except ValueError:
                        log('CONSOLE', 'evp set: five ints (0..10) required')
                else:
                    log('CONSOLE', 'Usage: evp on | off | status | set <AA> <Flak> <BomberGunner> <ShipAA> <TankAA>')
            elif cmd == 'rec':
                # rec on|off|status|dump  - flight recorder (reliable + telemetry ring per client)
                ra = (parts[1].split() if len(parts) > 1 else [])
                global FLIGHT_RECORDER
                if not ra or ra[0] == 'status':
                    _sess=get_all_sessions()
                    log('CONSOLE', f'rec: {"ON" if FLIGHT_RECORDER else "OFF"}, '
                                   f'ring rel={FLIGHT_REC_RELMAX}/unrel={FLIGHT_REC_UNRMAX}, '
                                   f'{len(_sess)} live session(s), dir={FLIGHT_REC_DIR}')
                elif ra[0] == 'on':
                    FLIGHT_RECORDER = True; log('CONSOLE', 'rec ON - flight recorder capturing')
                elif ra[0] == 'off':
                    FLIGHT_RECORDER = False; log('CONSOLE', 'rec OFF')
                elif ra[0] == 'dump':
                    n=0
                    for s in get_all_sessions():
                        _p=_rec_dump(s, 'manual console dump')
                        if _p:
                            n+=1; log('CONSOLE', f'  dumped {s.current_pilot} -> {_p}')
                    log('CONSOLE', f'rec dump: wrote {n} file(s)')
                else:
                    log('CONSOLE', 'Usage: rec on | off | status | dump')
            elif cmd == 'loglevel':
                a = parts[1].split() if len(parts) > 1 else []
                if len(a) == 2 and a[0] == 'console':
                    _falog.set_console_level(a[1]); log('CONSOLE', f'console level -> {a[1].upper()}')
                else:
                    log('CONSOLE', 'Usage: loglevel console <DEBUG|INFO|WARNING|ERROR>')
            elif cmd == 'logmute':
                if len(parts) > 1: _falog.mute_tag(parts[1].strip()); log('CONSOLE', f'muted {parts[1].strip()}')
                else: log('CONSOLE', 'Usage: logmute <TAG>')
            elif cmd == 'logunmute':
                if len(parts) > 1: _falog.unmute_tag(parts[1].strip()); log('CONSOLE', f'unmuted {parts[1].strip()}')
                else: log('CONSOLE', 'Usage: logunmute <TAG>')
            elif cmd == 'logtags':
                log('CONSOLE', f'muted tags: {_falog.list_muted() or "(none)"}')
            elif cmd == 'help':
                log('CONSOLE', 'gen <name>  - generate ticket for new account')
                log('CONSOLE', 'list        - show all accounts and their pilots')
                log('CONSOLE', 'destroy <sceneIdx> [camp] [progress] - fire msg 36 SCENE DESTROY to in-game players')
                log('CONSOLE', 'resupply [flags] [amount] [amt2] [b1] [b2] - send msg 60 supply grant (in-world rearm/refuel)')
                log('CONSOLE', 'loglevel console <LVL> | logmute <TAG> | logunmute <TAG> | logtags - logging control')
            else: log('CONSOLE', f'Unknown command "{cmd}". Type "help".')
        except Exception:
            logx('CONSOLE', f'command failed: {line!r}')

# --- SYN identification -------------------------------------------------------

def identify_account_from_syn(syn_data):
    payload = syn_data[8:]
    pid_hex = hx(payload[SYN_OFF_PID:SYN_OFF_PID+4])   if len(payload) > SYN_OFF_PID+4  else '00000000'
    ab_hex  = hx(payload[SYN_OFF_AUTH:SYN_OFF_AUTH+16]) if len(payload) > SYN_OFF_AUTH+16 else '0'*32
    f45_hex = hx(payload[SYN_OFF_F45:SYN_OFF_F45+4])   if len(payload) > SYN_OFF_F45+4  else '00000000'
    null = payload.find(b'\x00', SYN_OFF_ACCT)
    raw  = payload[SYN_OFF_ACCT:null] if null > SYN_OFF_ACCT else b''
    acct = raw.decode('ascii', errors='ignore').strip()
    log('SYN', f'pid={pid_hex}  acct_raw={raw.hex()!r}  acct="{acct}"')
    if acct and all(0x20 <= ord(c) <= 0x7e for c in acct):
        log('SYN', f'Identified: account="{acct}" pid={pid_hex}')
        db_upsert_account(acct, pid_hex, f45_hex, ab_hex)
        return (acct, pid_hex, f45_hex, ab_hex)
    log('SYN', f'Name unreadable, falling back to pid search')
    row = db_get_account_by_pid(pid_hex)
    if row: return row
    for row in db_get_all_accounts():
        pid_bytes = bytes.fromhex(row[1])
        idx = payload.find(pid_bytes)
        if idx >= 0:
            if idx >= 20:
                ab_scan  = hx(payload[idx-20:idx-4])
                f45_scan = hx(payload[idx-4:idx])
                db_upsert_account(row[0], row[1],
                    f45_scan if f45_scan != '0'*8 else row[2],
                    ab_scan  if len(ab_scan)==32  else row[3])
            return db_get_account_by_pid(row[1])
    return None

# --- Startup ------------------------------------------------------------------

init_db(); init_rooms_db(); load_ticket_template()
for _a, _p, *_ in db_get_all_accounts():
    log('DB', f'account="{_a}" pid={_p} pilots={[n for n,_ in db_get_pilots(_a)]}')

# --- Packet builders ----------------------------------------------------------

# Time-sync epoch. The in-game STATUS/TIME beacon (type 2, p[1]=0x40, p[2]=0x80) and
# the time_reply (type 2, p[2]=0x80) carry a packed time dword at p[8:12]:
#   A = dword & 0x3FFFF  (low 18 bits)  - a MILLISECOND timestamp the client converts
#                                         to seconds (A/1000) + fixed-point fraction
#   B = dword >> 18      (high 14 bits) - a delay correction, SUBTRACTED; must stay 0
# The client (vcncNet.dll, RecalculateDriftRate @0x10008739) fits a linear regression of
# clock-offset (serverTime - localTime) vs localTime over 8 samples; the slope is the
# drift Rate. If serverTime ADVANCES 1:1 with local time the offset is constant -> slope 0.
# The old code sent A=int((time.time()%1.0)*1000) (0..999, sawtoothing every second), so
# decoded whole-seconds never advanced -> slope -1.00075 -> NET time froze ~60s in (the
# 'CRAP!!! HUGE backward NET Time' meltdown @0x10009ff2) -> disconnect. Sending a
# MONOTONIC ms counter makes A/1000 advance at 1 s/s -> slope 0. Masked to the 18-bit
# field (keeps B=0); wraps every 0x3FFFF ms ~= 262 s - the client re-bases from samples
# far more often (every ~8 beacons), so the wrap never lands inside a fit window.
# v204: the wrap DID melt down on arena RE-ENTRY (client re-fits its drift regression then);
# v204's per-session rebase FIXED the wrap but reset the counter mid-session -> a DIFFERENT
# backward jump (= session-elapsed). Both moved the value backward. REVERTED in v205.
# v205 ROOT-CAUSE FIX: the client (vcncNet FUN_10007fc0) decodes A = dword & 0x3FFFF, takes
# A/1000 as SECONDS, and ADDS it to a persistent base anchored from our SYNACK timestamp. A is
# only 18 bits -> 262.143s range. The client reconstructs the HIGH-ORDER time from its OWN wall
# clock and uses A only for the sub-262s phase; so A must be PHASE-ALIGNED to WALL-CLOCK ms, not
# to elapsed-since-connect. Sending elapsed-ms (v202/203) drifts out of phase and wraps visibly
# -> the ~262s 'CRAP backward NET Time' jump. Sending A = (unix_ms & 0x3FFFF) keeps the low 18
# bits phase-locked to real wall-clock time, so the client's high-bit reconstruction always lands
# on the correct absolute second and the wrap is invisible. This is inherently monotonic (never
# resets, never needs rebasing) as long as the server & client wall clocks agree within ~131s.
_TSYNC_T0 = time.time()
def tsync_ms(sess=None):
    """A-field value for the beacon/time_reply: low 18 bits of ms ELAPSED since the session's NTP
    base anchor (sess._ntp_epoch). The client reconstructs server_time = base + A/1000; with base =
    the fa_s:fa_frac we anchored at _ntp_epoch, base + A == server_now, so the NTP clock offset is
    ~0 (only the real network delay remains -> a truthful HUD 'L:' lag instead of the broken 0.00).
    A is 18-bit and would wrap at 262.143s, but the heartbeat re-anchors the base (and resets
    _ntp_epoch) every NTP_REANCHOR_S < 262s, so elapsed never reaches the wrap. Falls back to the
    FA_EPOCH-absolute phase for the pre-session/SYN path where no session epoch exists yet.
    History: v205/6 sent unix_ms&mask (122s phase skew); v207 sent (unix-FA_EPOCH)ms&mask (absolute
    phase, a constant ~246s offset vs the client's elapsed-since-base -> the 262s wrap then slewed
    to death). v211 sends elapsed-since-anchor + periodic re-anchor: offset ~0, no wrap."""
    if sess is not None and getattr(sess, '_ntp_epoch', None) is not None:
        return int((time.time() - sess._ntp_epoch) * 1000) & 0x3FFFF
    return int((time.time() - FA_EPOCH) * 1000) & 0x3FFFF

def build_synack(fixed_fa=None):
    # v209: `fixed_fa` = (fa_s, fa_frac) to re-use the ORIGINAL connect-time base on a re-anchor.
    # 2009 ground truth (messages04): CreationTimeSeconds was IDENTICAL on connect (01:31) and on
    # world re-entry (03:04) = 3451426175 - the base is a FIXED connect constant, not a fresh
    # timestamp. Re-sending a NEWER base on HQ re-entry would jump the client's NET time forward by
    # the session-elapsed. So a re-anchor MUST replay the connect fa_s/fa_frac, not call
    # fa_timestamp() again.
    fa_s, fa_frac = fixed_fa if fixed_fa is not None else fa_timestamp()
    p = bytearray(92); p[2]=0x10          # v217: 84 -> 92 bytes so the true cfg+0x40 (byte 88) fits
    struct.pack_into('>I',p,8,fa_s); struct.pack_into('>I',p,12,fa_frac)
    c=16
    # v217 CORRECTION of a long-standing byte-alignment error. The client copies 0x44 (68) bytes of
    # net-config into its struct at 0x10020300, but the copy SOURCE is the SYN section base + 0x10.
    # Traced precisely (dispatcher lea ebx,[esi+0xc]=wire byte 8 for a SYN-only packet; RecvSYNReply
    # FUN_10003cd3 then `add esi,0x10`): the config source is WIRE BYTE 24, so the client's cfg[k] =
    # our packet byte (24 + k). The RTT-sample RING CAPACITY is cfg[0x40] = packet BYTE 88 - NOT byte
    # 80 as an earlier note assumed. Our config block below is written at c=16, i.e. 8 bytes EARLIER
    # than where the client reads it, so cfg[0x40] fell on packet byte 88 which was PAST the old
    # 84-byte packet -> the client read 0/garbage as the cap -> the RTT ring was effectively
    # unbounded and, once a sample was taken, its slot writes ran past the 32-slot region into the
    # delivery-callback pointer (ring index 64 == struct+0xcc) -> CTD. This is the real mechanism
    # behind the "~Nth re-entry" crash AND why v216's next_exp=seq+1 (which re-enables sampling)
    # crashed immediately: with no valid cap, the very first sample overflowed.
    #
    # MINIMAL FIX (chosen to protect the stable v215 baseline): leave the existing config block at
    # c=16 BYTE-FOR-BYTE UNCHANGED (so every field the client currently reads at cfg[0x00..0x38] is
    # identical to what it has always seen), and ADDITIONALLY write the RTT cap at the TRUE location
    # (packet byte 88 == cfg[0x40]). The packet is extended to 92 bytes so byte 88-91 exist and the
    # client's 68-byte copy (bytes 24..91) is fully covered. Net effect: exactly ONE value the client
    # sees changes - cfg[0x40] goes from out-of-bounds 0/garbage to a valid 32 - and nothing else.
    # With a real cap the ring is bounded at 32 (< the index-64 callback slot), so RTT sampling is
    # finally safe to enable (RTT_SAMPLING, step 2). While RTT_SAMPLING=False this fix is inert (the
    # ring never advances), so step 1 just proves the 92-byte SYNACK doesn't disturb connect.
    RTT_RING_CAP = 32   # cfg+0x40 == packet byte 88; must be 1..64 (64 = array ends right before the callback ptr)
    for off,val in [(0,30),(0x14,8),(0x18,5000),(0x1C,10),(0x20,30000),
                    (0x24,5000),(0x28,200),(0x2C,50),(0x30,100),(0x34,16),(0x38,16),(0x3C,100),
                    (0x40,RTT_RING_CAP)]:
        struct.pack_into('>I',p,c+off,val)
    # v217: the cap at the TRUE offset (packet byte 88 = client cfg[0x40]). This is the field that
    # actually reaches the client's ring sizer; the c=16 copy above lands it at byte 80 (client
    # cfg[0x38]) which is a DIFFERENT field, so we must also write it here.
    struct.pack_into('>I', p, 24 + 0x40, RTT_RING_CAP)   # == byte 88
    return bytes(p), fa_s, fa_frac

def build_time_reply(cd, sess=None):
    ti = struct.unpack_from('>H',cd,8)[0] if len(cd)>=10 else 0
    ms=tsync_ms(sess); p=bytearray(144); p[0]=2; p[2]=0x80
    struct.pack_into('>I',p,8,ms&0x3FFFF); struct.pack_into('>H',p,12,STATUS_INDEX)
    struct.pack_into('>H',p,14,ti); return bytes(p)

def build_beacon(seq, idx=0, sess=None):
    ms=tsync_ms(sess); p=bytearray(144); p[0]=2; p[1]=0x40; p[2]=0x80
    struct.pack_into('<H',p,6,seq&0xFFFF); struct.pack_into('>I',p,8,ms&0x3FFFF)
    struct.pack_into('>H',p,12,STATUS_INDEX); struct.pack_into('>H',p,14,idx); return bytes(p)

def build_keepalive(sess=None):
    """v213: in-game connection keepalive that resets the client's 60s connection-alive timer
    (vcncOpen DAT_1001f878=60000) WITHOUT feeding the NET-time base or suppressing the client's
    self-healing resync. It's a TIME packet (p[2]=0x80) carrying a SENTINEL time-index 0xFFFF that
    matches no pending ping. Two cases, both safe (verified in vcncNet FUN_10007f06):
      - synced (sync state 3): the time handler early-exits (it only runs in state 1/2), so the
        packet is ignored by the time layer entirely; but the packet dispatcher (FUN_100032da)
        stamps DAT_10017be8 on EVERY received packet, resetting the 60s timer. Pure keepalive.
      - mid-resync (state 2): the sentinel index fails the queue match (FUN_10007b0c), so it's
        logged as a 'Duplicate time message' and dropped - no sample, no DAT_1001d630 update, no
        wrapping-A applied. The client still resyncs off its OWN two-way pings (we answer those).
    So this keeps the link alive across the ~60s window without re-introducing the 262s beacon wrap
    or preventing the resync that re-baselines the clock and measures latency."""
    p=bytearray(144); p[0]=2; p[2]=0x80
    struct.pack_into('>I',p,8,tsync_ms(sess)&0x3FFFF)
    struct.pack_into('>H',p,12,STATUS_INDEX)
    struct.pack_into('>H',p,14,0xFFFF)   # sentinel time-index: matches no pending ping -> dropped
    return bytes(p)

def build_status_request(sess, base_incr_ms):
    """v215: build a 'Game Status Message' / STATUS REQUEST packet - the REAL in-game time keeper.

    Discovery (from the user's clue that the System Status window's session timer sits at 0:00):
    the System Status window (bytes/sec, loss%, latency, SESSION TIME) is fed by a two-way STATUS
    exchange that is SEPARATE from the NTP time sync. When the client receives a STATUS request it
    runs FUN_100073a4 (updates those fields + the session clock) AND - critically - FUN_10007d13
    ('STATUS Update server base time'), which ADDS base_incr_ms to the NET-time BASE (DAT_1001d0b0)
    via FUN_100079c4. That base is the value we had proven was otherwise connect-only (set-base is
    gated behind a state-1 SYN that's rejected in-game). So the STATUS packet is how the server
    ADVANCES the client's base time mid-game - which defeats the 262s wrap of the 18-bit A field:
    with the base advancing, base + A tracks real time and the wrap of A stops mattering. This is
    almost certainly how the 2009 server kept in-game time; our one-way NTP beacon was a wrong
    substitute that both wrapped and (during a resync) impersonated a ping reply.

    Wire format (mirrors the client's own STATUS reply builder in FUN_100076c2 / FUN_100070c9):
      bytes 0-1  : connection id (the value the client stamps in its own packets; captured per
                   session as _status_connid, else fall back to the beacon-style 0x0240).
      byte  2    : section-flags byte = 0x20 (DATA section; the dispatcher routes on byte[7] after
                   ntohs == wire byte 2). (The client also sets 0x02 ACK; DATA alone suffices to
                   reach the sub-type switch.)
      byte  3    : 0.
      bytes 4-7  : control dword (big-endian). Top 3 bits = DATA sub-type = 4 -> selects the STATUS
                   handler FUN_100076c2. Low 9 bits of the header carry the status sequence; we also
                   place the sequence where the client expects it.
      bytes 8-11 : base-time increment in ms (big-endian) -> client ADDs to its base. THE KEY FIELD.
      bytes 12-23: status counters (msgs sent/recvd, etc) used for the loss%/RTT/session calc. We
                   feed monotonic sent/recv counts so the window shows sane values.
    Length 36 (0x24) to match the client's STATUS packet size.
    """
    seq = sess._status_seq & 0x1FF
    p = bytearray(36)
    connid = sess._status_connid if sess._status_connid is not None else 0x0240
    struct.pack_into('>H', p, 0, connid & 0xFFFF)
    p[2] = 0x20                                    # DATA section flag (wire byte 2 == dispatcher byte[7])
    p[3] = 0x00
    ctrl = (4 << 29) | (seq << 20) | 0x80000       # sub_type 4 + seq + status bit (matches client)
    struct.pack_into('>I', p, 4, ctrl & 0xFFFFFFFF)
    struct.pack_into('>I', p, 8, base_incr_ms & 0xFFFFFFFF)   # base increment (ms) -> advances base
    # status counters (wire 12-23): server msgs sent / recvd so far, then two spare u32s. These drive
    # the loss%/RTT display; monotonic counts keep it sane.
    struct.pack_into('>H', p, 12, sess.sq & 0xFFFF)          # msgs sent from server (approx)
    struct.pack_into('>H', p, 14, sess.rx & 0xFFFF)          # msgs recvd by server
    struct.pack_into('>I', p, 16, 0)
    struct.pack_into('>I', p, 20, 0)
    return bytes(p)

def build_rel_ack(cid, seq=0, next_exp=None):
    # CUMULATIVE ACK -- ROOT-CAUSE FIX for the 3rd-reentry CTD.
    # Bit layout (matches vcncNet's own ACK builder FUN_10002a76 / router FUN_100032da):
    #   bits 20-28 = acked-seq (drives the client's RTT sample lookup)
    #   bits 17-19 = type (1 = reliable ACK)
    #   bits  8-16 = next-expected (drives cumulative send-queue removal)
    # WHY: vcncNet keeps a 70-entry RTT-sample history ring based at vcncNet+0x203AC;
    # ring index 64 physically overlaps the registered packet-delivery callback pointer
    # at vcncNet+0x2042c. The ring head advances once per RTT sample, and a sample is
    # taken on the FIRST *timed* ACK of each client packet (FUN_10006f55, whose sole
    # caller is the ACK processor FUN_10006b0e). After ~64 samples the head writes through
    # the callback -> next delivery via (*callback)() faults (the CTD).
    # The old code sent next_exp=0, which forced vcncNet down the single-packet ACK path
    # that finds the packet still queued and DOES sample -> one ring step per client packet.
    # Sending next_exp = seq+2 makes vcncNet remove 'seq' via the cumulative loop
    # FIRST. (The loop internally does next_exp-=1 then removes base..next_exp-1, so seq+2
    # is required to clear seq itself; seq+1 only clears base..seq-1 and leaves seq to be
    # removed -- and SAMPLED -- via the single-packet lookup, which is why seq+1 didn't work.)
    # With seq removed by the loop, the subsequent same-packet RTT lookup misses
    # (FUN_10005e0d returns 0 -> duplicate path FUN_10006fd7) so NO sample is taken. Send-queue
    # removal stays correct (we only ever clear base..seq; the +1 lives in a cosmetic tracker);
    # the ring head never advances, so the callback is never overwritten. RTT estimation is
    # lost, which is harmless on LAN.
    # v216: the next_exp choice controls whether the client SAMPLES RTT for this ACK:
    #   seq+1 -> cumulative loop clears base..seq-1, leaves seq; the same-packet RTT lookup HITS
    #            -> a sample is taken -> the (now capped) RTT ring advances -> REAL-TIME latency.
    #   seq+2 -> the loop clears seq itself first; the same-packet lookup MISSES (duplicate path)
    #            -> NO sample -> frozen latency (the pre-v216 CTD-avoidance behavior).
    # Either way send-queue removal stays correct (we only ever clear base..seq). RTT sampling is
    # now safe because the ring is capped at 32 (RTT_RING_CAP in the SYNACK config), so the ring
    # index wraps well before the index-64 delivery-callback slot that caused the old CTD.
    if next_exp is None: next_exp = (seq + (1 if RTT_SAMPLING else 2)) & 0x1FF
    p=bytearray(8); p[0]=0; p[1]=cid&0xFF; p[2]=2
    struct.pack_into('>I',p,4,(seq<<20)|0x00020000|((next_exp&0x1FF)<<8)); return bytes(p)

def build_data(cmd, sq=0):
    p=bytearray(15); p[0]=2; p[2]=0x20; p[10]=(cmd>>8)&0xFF; p[11]=cmd&0xFF; p[14]=sq&0xFF
    return bytes(p)

def build_rel(payload, seq=0):
    h=bytearray(8); h[0]=0; h[2]=0x20; h[3]=seq&0xFF
    struct.pack_into('>I',h,4,0x20000000); return bytes(h)+bytes(payload)

def build_appspace_pkt(data_bytes):
    n = len(data_bytes); bc = 0 if n<=1 else (n-1+15)//16; size = bc*16+1
    pl = bytearray(4+size); pl[0]=bc&0xFF; pl[1]=0x12; pl[4:4+min(n,size)]=data_bytes[:size]
    return bytes(pl)

def build_appspace_pkt_exact(data_bytes):
    """Like build_appspace_pkt but the payload is the EXACT length of data_bytes -
    NO rounding up to bc*16+1, so NO trailing zero padding. Required for the 212
    GAME_DEF: the client decompresses exactly `size-5` bytes (mix.cpp), and any pad
    bytes are fed into the decompressor -> DecompressedResultSize overflow / corrupt
    parse. The real server's 212 ('in 212'793') is likewise not bc*16+1-aligned, i.e.
    sent at exact size. bc is still set (block hint) but the buffer is not padded."""
    n = len(data_bytes); bc = 0 if n <= 1 else (n - 1 + 15) // 16
    pl = bytearray(4 + n); pl[0] = bc & 0xFF; pl[1] = 0x12; pl[4:4 + n] = data_bytes
    return bytes(pl)

def build_ingame_pkt(data_bytes):
    """BYTE-EXACT in-game framing. THE real Size formula (pinned from the vcncnet log):
    the client computes  Size = bc*16 + (T>>4)  where bc = appspace header byte 0 and
    T = header byte 1. The length is SPLIT - high bits in bc (x16), low 4 bits in T's
    HIGH nibble; T's low nibble (0x2) = the APPSPACE-data channel (-> 'Cmd 0'). Proof:
    StartPlace bc=0 T=0x42 -> 0+4=4; 0x3a echo bc=7 T=0x92 -> 112+9=121; cd chat bc=3
    T=0x12 -> 48+1=49; 212 bc=84 T=0x12 -> 1345. build_appspace_pkt/_exact HARDCODE T=0x12,
    i.e. they pin the size's low nibble to 1 - that's why every message was forced onto the
    Size == 1 (mod 16) grid and small msgs had to be padded. To send Size == n exactly:
    bc = n>>4, T = ((n&0xf)<<4) | 0x2. For n=5 (ServerConfirm): bc=0, T=0x52 -> Size 5 ->
    (5-1)/4 = exactly 1 record. (messages34: the old T=0x12 with bc=0 gave Size = 0*16+1 = 1
    -> client read 1 byte -> 0 records -> no confirm -> freeze. THIS is the actual fix.)"""
    n = len(data_bytes); bc = (n >> 4) & 0xFF
    pl = bytearray(4 + n); pl[0] = bc; pl[1] = ((n & 0x0f) << 4) | 0x02
    pl[4:4 + n] = data_bytes
    return bytes(pl)

def build_typed_pkt(type_byte, data_bytes, bc=None):
    n = len(data_bytes)
    if bc is None: bc = 0 if n <= 1 else (n - 1 + 15) // 16
    size = bc * 16 + 1; pl = bytearray(4 + size)
    pl[0] = bc & 0xFF; pl[1] = type_byte; pl[4:4 + min(n, size)] = data_bytes[:size]
    return bytes(pl)

def build_auth64(pid_hex, f45_hex, ab_hex, acct):
    d = bytearray(64)
    pid=bytes.fromhex(pid_hex); f45=bytes.fromhex(f45_hex); ab=bytes.fromhex(ab_hex)
    acct_b=(acct.encode() if isinstance(acct,str) else acct)+b'\x00'
    d[4:8]=pid[:4]; d[8:12]=f45[:4]; d[12:16]=ab[:4]; d[16:32]=ab[:16]
    d[32:32+len(acct_b)]=acct_b[:32]; return bytes(d)

def build_auth_response(auth64):
    pl=bytearray(80); pl[0]=4; pl[3]=0x64; pl[4:16]=auth64[32:44]; pl[16:80]=auth64
    return bytes(pl)

def build_da_session():
    data=bytearray(17); data[0]=0xDA; data[1]=0x01
    return build_appspace_pkt(bytes(data))

def build_da_session_safe():
    """63-misdispatch-safe variant of the 0xDA lobby re-attach, for the EXIT-TO-HQ
    path only (NOT login). After >=3 enter/fly/exit cycles the client routes this 0xDA
    to the msg-63 ChangePlayerCB handler FUN_004fa9c0 instead of the 218 handler
    FUN_004edcf0 (reproducible: messages29 'in 218'17' early, 'in 63'17' at the crash).
    FUN_004fa9c0 consumes FIXED 7-byte records with NO count, asserting Length>=0
    (VNet_Rcv.cpp:1227) when a remainder of 1..6 bytes is left after the last full
    record. The old Size-17 packet => Length 16 -> 9 -> 2 -> tries a 3rd record -> -5
    -> assert -> CTD. Size 15 => Length 14 -> 7 -> 0 -> loop exits clean (exactly two
    7-byte records, both 'Unknown RemotePlayer' no-ops in single-player). payload[0]
    stays 0xDA so a CORRECT dispatch still hits the 218 handler, which only reads
    offsets 1/5/9 (Size!=0x19) -> all within 15 bytes, identical effect to Size 17.
    build_ingame_pkt sends Size==n exactly: n=15 -> bc=0, T=0xf2 (T>>4=15, low nibble
    2 = appspace-data channel)."""
    return build_ingame_pkt(bytes([0xDA, 0x01]) + bytes(13))

def build_e1_pilot_list(pilots):
    data = bytearray([0xe1])
    for (name, _slot) in pilots:
        data.extend((name.encode() if isinstance(name,str) else name) + b'\x00')
    pl = build_appspace_pkt(bytes(data)); bc = pl[0]
    log('PILOTS', f'{len(pilots)} pilot(s) bc={bc}(p3={bc*16+1}): {[n for n,_ in pilots]}')
    return pl

def build_empty_room_list(sub_cmd):
    return build_appspace_pkt(bytes([sub_cmd]))

def build_ce_room_list(rooms):
    """Build 0xce AppSpaceList response.

    0xce = AppSpaceList = PLAYER/SQUADRON PRESENCE list, NOT the arena/room list.
    Evidence: sending GAME_DEF bytes via 0xce causes FA.exe to:
      - Parse them as player/squad records
      - Send sub=0xd7/0xd9 packets with IDs extracted from our GAME_DEF
      - Populate the Squadrons tab with faction names
      - NEVER add a room to the arena list
    Empty 0xce (just the byte) = correctly represents "0 players in lobby".
    TODO: find which sub-command (0xca ServerList? 0xcb GameList?) holds the room list.
    Ghidra targets: FUN_006ace60, FUN_0070f940, XREF to ArenaSt (0x00a59ad8),
                    RECEIVER<EVENT_LOBBY_CREATE_ONE_GAME_ARENAS_INFO> at 0x00bf9c98.
    """
    return build_appspace_pkt(bytes([0xce]))  # empty = 0 lobby players

# --- 0xcb GameList (ARENA LIST) - experimental, switchable --------------------
#
# Confirmed via Ghidra this session:
#   FUN_004f03b0  : client sends bare [0xcb] on lobby entry = GameList request.
#   FUN_0070eda0  : displays ArenasInfo (LobbyDialogsInitPars+0xa0), 40B entries,
#                   renders the string at entry+8.
#   FUN_006ad210  : ArenasInfo::operator[]  -> base+index*0x28.
#   FUN_006af980  : JOIN reads ArenaSt[+4]=GameIndex, ArenaSt[+0xc]=GameDef(0 OK).
#   FUN_0076bd00  : finds ArenaSt by matching [+4]==GameIndex.
# In-memory ArenaSt: [+0]type [+4]GameIndex [+8]name [+0xc]GameDef(optional).
#
# The WIRE format of the 0xcb RESPONSE (what the receive-parser converts into
# those 40B records) is the one thing we could NOT pin from decompilation, so
# this builder offers several candidates. Flip GAMELIST_FORMAT and re-test.
#
# GameIndex convention observed for room CREATION echoes:
#   bytes[2:6] = [0x00][0xff][0xff][name[0]]  ->  e.g. "Test1" -> 0x54ffff00.
# We reuse that here so a listed arena's GameIndex matches what Join expects.

GAMELIST_FORMAT = 'empty'   # 0xcb is the LOBBY PLAYER list, not arenas - keep empty until handled separately

def _arena_gameindex(name, room_id=0):
    """GameIndex as FA derives it for a room: 4 LE bytes [room_id&0xff][ff][ff][name[0]].
    name[0] is the MSB (it overlaps the creator-name field in the room echo). The LOW
    byte - a fixed 0x00 before 2026-06-29 - now carries room_id, so two rooms whose
    creators share a first letter no longer collide on the GameIndex. room_id=0
    reproduces the legacy value, kept as a resolution fallback in _find_room_by_gidx."""
    first = (name.encode()[:1] or b'\x00')[0]
    return bytes([room_id & 0xff, 0xff, 0xff, first])   # 4 bytes, little-endian on wire

def build_gamelist(rooms):
    """Build the 0xcb GameList (arena list) response.

    `rooms` = rows from db_get_open_rooms():
        (room_id, room_name, creator_pilot, account_name, created_at, room_slot, game_def_raw)
    """
    fmt = GAMELIST_FORMAT
    data = bytearray([0xcb])

    if fmt == 'empty' or not rooms:
        log('GAMELIST', f'0xcb -> empty ({len(rooms)} rooms, fmt={fmt})')
        return build_appspace_pkt(bytes([0xcb]))

    if fmt == 'byte_name':
        # CONFIRMED by decompiling the 0xcb receive parser (FUN_004ef8b0):
        #   payload = [0xcb] then, per arena, [1 byte id][name + NUL].
        # The parser reads pkt[1]=id (-> ArenaSt+4 / GameIndex via FUN_004ed150),
        # then scans the name to its NUL (-> ArenaSt+8, the displayed field),
        # advancing strlen+2 per record; it stops on an empty name (so trailing
        # zero padding is a safe terminator). The leading byte is irrelevant for
        # display, so we use a 1-based arena index here.
        for i, r in enumerate(rooms, start=1):
            nm = (r[1] or 'Arena')
            data.append(i & 0xFF)                  # 1-byte id (non-zero)
            data.extend(nm.encode()[:31] + b'\x00')  # name + NUL

    elif fmt == 'names':
        # FA's proven list convention (cf. 0xe1 pilot list): just concatenated
        # null-terminated names, no count, no index. Client assigns indices.
        for r in rooms:
            nm = (r[1] or 'Arena')
            data.extend(nm.encode()[:31] + b'\x00')

    elif fmt == 'idx_name':
        # Per arena: [GameIndex 4B LE][name \0]
        for r in rooms:
            nm = (r[1] or 'Arena')
            data.extend(_arena_gameindex(nm))
            data.extend(nm.encode()[:31] + b'\x00')

    elif fmt == 'count_idx_name':
        # [count 1B] then [GameIndex 4B][name \0] per arena
        data.append(len(rooms) & 0xFF)
        for r in rooms:
            nm = (r[1] or 'Arena')
            data.extend(_arena_gameindex(nm))
            data.extend(nm.encode()[:31] + b'\x00')

    elif fmt == 'fixed40':
        # Mirror the in-memory 40B ArenaSt minus the vtable:
        #   [+0:4]=0  [+4:8]=GameIndex  [+8:0x28]=name padded to 32B
        for r in rooms:
            nm = (r[1] or 'Arena')
            rec = bytearray(40)
            rec[4:8] = _arena_gameindex(nm)
            nb = nm.encode()[:31]
            rec[8:8+len(nb)] = nb
            data.extend(rec)

    else:
        log('GAMELIST', f'unknown GAMELIST_FORMAT={fmt!r}, sending empty')
        return build_appspace_pkt(bytes([0xcb]))

    pkt = build_appspace_pkt(bytes(data))
    bc = pkt[0]
    names = [ (r[1] or 'Arena') for r in rooms ]
    log('GAMELIST', f'0xcb -> {len(rooms)} arena(s) fmt={fmt} '
                    f'payload={len(data)}B bc={bc}(p3={bc*16+1}): {names}')
    log('GAMELIST', f'0xcb payload hex: {bytes(data).hex()}')
    return pkt

# --- 0xd2 ARENA LIST (THE REAL ONE) -------------------------------------------
#
# CONFIRMED this session via the real 2009 capture (messages04.log) + Ghidra:
#   * Real lobby prefetch: 0xce(squadrons) 0xca(news) 0xcb(lobby players) then
#     out 210'1 -> in 210'1110  <- the 1110-byte ARENA/ROOM LIST.
#   * handler[0xd2] = FUN_004efda0 parses it and fires PTR_LOOP_00bfe95c, which is
#     the arena dialog's receiver (FUN_0076e8b0 param_1[3], vtable 0xaa9658) ->
#     writes the displayed arena vector (LobbyDialogsInitPars +0xa8) that
#     FUN_0070eda0 renders. So 0xd2 IS the arena tab's list.
#   * The Arenas tab issues NO query on click - it renders this prefetch data and
#     receives live 0xcc(204) updates afterward.
#
# Record format (from the FUN_004efda0 parse loop):
#   [0xd2] then per room:
#       [12-byte header]   - only header[+4:+8] = GameIndex is read by the parser
#       [name1 \0]         - primary name (FUN_007ed210(pcVar10) -> displayed)
#       [name2 \0]         - second string (host/owner column)
#   Stride = 12 + len(name1)+1 + len(name2)+1; loop stops on empty/over-length,
#   so trailing zero padding terminates safely.
#
# GameIndex must match what JOIN expects. FA derives a created room's GameIndex as
# bytes[2:6] of the 0xdc create = [00 ff ff creator[0]] (e.g. "Test1" -> 0x54ffff00),
# so we reuse that here keyed on the creator pilot.

# Per-arena terrain now comes from the DB (extracted from each room's GAME_DEF at
# creation). ARENA_TRN_NUMBER is only the fallback when a row somehow lacks one.
ARENA_TRN_NUMBER = DEFAULT_TERRAIN

def build_arenalist(rooms):
    """Build the 0xd2 arena/room list response (the Arenas tab's list)."""
    data = bytearray([0xd2])
    if not rooms:
        log('ARENALIST', f'0xd2 -> empty (0 rooms)')
        return build_appspace_pkt(bytes([0xd2]))
    listed = []
    records = []
    for r in rooms:
        room_name = (r[1] or 'Arena')
        creator   = (r[2] or room_name)          # pilot who created the room
        gamedef = bytes(r[6]) if len(r) > 6 and r[6] else b''
        trn      = extract_terrain_from_gamedef(gamedef) & 0xFF    # param[0x39]; 1..99
        planeset = 0                                              # desc+0x04; 0 = default Planes.txt
        # 12-byte record header - field->descriptor map PROVEN from FUN_004efda0
        # disassembly (the register loads feeding FUN_004ef130->FUN_004ed040):
        #   [+0:4]  *(rec+0)        -> desc+0x04  PLANE-SET (validated by FUN_004c2b60)
        #   [+4:4]  GameIndex       -> desc+0x08  (also the uVar2 key; matches Join)
        #   [+8]    flag byte: bit0->desc+0x10, bit1->desc+0x14, bit2->desc+0x20
        #   [+9:2]  ushort          -> desc+0x18
        #   [+11]   HIGH byte of the +8 dword -> desc+0x1c  TERRAIN (_TrnNumber) *
        hdr = bytearray(12)
        hdr[0:4]  = (planeset & 0xFFFFFFFF).to_bytes(4, 'little')  # plane-set (default)
        hdr[4:8]  = _arena_gameindex(creator, r[0])                     # [00 ff ff creator[0]]
        hdr[8]    = 0                                             # flag bits (none)
        hdr[9:11] = (0).to_bytes(2, 'little')                     # desc+0x18 (unused)
        hdr[11]   = trn                                           # TERRAIN -> desc+0x1c *
        # Name slots (empirically, from v167 live test): the FIRST name is the
        # category/section HEADER the client groups rows under; the SECOND name is
        # the arena's own row label. So name1 = category, name2 = the room's name.
        category = (r[8] if len(r) > 8 and r[8] else 'Custom Arenas')   # name1 section header (web-editable)
        records.append((bytes(hdr), category.encode()[:31], room_name.encode()[:31]))
        listed.append((room_name, trn))
    # Assemble. The 0xd2 parser (FUN_004efda0) is length-driven - it keeps starting
    # new records until consumed >= len, with NO bounds check, so leftover zero pad
    # would spawn a phantom record and read past the buffer -> crash. build_appspace_pkt
    # frames to bc*16+1, so the LAST record must absorb the pad. Pad name2 (the arena's
    # DISPLAY label), NOT name1: name1 is the CATEGORY the client groups rows under, and
    # any trailing spaces on it make an otherwise-identical category compare unequal, so a
    # shared group (e.g. two 'Dogfighting' arenas) splits into a duplicate 'Dogfighting   
    # Arenas' header. Trailing spaces on name2 are display-only and invisible in the list.
    def _assemble(extra_pad):
        d = bytearray([0xd2])
        last = len(records) - 1
        for i, (hdr, cat, arena) in enumerate(records):
            d.extend(hdr)
            d.extend(cat + b'\x00')                       # name1 = CATEGORY (grouping key) - keep clean
            if i == last and extra_pad > 0:
                d.extend(arena + (b'\x20' * extra_pad) + b'\x00')   # pad the DISPLAY label instead
            else:
                d.extend(arena + b'\x00')
        return d
    d0 = _assemble(0)
    L  = len(d0)
    bc = 0 if L <= 1 else (L - 1 + 15) // 16
    size = bc * 16 + 1
    pad = size - L
    data = _assemble(pad)
    pkt = build_appspace_pkt(bytes(data)); bc = pkt[0]
    desc = [f'{n}(trn{t}:{TERRAIN_NAMES.get(t, "?")})' for n, t in listed]
    log('ARENALIST', f'0xd2 -> {len(rooms)} arena(s) payload={len(data)}B '
                     f'bc={bc}(p3={bc*16+1}) pad={pad}: {desc}')
    log('ARENALIST', f'0xd2 payload hex: {bytes(data).hex()}')
    return pkt

# --- 0xd4 / 212  GAME_DEF push (v164 experiment) ------------------------------
#
# The 0xd2 list record carries ONLY GameIndex + 2 names; the parser never sets the
# descriptor's terrain field (desc+0x1c stays 0 -> _TrnNumber>=1 assert at tab-open).
# Terrain lives in the arena's GAME_DEF (a packed BINARY blob, NOT INI text - the
# client pretty-prints it as Terrain=N). The 212 handler FUN_004ed9c0 reads the
# message as [0xd4][LobbyIndex:4 != 0][binary blob], then FUN_0057f390 deserialises
# the blob into the arena object (incl. terrain). Hypothesis: the list display
# resolves each arena's terrain from a GAME_DEF the client has cached, keyed by
# GameIndex. A server arena this client never selected was never cached -> terrain 0
# -> crash. So push the stored GAME_DEF as a 212 (same GameIndex as the 0xd2 record)
# BEFORE the list, so the arena - with its real terrain - is cached first.
def build_gamedef_212(room):
    """[0xd4][GameIndex:4][LZ GAME_DEF] as an APPSPACE packet, EXACT bc*16+1 size.
    The stored blob is LZ-compressed at a size (==4 mod16) that can't sit on the
    bc*16+1 grid. We decompress it and RE-ENCODE it as an all-literals LZ stream whose
    size we control (comment pad) so the 212 payload lands exactly on bc*16+1 - no
    over-read, valid version byte, parser consumes the whole decompressed buffer."""
    creator = (room[2] or room[1] or 'Arena')
    gidx    = _arena_gameindex(creator, room[0])          # 4 bytes [00 ff ff creator[0]] (non-zero)
    blob    = bytes(room[6]) if len(room) > 6 and room[6] else b''
    comp, D, pad = build_lz_gamedef(blob, planeset_for_room(room),
                                    force_ffa=(FFA_NEUTRAL_GUARD and is_ffa_room(room)),
                                    plane_camp=plane_camp_for_room(room),
                                    arena_settings=db_get_room_settings(room[0]))
    if comp is None:
        log('GAMEDEF212', f'LZ build failed for room {room[0]}; skipping 212')
        return None
    payload = bytes([0xd4]) + gidx + comp
    n = len(payload); bc = 0 if n <= 1 else (n - 1 + 15) // 16
    log('GAMEDEF212', f'212 LZ gidx={gidx.hex()} decompressed={D}B pad={pad} '
                      f'comp={len(comp)}B name={room[1]!r} payload={n}B bc*16+1={bc*16+1} '
                      f'{"ALIGNED" if n==bc*16+1 else "MISALIGNED!"}')
    return build_appspace_pkt_exact(payload)

def build_join_game_answer_201(client_number=0, player_index=0):
    """FA message 201 (0xc9) = VNET::JoinToGameAnswer - the server's grant in reply to
    the client's SendEnterToGame (200/0xc8). Decoded from handler FUN_004f88f0
    (VNET::JoingToGameAnswerCB), dispatch slot _DAT_00c821fc (id 201):
        [0xc9][ClientNumber:4 LE signed][PlayerIndex:4 LE signed]   (read at +1 and +5)
    ClientNumber >= 0 AND PlayerIndex >= 0  ->  client allocates its client+player
    objects, sets DAT_00bfedb4=ClientNumber (clears the 0xfffffffe 'entering' state),
    sends 0x41, sets DAT_00c82eb0=0 (STOPS the 0x43 poll) and DAT_00c82348=1 (game
    active). ClientNumber < 0  ->  'not granted, keep polling' (what our 0x43 confirm
    effectively signalled). Handler reads fixed offsets, so bc*16+1 zero-pad is fine."""
    payload = (bytes([0xc9])
               + (client_number & 0xFFFFFFFF).to_bytes(4, 'little')
               + (player_index  & 0xFFFFFFFF).to_bytes(4, 'little'))
    log('JGA201', f'JoinToGameAnswer ClientNumber={client_number} PlayerIndex={player_index} '
                  f'payload={payload.hex()}')
    return build_appspace_pkt(payload)


# -- IN-ARENA CHAT (msg 20 / 0x14) ----------------------------------------------
# Decoded from the message-20 dispatch handler FUN_004f6030 (lobby builder
# FUN_004f1490 installs it at slot _DAT_00c81f28). The handler:
#   iVar6 = GetPlayer(*(param_1+2))          ; PlayerIndex at +2 (4 bytes, LE)
#       if 0  ->  "ChatMessage from unknown player with PlayerIndex=%i" + drop
#   channel = *(param_1+1)                   ; +1
#       3      ->  FUN_0046a420(0,0xd,"%s: %s", name, text)            (plain)
#       4      ->  uppercase(text) then same + sound                  (shout)
#       0/1/2  ->  team/squadron-coloured "%s: %s", BUT only if player+0x1c != 0;
#                 squad colour looked up from *(param_1+6) (SquadronId)
#   text = param_1+10
# So the DISPLAY wire form (what the client renders) is:
#       [0x14][channel:1][PlayerIndex:4 LE][SquadronId:4 LE][text\0]
# i.e. the SEND form [0x14][channel][text\0] with an 8-byte PlayerIndex+SquadronId
# inserted after the channel. Our old blind echo left the text where PlayerIndex
# should be, so the handler read "Hell" (0x6C6C6548) as the index -> unknown player.
# We stamp PlayerIndex=0 - the player allocated by the 201 grant - so it resolves to
# the local pilot ("Test1").

def build_chat_display_20(channel, text, player_index=0, squadron_id=0):
    """Build the DISPLAY form of msg 20 so the client renders a chat line."""
    if isinstance(text, str):
        text = text.encode('ascii', 'replace')
    text = text.split(b'\x00')[0]  # stop at first NUL - drop any trailing wrapper bytes
    payload = (bytes([0x14, channel & 0xFF])
               + (player_index & 0xFFFFFFFF).to_bytes(4, 'little')
               + (squadron_id  & 0xFFFFFFFF).to_bytes(4, 'little')
               + text + b'\x00')
    return build_appspace_pkt(payload)


def reflect_chat_20(s, channel, text, player_index=0):
    """Reflect an in-arena chat so it renders in the chat pane. Recipients are scoped to
    the SENDER's room (multi-room isolation) and, for team/squadron channels, further to
    same-side / same-squad players: channel 0=all (whole room), 1=team (same nation),
    2=squadron (same squad - squad tracking TODO, currently sender only). The line is
    stamped with the SENDER's PlayerIndex so every recipient resolves it to the sender's
    name via FUN_004f6030's GetPlayer."""
    if isinstance(text, (bytes, bytearray)):
        disp = text.split(b'\x00')[0].decode('ascii', 'replace')
    else:
        disp = str(text)
    room = s.current_room
    room_players = get_sessions_in_room(room) if room is not None else []
    if channel == 1:
        targets = [x for x in room_players if x.nation == s.nation]
    elif channel == 2:
        targets = [s]                       # squadron membership not modelled yet
    else:
        targets = list(room_players)        # channel 0 = whole room
    if s not in targets:
        targets.append(s)
    if not targets:
        targets = [s]
    pkt = build_chat_display_20(channel, text, player_index=s.player_index)
    log('CHAT20', f'reflect ch={channel} {disp!r} from PI={s.player_index} '
                  f'-> {len(targets)} player(s) in room {room}')
    for sess in targets:
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt,
                         f'<- chat-20 ch={channel} {disp!r}', to=3.0), daemon=True).start()

def build_arena_players_213(room, counts=None, names=None):
    """FA message 213 - arena player info, the reply to the client's 'out 213' request.
    Layout decoded from incoming-213 handler FUN_004ef6e0:
        [0xd5][GameIndex:4][8 x uint16 per-nation counts]   (header = 0x15 = 21 bytes)
        then a length-driven list of [player_name\\0] (the arena roster).
    The 8 uint16s at +5..+0x13 are pushed to observers as per-nation player tallies
    (the Nations-list counts). local_30 (GameIndex) must be non-zero or the handler
    no-ops. Sent at EXACT length (no bc*16+1 zero pad) so the roster loop ends on the
    wire length - zero padding would be parsed as phantom empty-name players."""
    creator = (room[2] or room[1] or 'Arena')
    gidx = _arena_gameindex(creator, room[0])                         # 4 bytes, non-zero
    counts = (list(counts) if counts else [0] * 8)[:8]
    while len(counts) < 8:
        counts.append(0)
    payload = bytearray([0xd5]) + gidx
    for c in counts:
        payload += int(c & 0xFFFF).to_bytes(2, 'little')     # 8 ushorts = 16 bytes
    # COUNTS ONLY - no trailing strings. Re-RE of the incoming-213 handler
    # (FUN_004ef6e0) shows the strings after +0x15 are NOT a roster: each NUL-string
    # (budgeted strlen+1+2) is appended to a UI list - and that list renders in the
    # arena-selection page's "Combat Action" box. Our invented roster is exactly the
    # "player names + corrupt strings" bug (the per-record trailing bytes, e.g.
    # nation=0xff, parsed as 1-char garbage strings). Per-nation grouping comes from
    # the 8 counts above, not from names here. Until we emulate real combat-action
    # lines, send counts only; bc-grid zero padding may yield blank entries at most.
    if names:
        log('ARENA213', f'NOTE: roster names suppressed (combat-action box): {names}')
    log('ARENA213', f'213 gidx={gidx.hex()} counts={counts} (counts-only) '
                    f'payload={len(payload)}B')
    return build_appspace_pkt_exact(bytes(payload))

# -- PLAYER-OBJECT LAYER (msgs 62 / 63 / 96) ------------------------------------
# Decoded from FA.exe VNet_Rcv.cpp handlers (dispatch table FUN_004f1490):
#   msg 62 (0x3e) -> FUN_004fa5f0  "Add existing REMOTE_PLAYER %s PlayerIndex=%i"
#   msg 63 (0x3f) -> FUN_004fa9c0  ChangePlayerCB (op=add/remove/change-camp)
#   msg 96 (0x60) -> FUN_004f53b0 -> FUN_00629600  SCORE_TABLE (ScoreTable.cpp)
#
# CRITICAL FRAMING - THE bc*16+1 OVER-DELIVERY BUG (root cause of every CTD v182-v186):
# The client's appspace layer does NOT deliver the exact datagram length to message
# handlers. It delivers Length = bc*16+1, where bc is the block count in the vcnc
# header. PROVEN by the client trace (vcncnet...510.log) for our 8-byte msg 63:
#     ProcessMessages(256) Cmd=0 Size=17
#     Receiving Message 0 - Data: 3f 00 00 00 00 00 00 01 | 00 00 00 8a 00 00 00 00 e6
# Our 7-byte record, then 9 bytes of STALE RECEIVE-BUFFER GARBAGE (here the head of
# the prior 212 stream: 8a 00 00 ...). All three handlers (62 FUN_004fa5f0,
# 63 FUN_004fa9c0, 96 FUN_00629600) are length-driven record loops that parse until
# Length runs out and then assert "Length>=0" at severity 0xffffffff (fatal). The
# garbage tail is parsed as phantom records; the final partial record drives Length
# negative -> assertion -> DLL_PROCESS_DETACH ~2s later. This - NOT use-after-free,
# NOT premature world state - was the killer in every player-object crash.
#
# THE RULE: a length-driven payload MUST TILE EXACTLY to bc*16+1, i.e.
# len(payload) % 16 == 1, with the padding forming PARSER-VALID, side-effect-free
# records. build_appspace_pkt_exact is a no-op fiction here (the client ignores the
# real length); each builder below pads itself to the bc*16+1 boundary:
#   63: pad to a multiple of 16 fixed records with dummy PlayerIndex (lookup fails ->
#       "Unknown RemotePlayer" log -> skipped, zero side effects).
#   62: pad the LAST record's trailing (unused, scanned) string - absorbs 0..15B.
#   96: append one pad group whose count tiles the remainder (7 is invertible mod 16);
#       it writes zero score-defs at a high object-type base -> harmless.
#
# DEPENDENCY CHAIN (the actual player-object lifecycle):
#   62 creates the REMOTE_PLAYER object  ->  63 sets its Camp()/side (player+0x2c)
#   ->  96 feeds the scoreboard.  v175's guess that the 121-byte msg 58 set side
#   membership was WRONG: msg 58 (FUN_004eff50, LobbyRcv.cpp) is a LOBBY 3-byte-record
#   list, not the in-arena side-setter. Side membership is msg 63 op=change-camp.

def _pad_to_bc_boundary_len(payload_len):
    """Return how many bytes to add so payload_len becomes == 1 (mod 16) = bc*16+1."""
    return (1 - payload_len) % 16

MSG_ADD_PLAYER_62      = 0x3e
MSG_CHANGE_PLAYER_63   = 0x3f
MSG_SCORE_TABLE_96     = 0x60
MSG_ACE_RANK_88        = 0x58   # v218: AceOrRankChangedCB (VNET table 0xc81ed8 slot 88).
MSG_SERVER_CONFIRM_5   = 0x05    # in-game ServerConfirm (post-takeoff sim-loop gate)
SERVERCONFIRM_READY    = True    # build_ingame_pkt (floored bc) -> client Size=5 -> 1 record
ADD_TEST_PLAYER        = False   # was True (fake Test2 roster test). OFF now: with a REAL
                                 # 2nd client it would collide on PlayerIndex 1 and add a
                                 # phantom. Re-enable only for solo roster tests.

# msg 63 ChangePlayerCB ops (the per-record op byte at record+6):
# msg 63 ChangePlayerCB ops (the per-record op byte at record+6). Decoded from the
# branch structure of FUN_004fa9c0: after the player is found by index,
#     if (iVar12 == 1) -> CAMP path: writes rp->Camp() at player+0x2c
#     else (any op != 1) -> DELETE path: FUN_007fca00 + free(player object)
# v182 SHIPPED THESE INVERTED (CAMP=2) -> op=2 hit the delete path and freed a live
# player object -> crash-to-desktop on side-select (messages07.log, WinError 10054).
CP_OP_CAMP   = 1     # iVar12==1 -> change-camp (set side); the ONLY op that sets +0x2c
CP_OP_REMOVE = 0     # any op != 1 -> delete the remote player object (we use 0)

def build_add_player_62(records):
    """FA msg 62 (0x3e) - Add existing REMOTE_PLAYER (handler FUN_004fa5f0).
    Per-record wire layout (decompiled record stride):
        [PlayerIndex:4 LE][side:1][reserved:1][name\\0][str2\\0]
    The handler reads PlayerIndex at +0, side at +4 (masked &0xf, valid 0..8 else
    0xffffffff), a byte at +5, then a NUL-terminated name at +6, then a SECOND
    NUL-terminated string (scanned but unused for our purposes - send empty).
    `records` = list of (player_index, side, name). side None -> 0xff (unassigned).
    Sent at EXACT length - see CRITICAL FRAMING note above.

    *** INVARIANT: a 62 sent to client X must NEVER contain X's own PlayerIndex. ***
    The msg 201 grant handler (FUN_004f88f0) already creates the LOCAL player's entry
    in the same table (FUN_004f3230, camp=-1, local pilot name). A 62 record for an
    existing index takes the "Add existing REMOTE_PLAYER" path: delete + free + re-add.
    For the local index that would free the live local player while the GamerClient
    (DAT_00c6eb98+0x128) still points at it. (NOTE: the v185 self-62 CTD was ALSO
    caused by bc*16+1 framing garbage - see v187 - but this delete+re-add hazard is
    real independent of framing, so the invariant stands. Peers only.)"""
    data = bytearray([MSG_ADD_PLAYER_62])
    for pi, side, name in records:
        sb = 0xff if side is None else (side & 0xff)
        nb = (name.encode('ascii', 'replace') if isinstance(name, str) else name)
        data += (pi & 0xFFFFFFFF).to_bytes(4, 'little')
        data += bytes([sb, 0x00])
        data += nb + b'\x00'      # name
        data += b'\x00'           # str2 (empty, NUL-terminated)
    # TILE to bc*16+1 (see CRITICAL FRAMING): the handler scans str2 to its NUL, so
    # we can grow the LAST record's str2 with filler bytes before its terminator
    # without adding a phantom record. Remove the lone terminator we just wrote,
    # insert `pad` filler bytes, then re-terminate.
    pad = _pad_to_bc_boundary_len(len(data))
    if pad:
        data = data[:-1] + (b'\x20' * pad) + b'\x00'   # spaces inside str2, then NUL
    assert len(data) % 16 == 1, f'62 framing {len(data)} !==1 mod16'
    log('PLAYER62', f'AddPlayer {len(records)} rec(s) (pad={pad}): '
                    f'{[(pi, sd, (n if isinstance(n,str) else n.decode("ascii","replace"))) for pi,sd,n in records]}')
    return build_appspace_pkt_exact(bytes(data))

# Dummy PlayerIndex for 63 padding records: a value the client's player table will
# never contain, so FUN_007fcac0 lookup fails -> "Unknown RemotePlayer(%i)" log ->
# record skipped with ZERO side effects (no add, no delete, no camp write).
DUMMY_PLAYER_INDEX = 0xFFFFFFFE

MSG63_TRUE_LENGTH = True   # send msg-63 as the real 'in 63'8' (true-length in-game framing).
                           # Set False to fall back to the legacy bc*16+1 padded form.
def build_change_player_63(records):
    """FA msg 63 (0x3f) - ChangePlayerCB (handler FUN_004fa9c0). Fixed 7-byte records:
        [PlayerIndex:4 LE][side:1][reserved:1][op:1]
    op (record+6), from the handler's branch structure after the player is found:
        op == 1  -> CHANGE-CAMP: writes rp->Camp() (player+0x2c) to `side` (masked &0xf).
                   This is the message that moves a player between nation groups.
        op != 1  -> DELETE: frees the remote player object (FUN_007fca00 + free).
    An unknown PlayerIndex logs "Unknown RemotePlayer(%i)" and is skipped - so the
    target must already exist (via the 201 grant for self, or a peer's 62), and must
    NOT be the recipient's own index for a delete op.
    `records` = list of (player_index, side, op).

    FRAMING - TRUE LENGTH (the 2009 'in 63'8' form, fully reverse-engineered):
      The handler is dispatched with (body, length); it reads the msg-id byte then loops
      `while length > 0` consuming 7 bytes/record. The client derives `length` from the
      packet size, which vcncNet computes as  Size = bc*16 + (T>>4)  (bc = appspace header
      byte 0, T = byte 1).  build_appspace_pkt_exact HARDCODES T=0x12, pinning Size's low
      nibble to 1 - so an 8-byte 1-record 63 arrived as Size=17 ('in 63'17'), the loop
      over-read into 2+ records, and we had to pad to 16 records with DUMMY(-2) entries.
      Cost of that workaround: 15 phantom 'Unknown RemotePlayer(-2)' operations PER roster
      change - something the real 2009 server (always 'in 63'8', 1306x, zero -2 errors) never
      did, and the leading suspect for the cumulative in-flight freeze.
      build_ingame_pkt encodes the EXACT size instead:  bc=n>>4, T=((n&0xf)<<4)|2.  For a
      1-record 63 (n=8): bc=0, T=0x82 -> Size = 0*16+8 = 8 -> 'in 63'8' -> handler reads exactly
      one 7-byte record, 0 leftover. No padding, no phantom records. Multiple real records
      still work (n = 1 + 7*k stays exact). Size bound: the client caps at 5000, far above
      any real roster."""
    recs = list(records)
    n = len(recs)
    data = bytearray([MSG_CHANGE_PLAYER_63])
    for pi, side, op in recs:
        sb = 0xff if side is None else (side & 0xff)
        data += (pi & 0xFFFFFFFF).to_bytes(4, 'little')
        data += bytes([sb, 0x00, op & 0xff])
    if MSG63_TRUE_LENGTH:
        # true-length in-game framing - the real 'in 63'<len>' form, no dummy padding
        log('PLAYER63', f'ChangePlayer {n} real rec(s) [true-len {len(data)}B]: {records}')
        return build_ingame_pkt(bytes(data))
    # ---- legacy fallback: pad to a multiple of 16 records (bc*16+1 grid) ----
    target = ((n + 15) // 16) * 16 if n else 16
    while len(recs) < target:
        recs.append((DUMMY_PLAYER_INDEX, None, 0))
    data = bytearray([MSG_CHANGE_PLAYER_63])
    for pi, side, op in recs:
        sb = 0xff if side is None else (side & 0xff)
        data += (pi & 0xFFFFFFFF).to_bytes(4, 'little')
        data += bytes([sb, 0x00, op & 0xff])
    assert len(data) % 16 == 1, f'63 framing {len(data)} !==1 mod16'
    log('PLAYER63', f'ChangePlayer {n} real + {target - n} pad rec(s) [legacy]: {records}')
    return build_appspace_pkt_exact(bytes(data))

def build_server_confirm_5(number, ident=0):
    """FA msg 5 - ServerConfirm (wire handler FUN_007e5030, in-game dispatch idx 5 @
    table 0xcbc190+0x14). THE post-takeoff gate: the client registers its plane locally
    with a per-client monotonic IDENT (0 for its first object), sends its full state
    (out 4'33), then blocks until the server stamps a global object NUMBER onto it -
    only then does the sim loop ('out 6') start. Missing it = the ~20s flight freeze.

    Wire: [0x05] then N x [Number:u16 LE][ident:u16 LE]; 'in 5'5' = exactly 1 record.
    FUN_007e5030 finds the local object whose registration ident == `ident`, asserts its
    NumberVar==-1, sets NumberVar=Number + ClientVar=own-id, then fires the object's
    OnConfirm (FUN_00427690 -> logs 'ServerConfirm. Client=%i, Number=%i', sets
    DAT_00bfedb8=Number). Number<0 OR ident-not-found -> the client DELETEs instead, so
    Number must be a valid non-negative u16 and `ident` must match a live local object.
    Sent BYTE-EXACT via build_ingame_pkt: n=5 -> bc=0 -> client Size=max(1,5)=5 ->
    (5-1)/4 = exactly 1 record. (build_appspace_pkt_exact's CEIL bc would give bc=1 ->
    Size=17 -> 4 records -> 3 dummy confirms -> 'not found, send delete' / assert -> CTD.)"""
    data = bytes([MSG_SERVER_CONFIRM_5]) + struct.pack('<HH', number & 0xFFFF, ident & 0xFFFF)
    return build_ingame_pkt(data)

def build_add_player_62(records):
    """FA msg 62 (0x3e) - AddPlayer / REMOTE_PLAYER (handler FUN_004fa5f0, VNET table
    0xc81ed8 slot 62). Adds remote players to the in-game ROSTER/scoreboard (not a 3D
    object - that's msg 2). Per-record wire format, looped until Length consumed:
        [PlayerIndex:u32 LE][camp:u8][field:s8][name:asciiz]
    record size = 7 + len(name). camp 0-8 valid (handler does camp & 0xf; >=9 -> camp=-1).
    FUN_004fa5f0 looks the player up by PlayerIndex, allocates a 0x24-byte REMOTE_PLAYER
    (FUN_004f3230(idx,camp,field)), sets the name, and fires the roster/announce UI
    (logs 'Add existing REMOTE_PLAYER %s' if the index already exists). Verified vs real
    log: in 62'18 = [0x3e]+17B rec = 7+10-char name; in 62'24 = 7+16.
    `records` = [(player_index, camp, name[, field]), ...]. Returns the raw msg-62
    sub-message bytes (type+records) for wrapping in a msg 13 batch."""
    data = bytearray([0x3e])                                  # MSG_ADD_PLAYER_62
    for rec in records:
        pidx, camp, name = rec[0], rec[1], rec[2]
        if camp is None:
            # v260: a player who hasn't picked a side. Sending camp=0 encoded them as US, so no-team
            # players showed under US in every peer's roster until they chose a team (Bug A). The
            # handler FUN_004fa5f0 maps camp>=9 -> camp=-1 (no side), which is the SAME 'In Menu'
            # encoding the client gives its own local entry at grant (FUN_004f88f0, camp=-1). So send
            # 0xff -> the peer shows them as neutral/In Menu, not US. msg 63 still sets the real side.
            camp = 0xff if ADD_PLAYER_NOTEAM_NEUTRAL else 0
        field = rec[3] if len(rec) > 3 else 0
        nb = name.encode('latin1', 'replace')[:31] + b'\x00'  # asciiz, capped
        data += struct.pack('<I', pidx & 0xFFFFFFFF)
        data += bytes([camp & 0xff, field & 0xff])
        data += nb
    return bytes(data)

def build_msg13(*submsgs):
    """FA msg 13 (0x0d) - the sim-conductor BATCH CONTAINER (handler LAB_007e3230 @
    0x7e3230). Wraps N sub-messages, each as [len:u16 LE][submsg: type+data, `len` bytes];
    the client then dispatches each one through the normal tables exactly as if received
    standalone (type<0x14 -> in-game 0xcbc190, else VNET 0xc81ed8). This is the literal
    '{ ... }' group in the real log - e.g. in 13'132 = 1 + (2+18) + (2+24) + (2+83) {62,62,2}.
    Each arg is the raw type+data of one sub-message (e.g. from build_add_player_62).
    Framed BYTE-EXACT via build_ingame_pkt so the client's Size == the real byte count."""
    data = bytearray([0x0d])                                  # MSG_SIM_BATCH_13
    for sm in submsgs:
        data += struct.pack('<H', len(sm))                    # sub-message length prefix
        data += sm
    return build_ingame_pkt(bytes(data))

def build_score_table_96(nation_scores=None, object_groups=None):
    """FA msg 96 (0x60) - SCORE_TABLE (FUN_004f53b0 -> FUN_00629600, ScoreTable.cpp).

    *** SEND ONLY ON REQUEST (bare inbound 0x60) - NEVER UNSOLICITED AT ENTRY ***
    v183 sent this on the 201 grant and crashed arena-join (messages08.log): the
    handler frees+reallocates the host-side score-table object before the client's
    world is stood up (~3s stall -> WinError 10054). The client REQUESTS the table
    with a bare 0x60 right after the FLY 23 StartPlace grant (messages09.log) -
    answer it then, and only then.

    The dispatch handler FUN_004f53b0 passes (payload+1, len-1) to FUN_00629600, which
    reads its buffer starting at the VERSION byte:
        [0x60][version=0x02][7 x uint16 LE tallies]   (handler buffer = version-first)
    so on the wire, immediately after the 0x60 msg-id comes version 0x02, then the 7
    ushorts (param_1[0..6]). version MUST be 2 or the client asserts
    "Wrong SCORE_TABLE version". Header total = 1(id)+1(ver)+14 = 16 bytes.
    Then a length-driven list of object-score groups; each group:
        [base_index:1][count:1] then (count+1) x 7-byte object records
        [obj_type:1][score:2 LE][kills:2 LE][?:2 LE]
    NOTE the +1: the parser does `param_2 = count + 1` and loops that many times,
    consuming 9 + 7*count bytes per group, then asserts Length>=0. An empty arena
    needs NO real groups (loop guard `param_3>0` ends immediately after the header).

    FRAMING: like 62/63 the client delivers Length=bc*16+1, so the payload must tile
    to ==1 (mod 16) or the leftover bytes are parsed as a garbage group -> the
    ScoreTable.cpp:0x6c "Length>=0" assert (fatal). Header is 16B (==0 mod16), so an
    otherwise-empty table needs +1 byte... but a group is min 9B. We instead append
    ONE pad group sized so 9+7N tiles the whole payload: since gcd(7,16)=1 there is
    always an N in 0..15. The pad group uses a high base_index (240) so its zero
    score-defs land on unused object-type slots - harmless. See CRITICAL FRAMING."""
    ns = (list(nation_scores) if nation_scores else [0] * 7)[:7]
    while len(ns) < 7:
        ns.append(0)
    data = bytearray([MSG_SCORE_TABLE_96, 0x02])        # msg-id, then SCORE_TABLE version
    for v in ns:
        data += int(v & 0xFFFF).to_bytes(2, 'little')   # 7 ushorts = 14 bytes
    n_real_groups = 0
    if object_groups:
        for base_index, recs in object_groups:
            n_real_groups += 1
            # count byte = len(recs)-1 because the parser loops count+1 times
            cnt = max(len(recs) - 1, 0)
            data += bytes([base_index & 0xff, cnt & 0xff])
            for (obj_type, score, kills, extra) in recs:
                data += bytes([obj_type & 0xff])
                data += int(score & 0xFFFF).to_bytes(2, 'little')
                data += int(kills & 0xFFFF).to_bytes(2, 'little')
                data += int(extra & 0xFFFF).to_bytes(2, 'little')
    # TILE to bc*16+1 with one pad group consuming 9+7N bytes.
    deficit = _pad_to_bc_boundary_len(len(data))        # 0..15 bytes still needed
    # We must add a whole group: solve 9 + 7N == deficit (mod 16) for N in 0..15.
    inv7 = 7   # 7*7=49==1 mod16, so 7-1 == 7
    N = (inv7 * (deficit - 9)) % 16
    pad_recs = N + 1                                     # parser loops count+1 times
    data += bytes([0xF0, N & 0xff])                     # base_index=240, count=N
    data += b'\x00' * (7 * pad_recs)                    # zeroed score-defs
    assert len(data) % 16 == 1, f'96 framing {len(data)} !==1 mod16'
    log('SCORE96', f'ScoreTable nation_scores={ns} real_groups={n_real_groups} '
                   f'pad_group(N={N}, recs={pad_recs})')
    return build_appspace_pkt_exact(bytes(data))

MSG_STAT_BLOCK_25 = 0x19

# v230: field order of the 20-dword stat block (score+0x30), as FUN_004f4570 unpacks it. The wire
# types are fixed by that function (u8/u16/u32 at the offsets below); the MEANING of each slot is
# mapped to the manual's Scores Screen row order and refined empirically by reading the HUD. Only a
# few are known-for-sure yet, so unknowns are sent as 0. Indices 0..19 correspond to param_1[0..0x13].
STAT25_FIELD_TYPES = ['u8','u16','u16','u16','u16','u16','u16','u8','u8','u32','u32',
                      'u16','u16','u16','u16','u16','u16','u16','u16','u16']

def build_stat_block_25(player_index, fields):
    """FA msg 25 (0x19) SERVER->CLIENT - the full Current Life / Current Game stat table.

    Handler FUN_004f65a0 (dispatch slot 25): scans the GamerClientScore slots for +0x24 ==
    PlayerIndex, then FUN_004f4570(score+0x30, payload+5) unpacks 20 fields straight into the score
    object. THIS is the message that actually fills the scoreboard - msg 88 only sets aces (+0x50)
    and rank (+0x30-as-rank... separate). We never sent it, which is why kills/deaths/planes-lost
    stayed blank no matter what else we did.

    Wire: [0x19][PlayerIndex u32 LE] + packed block (offsets relative to block start = payload+5):
        +0x00 u8  f0     +0x01 u16 f1   +0x03 u16 f2   +0x05 u16 f3   +0x07 u16 f4
        +0x09 u16 f5     +0x0b u16 f6   +0x0d u8  f7    +0x0e u8  f8
        +0x0f u32 f9     +0x13 u32 f10
        +0x17 u16 f11 .. +0x27 u16 f19  (nine u16)
    `fields` is a list of 20 ints (missing/short -> 0). Values are clamped to each slot's width.

    NB the client's own 'out 25' is a short 7-byte NOTIFY in the other direction - unrelated, still
    swallowed (echoing it caused the v220 garbage-ace announcements). This is the SERVER->CLIENT set.
    """
    f = list(fields) + [0] * (20 - len(fields))
    def u8(i):  return bytes([int(f[i]) & 0xff])
    def u16(i): return struct.pack('<H', int(f[i]) & 0xffff)
    def u32(i):
        # v239: slots 9 and 10 are FLOATS (Fighter Score / Bomber Score), not integers. PROVEN:
        # probe #1 wrote int 9 there and the HQ screen read 0 - because int 9 reinterpreted as a
        # float is 1.26e-44. Probe #2 wrote the float bit-pattern for 1234.0 and the screen read
        # 1234. So pack these two as IEEE floats; everything else stays a plain u32.
        if i in STAT25_FLOAT_SLOTS:
            return struct.pack('<f', float(f[i]))
        return struct.pack('<I', int(f[i]) & 0xffffffff)
    block  = u8(0)
    block += b''.join(u16(i) for i in range(1, 7))     # f1..f6
    block += u8(7) + u8(8)
    block += u32(9) + u32(10)
    block += b''.join(u16(i) for i in range(11, 20))   # f11..f19
    assert len(block) == 0x29, f'stat block is {len(block)}B, expected 41'
    data = bytearray([MSG_STAT_BLOCK_25])
    data += struct.pack('<I', player_index & 0xFFFFFFFF)
    data += block
    return bytes(data)

# v231: WHERE THE BLOCK LANDS - two slots are already known for certain.
# FUN_004f65a0 does `lea ebx,[ebp+0x30]` then FUN_004f4570(ebx, payload+5), so the 20 fields are the
# dwords at score+0x30 .. score+0x7c. Cross-referencing msg 88 (FUN_004f4120), which writes
# score+0x30 = rank and score+0x50 = aces:
#       f0  -> score+0x30  == RANK      (CONFIRMED: v230 put deaths=22 in f0 and the client
#                                        announced the highest rank - it clamps >12 to 12)
#       f8  -> score+0x50  == ACES      (same arithmetic: 0x30 + 8*4 = 0x50)
# Everything else is still unmapped. Rather than guess, PROBE: write a distinct value into every
# slot in one go and read the scoreboard - whichever row shows 3 is f3, and so on. f0/f8 are
# excluded from the probe and always carry the pilot's REAL rank/aces so we don't corrupt them.
# v236: PROBE BACK ON - AIMED AT THE RIGHT SCREEN THIS TIME.
# The v231 probe was read on the IN-FLIGHT screen (Current Life / Current Game) and showed nothing,
# so msg 25 was written off. That was the WRONG SCREEN: those two columns are session state the
# client computes itself. The HQ SCORES screen is a different consumer entirely - it has
# "Latest | Career" columns, and it DISPLAYS THE RANK. Rank lives at score+0x30, which is exactly
# f0 of this block - so that screen demonstrably reads the very structure msg 25 writes, and the
# other 19 fields should drive its rows.
# Field WIDTHS are fixed by FUN_004f4570 and line up with the HQ screen beautifully:
#     f0 u8   = Rank                (CONFIRMED)
#     f7 u8   = a small counter     (Kills In A Row?)
#     f8 u8   = Aces                (CONFIRMED)
#     f9,f10 u32 = the only 32-bit slots -> Fighter Score / Bomber Score (only scores need 32 bits)
#     f1..f6, f11..f19 u16 = Planes Lost, Lost Pilots, Kills/Fighters/Bombers, and the AI section
# Probe sends f_i = i into every unmapped slot; f0/f8 keep the pilot's REAL rank/aces.
# READ THE HQ SCORES SCREEN (not the in-flight one): whichever row shows N is field N.
STAT25_PROBE = True          # <- set False once STAT25_MAP is calibrated from the HQ screen
STAT25_PROBE_BASE = 0        # probe value for slot i = STAT25_PROBE_BASE + i  (f1=1, f2=2, ... f19=19)

# ==== v238: THE HQ CAREER SCREEN IS MAPPED (probe #1 result, run 11:45) ====
# The probe finally ran (v237 pushes msg 25 when the HQ screen opens) and the HQ SCORES screen's
# CAREER column came back FULL of our probe values. msg 25 DOES drive it. Sent f_i = i (f0=rank=5,
# f8=aces=0) and read straight off the screen:
#     HQ row (Career)      shows   field
#     Rank                 Major     f0    (rank 5)          u8   CONFIRMED
#     Lost Pilots            1       f1                      u16  CONFIRMED
#     Kills > Fighters       2       f2                      u16  CONFIRMED
#     Kills > Bombers        3       f3                      u16  CONFIRMED
#     Kills                  5       f5                      u16  CONFIRMED
#     Kills In A Row         7       f7                      u8   CONFIRMED
#     Aces                   0       f8    (real aces)       u8   CONFIRMED
#     AI Fighters           11       f11                     u16  CONFIRMED
#     AI Bombers            12       f12                     u16  CONFIRMED
#     AI Ships              16       f16                     u16  CONFIRMED
#     AI Tanks              17       f17                     u16  CONFIRMED
#     AI Ground Units       18       f18                     u16  CONFIRMED
#     AI Buildings          19       f19                     u16  CONFIRMED
# The "Latest" column stayed 0 -> it is a SEPARATE block (last-mission stats) we don't set.
# STILL OPEN (probe #2 resolves both):
#   * Fighter Score / Bomber Score read 0 even though we put 9/10 in the two u32 slots (f9,f10).
#     Reinterpreting int 9 as a FLOAT gives 1.26e-44, which renders as 0 - so f9/f10 are almost
#     certainly FLOATS. Probe #2 sends float bit-patterns (1234.0 / 5678.0) to prove it.
#   * "Planes Lost" showed 17, the same value as AI Tanks (f17) - ambiguous. Probe #2 sets f17=97
#     and puts distinct markers in the remaining unknowns (f4,f6,f13,f14,f15) to find its real home.
STAT25_MAP = {
    # ============ FULLY MAPPED from the two HQ probes (v238/v239) ============
    'rank':            0,   # u8     Rank
    'deaths':          1,   # u16    "Lost Pilots"  (manual: times killed or captured)
    'kills_fighters':  2,   # u16    Kills > Fighters
    'kills_bombers':   3,   # u16    Kills > Bombers
    'planes_lost':     4,   # u16    Planes Lost TO PLAYERS   -- HQ shows f4 + f13
    'kills':           5,   # u16    Kills (total)
    'kills_in_a_row':  7,   # u8     Kills In A Row
    'aces':            8,   # u8     Aces
    'fighter_score':   9,   # FLOAT  Fighter Score   (proven: float 1234.0 -> screen read 1234)
    'bomber_score':   10,   # FLOAT  Bomber Score    (proven: float 5678.0 -> screen read 5678)
    'ai_fighters':    11,   # u16    AI Fighters Destroyed
    'ai_bombers':     12,   # u16    AI Bombers Destroyed
    'planes_lost_ai': 13,   # u16    Planes Lost TO AI        -- HQ shows f4 + f13
    'ai_ships':       16,   # u16    Ships
    'ai_tanks':       17,   # u16    Tanks
    'ai_ground':      18,   # u16    Ground Units
    'ai_buildings':   19,   # u16    Buildings
    # STILL UNMAPPED: f6, f14, f15 - they show NOTHING on the HQ screen, so they are almost certainly
    # the ASSISTS rows (Fighters Assists / Bombers Assists / Ship Assists) which appear only on the
    # IN-FLIGHT screen. Harmless; left at 0.
}
STAT25_FLOAT_SLOTS = (9, 10)   # Fighter/Bomber Score are FLOATS, not ints. PROVEN: probe #1 put int
                               # 9 there and the screen read 0 - because int 9 reinterpreted as a
                               # float is 1.26e-44. Probe #2 sent the float bit-pattern for 1234.0
                               # and the screen read 1234.

# ---- PROBE: DONE. Both probes have been read; the block is fully mapped. ----
STAT25_PROBE = False
STAT25_PROBE_UNKNOWN = {4: 91, 6: 92, 13: 93, 14: 94, 15: 95, 17: 97}   # kept for reference
STAT25_PROBE_SCORE_AS_FLOAT = True
STAT25_PROBE_F9  = 1234.0
STAT25_PROBE_F10 = 5678.0

def db_get_pilot_stat25(name):
    """v240: read every column that feeds the msg-25 stat block (the HQ Scores career screen).
    Returns a dict keyed by STAT25_MAP's keys, so send_stat_block_25 is a straight copy. Missing
    columns read as 0, so this is safe on an un-migrated DB."""
    keys = ('rank', 'deaths', 'kills_fighters', 'kills_bombers', 'planes_lost', 'kills',
            'kills_in_a_row', 'aces', 'score', 'bomber_score', 'ai_fighters', 'ai_bombers',
            'planes_lost_ai', 'ai_ships', 'ai_tanks', 'ai_ground', 'ai_buildings')
    out = {k: 0 for k in keys}
    if not name:
        return out
    conn = sqlite3.connect(DB_PATH)
    have = {r[1] for r in conn.execute("PRAGMA table_info(pilots)").fetchall()}
    cols = [k for k in keys if k in have]
    if cols:
        sel = ', '.join(f'COALESCE({c},0)' for c in cols)
        row = conn.execute(f"SELECT {sel} FROM pilots WHERE pilot_name=?", (name,)).fetchone()
        if row:
            for c, v in zip(cols, row):
                out[c] = v or 0
    conn.close()
    # 'score' is the FIGHTER score (msg-25 f9). Alias it so STAT25_MAP's key names line up.
    out['fighter_score'] = out.pop('score')
    return out

def send_stat_block_25(s, reason='', dst=None):
    """Fill the HQ SCORES screen's CAREER column from the DB via msg 25.

    v240: EVERY row of that screen now has its own DB column (see init_db), and STAT25_MAP maps each
    one to its slot in the 20-dword block. So this is a straight copy: whatever the web admin editor
    stores is exactly what the client renders - which makes the editor a complete end-to-end test
    harness for the stat block.
    v241: kills_in_a_row comes straight from the DB too - db_credit_kill maintains it (+1 per kill,
    0 on death), so it is the one true streak. No session counter is consulted.
    """
    if not SEND_STAT_BLOCK_25 or getattr(s, 'player_index', None) is None:
        return
    pilot = getattr(s, 'current_pilot', None)
    st = db_get_pilot_stat25(pilot)
    fields = [0] * 20

    def put(key, val):
        idx = STAT25_MAP.get(key)
        if idx is not None:
            fields[idx] = val

    # Straight copy, DB column -> stat-block slot. The client clamps rank >12 to 12; aces is a u8.
    # v241: NO session override for kills_in_a_row. The DB column IS the streak - db_credit_kill
    # increments it on every kill and zeroes it on every death - and overriding it with the
    # per-session counter (which starts at 0 each login) would report a LOWER streak than the truth
    # and hide any value seeded by the admin. One source of truth.
    for _k, _v in st.items():
        put(_k, _v)
    put('rank', min(max(int(st['rank']), 0), 12))
    put('aces', min(max(int(st['aces']), 0), 255))

    # ---- PROBE (off; both probes have been read and the block is fully mapped) ----
    if STAT25_PROBE:
        for _i, _v in STAT25_PROBE_UNKNOWN.items():
            fields[_i] = _v
        if STAT25_PROBE_SCORE_AS_FLOAT:
            fields[9]  = STAT25_PROBE_F9
            fields[10] = STAT25_PROBE_F10

    pkt = build_msg13(build_stat_block_25(s.player_index, fields))
    _target = dst if dst is not None else s          # v257: allow sending s's block to a peer
    threading.Thread(target=lambda: send_rel(_target, pkt,
                     f'<- msg 25 stat block ({pilot}) {reason}', to=3.0), daemon=True).start()
    if STAT25_PROBE:
        log('STAT25', f'PROBE -> {pilot} PI={s.player_index}: markers {STAT25_PROBE_UNKNOWN}, '
                      f'f9/f10 = FLOAT {STAT25_PROBE_F9}/{STAT25_PROBE_F10}. {reason}')
    else:
        log('STAT25', f'career -> {pilot} PI={s.player_index}: rank={fields[0]} '
                      f'kills={fields[5]} (F{fields[2]}/B{fields[3]}) lostpilots={fields[1]} '
                      f'planeslost={fields[4]}+{fields[13]} fscore={fields[9]} bscore={fields[10]} '
                      f'aces={fields[8]} streak={fields[7]} '
                      f'ai=F{fields[11]}/B{fields[12]}/S{fields[16]}/T{fields[17]}/'
                      f'G{fields[18]}/Bld{fields[19]} {reason}')

def push_career_stats(s, reason='', delay=0.4):
    """v237: state the pilot's authoritative career to the client - msg 88 (rank/aces) + msg 25 (the
    20-dword stat block at score+0x30).

    *** WHY THIS EXISTS: the v236 probe read "all 0" because NOTHING WAS EVER SENT. ***
    Both messages were only ever pushed from the SPAWN-INIT path (after a plane's ServerConfirm).
    But the HQ SCORES screen is read AT HQ, BEFORE you fly - the screenshot even shows the
    "FLY LANCASTER" button. Neither test run contained a single plane spawn (CONFIRM5 = 0), so msg 25
    never went on the wire at all and every row was 0 by construction. That was a broken test, not a
    negative result.
    Pushed on a daemon thread (send_rel blocks for its ACK).
    """
    def _go(_s=s):
        if delay:
            time.sleep(delay)
        try:
            if SEND_ACE_RANK_88:
                send_ace_rank_88(_s, reason=reason)
            send_stat_block_25(_s, reason=reason)
        except Exception as e:
            log('CAREER', f'[warn] career push failed for {getattr(_s, "current_pilot", "?")}: {e}')
    threading.Thread(target=_go, daemon=True).start()

def plane_movement(s):
    """v243: how far has this pilot's plane moved over the last CRASH_MOVEMENT_WINDOW_S seconds?

    Returns the total |delta| summed across the three quantised position axes. A PARKED plane
    reports EXACTLY 0, sample after sample (verified across three separate parked exits in run
    230703); a plane in flight moves by hundreds per tick. So this is what separates a CRASH from a
    clean exit - the exit packet itself cannot, since both send MissExitCode 26.
    Returns 0 when there's no evidence, which is the conservative answer (treat as parked).
    """
    hist = getattr(s, '_pos_hist', None)
    if not hist or len(hist) < 2:
        return 0
    total = 0
    for i in range(1, len(hist)):
        a, b = hist[i - 1][1], hist[i][1]
        total += sum(abs(b[k] - a[k]) for k in range(3))
    return total

def plane_was_flying(s):
    """True if the plane was airborne//in motion when it was removed (see plane_movement)."""
    return plane_movement(s) >= CRASH_MOVEMENT_MIN

def build_ace_rank_88(player_index, aces=0, rank=0):
    """FA msg 88 (0x58) - AceOrRankChangedCB (VNET table 0xc81ed8 slot 88, handler FUN_004f4120).

    Wire (7 bytes): [0x58][PlayerIndex:u32 LE][aces:u8][rank:u8]. The handler scans the 512
    GamerClientScore slots (mgr@0xc822d8[i*4+0xc]) for the one whose +0x24 == PlayerIndex, then
    writes score+0x50 = aces and score+0x30 = rank. These two fields are set ONLY by this message,
    so if we never send it they hold whatever was in the freshly-allocated score object -> the
    '96 Aces' / bogus-rank garbage on Test2's scoreboard after a team-swap re-entry. Sending an
    authoritative 88 (aces=0, rank=<sane>) on spawn/re-entry initialises them cleanly.

    Returns the RAW 7-byte sub-message (msg-id + record) for wrapping in a msg-13 batch, exactly
    like build_add_player_62 - the VNET dispatch is reached the same way (13 -> per-submessage
    dispatch through 0xc81ed8). The handler matches by PlayerIndex, so the score object must ALREADY
    exist (created by the client record in the first-spawn create) or the handler logs
    'AceOrRankChangedCB. PlayerIndex=%i not found' and no-ops - hence we send it AFTER the spawn is
    confirmed, not before.
    """
    data = bytearray([MSG_ACE_RANK_88])
    data += struct.pack('<I', player_index & 0xFFFFFFFF)
    data += bytes([aces & 0xff, rank & 0xff])
    return bytes(data)

def send_ace_rank_88(s, reason='', aces=None, rank=None):
    """v219: push the pilot's AUTHORITATIVE aces/rank to their client via msg 88.

    Values are RE-READ FROM THE DB (db_get_pilot_career) every time, so a team change or room change
    RESTORES the pilot's real career standing rather than zeroing it. The client's GamerClientScore
    object persists across those transitions and its aces (+0x50) / rank (+0x30) fields are written
    ONLY by msg 88 - so if we don't state them, the client keeps whatever uninitialised memory was
    there and announces a bogus ace status at the transition (the '29 Aces' Test2 saw on USA->GBR).

    Pass explicit aces/rank to override the DB (e.g. for testing); otherwise they're derived from
    the pilot's career kills/rank. Safe no-op if the player has no assigned index yet.
    """
    if getattr(s, 'player_index', None) is None:
        return
    pilot = getattr(s, 'current_pilot', None)
    if aces is None or rank is None:
        _score, _kills, _deaths, _rank, _aces = db_get_pilot_career(pilot) if pilot else (0, 0, 0, 0, 0)
        if aces is None:
            # v221: use the STORED career ace status (u8). Do NOT derive it from kills - the live
            # ace rule (5 kills without dying, reset on death) is the CLIENT's own session logic.
            aces = min(max(int(_aces), 0), 255)
        if rank is None:
            rank = _rank
    pkt = build_msg13(build_ace_rank_88(s.player_index, aces=aces, rank=rank))
    # *** v245: PEERS ONLY - never send a player their OWN msg 88. ***
    # msg 88's handler (FUN_004f4120) is a PURE SETTER - it writes score+0x50 (aces) and score+0x30
    # (rank) and returns. No event, no message, nothing on screen.
    # The YELLOW IN-FLIGHT FLASH comes from msg 25's handler (FUN_004f65a0), which has TWO paths:
    #     [0xc6eb98] -> plane -> +0x128 -> score obj; if its PlayerIndex == the packet's, jump to
    #     the ANNOUNCING path at 0x4f6637 - otherwise take the silent write path.
    # On the announcing path it compares the INCOMING value against what's ALREADY in the score
    # object and only announces on an INCREASE:
    #     aces: byte[payload+0x13] > score+0x50  -> show message 0x4b for 3000ms  ("you're an Ace")
    #     rank: byte[payload+0x05] > score+0x30  -> show message 0x4c for 3000ms  (promotion)
    #     ...and only THEN does it write the block.
    # So if msg 88 reaches the OWNER first, it silently bumps score+0x50/+0x30 to the new value and
    # msg 25 arrives to find nothing left to announce -> the flash never fires. msg 88 was stealing
    # its own announcement.
    # Peers still need it (they never receive a msg 25 about somebody else), so it goes to everyone
    # EXCEPT the owner, and msg 25 does the owner's update AND the announcement.
    _targets = [t for t in (get_sessions_in_room(s.current_room)
                            if getattr(s, 'current_room', None) is not None else [])
                if t is not s]
    _label = (f'<- AceOrRank 88 (PI={s.player_index} aces={aces} rank={rank})'
              f'{(" " + reason) if reason else ""}')
    for _t in _targets:
        threading.Thread(target=lambda _x=_t: send_rel(_x, pkt, _label, to=3.0),
                         daemon=True).start()
    log('ACE88', f'AceOrRank -> {pilot} PI={s.player_index} aces={aces} rank={rank} '
                 f'(from DB career) -> {len(_targets)} PEER(s) in room {s.current_room}; the owner '
                 f'gets it via msg 25 so the in-flight announcement can fire {reason}')


# msg-96 = per-object-type point RULES; FUN_004f53b0 FREES the client's own loaded table and
# rebuilds from ours, so we MUST supply valid defs or a kill reads uninitialised memory
# (-> Score:-64662, bogus Ace/Rank, freeze - messages13 03.43.45). Two hard constraints from RE:
#   * SIZE: the msg must fit ONE reliable packet. A full 256-slot table was 1889B and the client
#     never ACKed it (entry hung -> 10054); a 1345B GAME_DEF does ACK, so the ceiling is ~MTU. The
#     score-def INDEX is the object's TYPE (FUN_00447520: bounds 0..255, but planes log Type=2 -
#     a small CATEGORY), so only low slots matter. Populate 0..31 -> ~321B, well inside one packet.
#   * FIELD: the scorer reads score-def+0xc (FUN_00449b60); the parser (FUN_00629600) fills that
#     from the record's THIRD u16 = the 'extra' field, NOT 'score'. Value must be > 0.
# Record tuple is (obj_type, score, kills, extra) - the points go in `extra`.
OBJ_SCORE_POINTS_DEFAULT = 100
SCORE_DEFS_DEFAULT = [(0, [(t, 0, 0, OBJ_SCORE_POINTS_DEFAULT) for t in range(32)])]

def push_player_roster_62(s, reason=''):
    """Send msg 62 to s: the full set of OTHER players already in s's room, so the
    client builds a REMOTE_PLAYER object for each. Self is excluded (the local pilot
    is the player object allocated by the 201 grant, not a remote)."""
    room_id = s.current_room
    if room_id is None:
        return
    peers = [x for x in get_sessions_in_room(room_id) if x is not s]
    if not peers:
        log('PLAYER62', f'no peers in room {room_id} to advertise to {s.current_pilot} {reason}')
        return
    records = [(p.player_index, p.nation, p.current_pilot or 'Player') for p in peers]
    pkt = build_msg13(build_add_player_62(records))   # WRAP in msg-13 batch (build_add_player_62
                                                      # returns a RAW sub-message; sending it
                                                      # unwrapped made the client read bc=0x3e=62)
    send_rel(s, pkt, f'<- AddPlayer 62 ({len(records)} peer(s)){(" " + reason) if reason else ""}', to=5.0)

def broadcast_player_join_62(joiner, reason=''):
    """Tell every OTHER player in joiner's room to add `joiner` as a REMOTE_PLAYER
    (msg 62, single record). Symmetric to push_player_roster_62, for the live case
    where someone enters a room others are already in."""
    room_id = joiner.current_room
    if room_id is None:
        return
    peers = [x for x in get_sessions_in_room(room_id) if x is not joiner]
    if not peers:
        log('PLAYER62', f'no peers in room {room_id} to announce {joiner.current_pilot} to '
                        f'{(reason or "").strip()}')
        return
    rec = [(joiner.player_index, joiner.nation, joiner.current_pilot or 'Player')]
    pkt = build_msg13(build_add_player_62(rec))       # WRAP in msg-13 batch (was sent raw -> bc=62)
    n = 0
    for sess in peers:
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt,
                         f'<- AddPlayer 62 (joiner {joiner.current_pilot}){(" " + reason) if reason else ""}',
                         to=3.0), daemon=True).start()
        n += 1
    log('PLAYER62', f'broadcast join of {joiner.current_pilot} -> {n} peer(s) in room {room_id}')

def broadcast_player_change_63(s, side, op=CP_OP_CAMP, reason=''):
    """Broadcast a msg 63 ChangePlayerCB for session s to EVERY player in the room,
    including s themselves.

    CORRECTED (v185/v186): v183's peers-only rule was a misread of FUN_004fa9c0 -
    the `iVar12 != DAT_00bfedb4` skip is the GetClient (FUN_004f2560) scan over the
    512-entry CLIENT table, skipping the local CLIENT NUMBER (DAT_00bfedb4 is set to
    jga->ClientNumber in the 201 handler), not the player lookup. The rp is resolved
    through FUN_007fcac0 for ANY index, INCLUDING the recipient's own: the msg 201
    grant handler (FUN_004f88f0) creates the local player's entry in that table
    (camp=-1, local pilot name) at join time. A self-directed 63 op=1 therefore
    resolves immediately, sets the camp (which drives friendly/enemy CHAT COLOR via
    FUN_0046bba0 in the msg 20 handler), and prints the "<pilot> changed to
    <nation>" system chat line. This is the designed team-change mechanism.
    The v182 crash was solely the op=2 delete path. NEVER send msg 62 about a
    player's own index (see build_add_player_62 invariant)."""
    room_id = s.current_room
    if room_id is None:
        return
    rec = [(s.player_index, side, op)]
    pkt = build_change_player_63(rec)
    # The SUBJECT must receive its OWN camp change for a real team JOIN (side is a nation):
    # the self-63 is what sets the local player's camp (chat colour + world/chat roster line),
    # and get_sessions_in_room filters on entered_game (briefly False at team-select after an
    # exit-flight), so without this the roster froze on the first side. But NEVER echo a
    # side=None (neutral/leave) self-63 to the subject: telling the client it has no team makes
    # it bail to the lobby (msg-64), and on a reliable-desynced re-entered channel that turns
    # into a back-to-lobby retransmit storm -> 'Test1 leaving GBR' flood -> dropped connection.
    # The transient leave is the client's own action; peers still get it for their roster.
    recipients = list(get_sessions_in_room(room_id))
    if side is not None and s not in recipients:
        recipients.append(s)
    n = 0
    for sess in recipients:
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt,
                         f'<- ChangePlayer 63 ({s.current_pilot} side={side} op={op})'
                         f'{(" " + reason) if reason else ""}', to=3.0), daemon=True).start()
        n += 1
    log('PLAYER63', f'broadcast camp-change {s.current_pilot} side={side} op={op} -> '
                    f'{n} session(s) incl. self')

def send_arenalist_with_gamedefs(s, rooms, label):
    """v164: send each room's 212 GAME_DEF FIRST, then the 0xd2 list.
    The 212 parse (FUN_0057bee0) calls the terrain setter FUN_004c7cd0(terrain) with
    the GAME_DEF's terrain ushort. build_lz_gamedef now patches that ushort from 0 to a
    valid terrain (FORCE_GAMEDEF_TERRAIN), so when the single arena is auto-selected and
    the list-box builds its Trn preview, _TrnNumber>=1 holds. (v163 sent the list alone
    and still asserted: with no 212 the current terrain stayed 0.)"""
    for r in rooms:
        if len(r) > 6 and r[6]:
            pkt = build_gamedef_212(r)
            if pkt is not None:
                send_rel(s, pkt, f'<- GAME_DEF 212 (room {r[0]})', to=5.0)
                time.sleep(0.01)
    send_rel(s, build_arenalist(rooms), label, to=3.0)

def build_chat_broadcast(pilot_name, message):
    nb = (pilot_name.encode() if isinstance(pilot_name,str) else pilot_name) + b'\x00'
    mb = (message.encode() if isinstance(message,str) else message) + b'\x00'
    return build_appspace_pkt(bytes([0xcd]) + nb + mb)

def build_ui_player_update(pilot_name, is_join=True):
    """Build 0xcc LmsChangePlayers packet to update the lobby UI list."""
    action_flag = 0x01 if is_join else 0x00
    status_byte = 0x00 if is_join else 0xFF
    nb = (pilot_name.encode() if isinstance(pilot_name,str) else pilot_name) + b'\x00'
    return build_appspace_pkt(bytes([0xcc, action_flag, status_byte]) + nb)

# --- Session state ------------------------------------------------------------

_session_counter = itertools.count(1)

class S:
    def __init__(self, cid, addr):
        self.sid = next(_session_counter)
        self.cid=cid; self.addr=addr; self.sq=0; self.ts=0
        self.rx=0; self.closing=False; self.t0=time.time()
        self.rseq=0; self._lock=threading.Lock(); self._evts={}
        self.undgram=0                 # per-session UNRELIABLE datagram seq (byte[3]); separate from rseq
        self._awaiting_reattach=False  # exit-to-HQ: resend 0xDA re-attach UNRELIABLY on each 0x43 poll
        self.auth_done=False; self.post_auth_cmds=[]
        self.account=None; self.auth64=None; self.auth_payload=None
        self.current_pilot=None; self.current_slot=0; self.current_room=None; self.room_slot=0; self.last_43_ts=0.0; self.entered_game=False; self.in_game=False; self.client_granted=False
        self.plane_type=PLANE_TYPE_ID   # v201: player's selected plane index (from out-4 byte[8]); default until first spawn
        self.para_obj_number=None       # v248: the PARACHUTER's object number after a bail. This is a
                                        # SECOND object alongside my_obj_number (the plane) - the plane
                                        # keeps its aircraft-type tag and flies on pilotless, while the
                                        # parachuter carries the pilot's name + rank. Keeping them in
                                        # separate slots is essential: reusing my_obj_number for the
                                        # parachute is what made the plane's later delete land on an
                                        # object nobody owned.
        self._status_seq=0              # v215: STATUS packet sequence (low 9 bits, increments each send)
        self._status_connid=None       # v215: connection id observed from the client's own packets (wire bytes 0-1)
        self._status_last=0.0          # v215: time of last STATUS request sent
        self._status_base_epoch=None   # v215: server-time anchor for the base-increment we feed the client
        # -- Per-room game state (multi-room: every player's runtime state is keyed
        # to the room they entered, so chat / roster / positions never cross rooms) --
        self.client_number=0      # assigned at the 201 grant, unique WITHIN the room
        self.player_index=0       # ditto; stamped into chat/roster so it resolves to us
        self.nation=None          # selected side 0..7 (US=0...), None = "In Menu"/unassigned
        # -- In-game spawn/object state (ServerConfirm + entity stream) --
        self.spawn_ident_next=0   # per-client object IDENT counter (0=first plane); echoed
                                  # in ServerConfirm (msg 5) to bind the client's local
                                  # object to a server object Number.
        self.obj_confirmed=False  # ServerConfirm sent for the current spawn? (reset per StartPlace)
        self.my_obj_number=None   # server-assigned object Number for this player's plane
        self.flying=False         # set once ServerConfirm sent (sim loop should start)
        # -- v267 auto-resupply state (P2a) --
        self.at_airfield=None     # AF ident the player is parked at (from StartPlace 0x17), else None
        self.engine_on=None       # last engine state (type=0x22 sub=0x53: 1=on, 0=off), None=unknown
        self.parked_since=None    # v268: time.time() when the settle timer started, else None
        self.stationary_since=None # v272: time.time() the plane's ground speed hit 0, else None
        self.last_pos=None        # v274: last quantised position seen by the resupply poll
        self.pos_static_since=None # v274: time.time() the position last changed (static clock)
        self.pos_static_samples=0 # v277: consecutive FRESH telemetry packets with the same position
        self.last_pos_telem_t=0.0 # v277: last_telem_time already consumed by the resupply poll
        self.resupplied_this_stop=False # v278: one-shot guard - fire once per stationary episode
        self.spawn_time=0.0       # v279: time.time() of the last ServerConfirm (spawn grace window)
        self.has_flown=False      # v269: engine has run since spawn -> a later shutdown = real landing
        self.last_resupply_at=0.0 # time.time() of the last auto-resupply grant (debounce)
        self.last_telem_tick=None # this player's most recent conductor tick (telemetry[5:7]);
        self.last_telem_time=0.0  # used to re-stamp packets we RELAY *to* this player so the
                                  # tick lands on THEIR clock (small +delta = smooth interp)
        # -- Combat scoring (server-authoritative kill tracking, accumulated in DB) --
        self.last_fired_at=0.0    # time.time() of this session's most recent DAMAGE28 (msg 28);
                                  #   used to attribute a peer's death to the most-recent shooter
        self.k_kills=0; self.k_deaths=0; self.k_score=0  # this-session tallies (DB holds the total)
        self.synack_base=None     # v209: (fa_s, fa_frac) from the connect SYNACK; replayed verbatim
                                  # on HQ re-entry so the client's NET-time base stays a fixed
                                  # connect constant (matches 2009 CreationTimeSeconds behaviour)
        # v211: NET-time NTP epoch. The client (vcncNet FUN_10007fc0 -> tSyncAddMeasurement) anchors
        # its clock BASE from the SYNACK fa_s:fa_frac (set-base FUN_10007cef, ONCE), then reconstructs
        # server_time = base + beacon_A/1000 - beacon_B/1000, and NTP-compares it to its local clock:
        # offset = ((pT2-pT1)+(pT3-pT4))/2, lag L = (pT4-pT1)-(pT3-pT2). The beacon A field is 18-bit
        # (wraps every 262.143s). For offset to stay ~0 (matching a live host's small real lag, e.g.
        # 2009's 'L:0.19'), A must encode ELAPSED since the base anchor so base+A == server_now. But
        # elapsed wraps at 262s -> the client, whose base is locked, then sees a 262s offset step and
        # slews to death ('CRAP backward NET Time', the -261.76 offset in run_054615). FIX: A =
        # elapsed-since-_ntp_epoch, and we RE-ANCHOR the base (resend a SYNACK-format fa_s:fa_frac and
        # reset _ntp_epoch=now) every NTP_REANCHOR_S < 262s, so A resets to ~0 before it can wrap and
        # base+A stays continuous. _ntp_epoch is the server wall-clock time of the last base anchor.
        self._ntp_epoch = time.time()
        self._ntp_last_reanchor = time.time()
        # -- Reliable-channel diagnostics (stall hunt) --
        self._rel_rx_time=0.0     # time of last reliable (pt=1) packet FROM this client
        self._unrel_rx_time=0.0   # time of last unreliable in-game packet FROM this client
        self._rel_rx_last_cs=None # last reliable RX seq byte (data[3]); repeats => client retransmit
        self._rel_rx_count=0; self._rel_rx_dups=0; self._ack_in_count=0
        self._stall_warned=False  # STALL-WATCH logs the transition once, not every tick
        # -- Flight recorder rings (dumped to logs/flightrec/ when STALL-WATCH fires) --
        self._rec_rel=deque(maxlen=FLIGHT_REC_RELMAX)    # reliable msgs both directions
        self._rec_unrel=deque(maxlen=FLIGHT_REC_UNRMAX)  # trailing unreliable telemetry
        self._rec_dumped=False    # dump once per stall, re-armed when reliable RX resumes
    def nsq(self): v=self.sq; self.sq=(self.sq+1)&0xFF; return v
    def nundgram(self): v=self.undgram; self.undgram=(self.undgram+1)&0xFF; return v
    def nts(self): self.ts=(self.ts+1)&0xFF; return self.ts
    def ela(self): return time.time()-self.t0
    def nrel(self):
        # Reliable TX seq. The wire carries this as the 8-bit byte[3] (build_rel: h[3]=seq&0xFF),
        # and the server reads the client's reliable seq the same way (cs=data[3], 8-bit). So the
        # counter MUST wrap at 256 to stay in lock-step with the wire and with _evts (keyed on
        # this value). It was &0x1FF (9-bit): fine below 256, but at the 256th reliable send of a
        # session the 9-bit key (256) no longer matched the 8-bit wire seq (0) the client ACKs,
        # so the ACK lookup missed and EVERY reliable send from then on timed out - a slow
        # "everything eventually wedges" failure on long sessions. &0xFF keeps key, wire, and ACK
        # aligned across the wrap.
        with self._lock: v=self.rseq; self.rseq=(self.rseq+1)&0xFF; return v
    def sig(self, seq):
        with self._lock: e=self._evts.get(seq)
        if e: e.set(); return True
        return False
    def mke(self, seq):
        e=threading.Event()
        with self._lock: self._evts[seq]=e; return e
    def rme(self, seq): self._lock.acquire(); self._evts.pop(seq,None); self._lock.release()

sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
# -- Windows UDP WSAECONNRESET trap (FATAL server-recovery fix) ----------------------------
# When the server sendto()s a client that has CTD'd / closed its port, Windows posts an ICMP
# port-unreachable and then raises WSAECONNRESET (WinError 10054) on the NEXT recvfrom() -
# DISCARDING the datagram that was waiting. The dead session's heartbeat keeps firing every
# ~5s, so each one eats an inbound packet; a reconnecting client's SYN / pilot-list / arena-list
# requests get intermittently dropped and come back EMPTY, needing a full server restart. The
# dead session is never reaped because on Windows the failure surfaces on recvfrom, not sendto,
# so the heartbeat's OSError 3-strikes path never fires. Disabling SIO_UDP_CONNRESET makes
# recvfrom ignore the stale ICMP and never drop a good datagram. Guarded/no-op off Windows.
try:
    _SIO_UDP_CONNRESET = getattr(socket, 'SIO_UDP_CONNRESET', 0x9800000C)
    sock.ioctl(_SIO_UDP_CONNRESET, False)
    log('INIT', 'SIO_UDP_CONNRESET disabled (recvfrom survives client CTDs)')
except (AttributeError, OSError, ValueError) as _e:
    log('INIT', f'SIO_UDP_CONNRESET not disabled ({_e!r}) - 10054s handled in recv loop instead')
sock.bind((HOST,PORT)); sock.settimeout(0.5)
sids={}; sadrs={}; sl=threading.Lock(); running=True

# Globally-unique in-game object Number allocator. ServerConfirm (msg 5) stamps this
# onto each spawning player's plane; the client echoes it back as the object id at
# telemetry offset 7-8 (LE u16, e.g. 0x0100 -> bytes 00 01). Distinct per player so a
# relayed stream never collides with the RECIPIENT's own object on the receiver - A's
# plane and B's plane carry different Numbers, so B treats A's update as a remote object.
_obj_num_lock = threading.Lock(); _obj_num_next = 0x0100
_obj_num_free = []   # recycled Numbers from deleted own-planes (LIFO); popped before incrementing
# EXPERIMENT (spawn-freeze hunt): the residual instant mid-flight freeze is cumulative in total
# spawn count, plane-independent, with a provably clean server + reliable channel. The one thing
# that grew unboundedly per spawn was the object Number (256,257,... never reused), a prime
# suspect for a client-side per-object structure that never gets pruned. Recycling the player's
# own Number when their plane is deleted keeps the working set tiny (spawn 50 reuses spawn 5's
# Number) so it either stops the freeze or cleanly rules Numbers out. Safe in single-player (no
# peers); the delete-notify means the client already dropped that object before we re-hand it.
RECYCLE_OBJ_NUMBERS = True
def next_obj_number():
    global _obj_num_next
    with _obj_num_lock:
        if RECYCLE_OBJ_NUMBERS and _obj_num_free:
            return _obj_num_free.pop()          # reuse a freed Number before minting a new one
        n = _obj_num_next
        _obj_num_next = _obj_num_next + 1
        if _obj_num_next > 0xFFFF: _obj_num_next = 0x0100
        return n
def free_obj_number(n):
    """Return a deleted own-plane Number to the recycle pool. No-op if disabled, None, or already
    pooled. Capped so a pathological leak can't grow the list without bound."""
    if not RECYCLE_OBJ_NUMBERS or n is None:
        return
    with _obj_num_lock:
        if n not in _obj_num_free and len(_obj_num_free) < 256:
            _obj_num_free.append(n)

def get_s(addr):
    with sl: return sadrs.get(addr)

def build_unrel(payload, seq=0):
    # UNRELIABLE (pt=0): offset-4 control dword = 0, same 8-byte framing as relay_telemetry
    # (byte[2]=0x20, byte[3]=datagram seq). The client does NOT run these through its reliable
    # channel, so they do NOT advance vcncNet's per-packet diagnostic array (the array that,
    # after ~32 reliable packets, overruns the delivery callback @0x1002042c -> exit-to-HQ CTD).
    return bytes([0x00, 0x00, 0x20, seq & 0xFF, 0x00, 0x00, 0x00, 0x00]) + bytes(payload)

def send_unrel(s, payload, label=''):
    seq = s.nundgram()
    try: sock.sendto(build_unrel(payload, seq), s.addr)
    except OSError: return False
    log('TX/UNREL', f'dseq={seq} type=0x{payload[1]:02x} {label}')
    return True

def send_rel(s, payload, label='', to=5.0):
    seq=s.nrel(); e=s.mke(seq)
    try: sock.sendto(build_rel(payload,seq),s.addr)
    except OSError: s.rme(seq); return False
    bc=payload[0]
    log('TX/RELIABLE',f'seq={seq} bc={bc}(p3={bc*16+1}) type=0x{payload[1]:02x} {label}')
    _rec(s, 'S->C', 'RELTX',
         f'seq={seq} type=0x{payload[1]:02x} bc={bc} {label} pl={binascii.hexlify(bytes(payload[:24])).decode()}')
    ok=e.wait(timeout=to); s.rme(seq)
    log('TX/RELIABLE',f'seq={seq} {"ACKed OK" if ok else "TIMEOUT X"}')
    if not ok:
        _rec(s, 'S->C', 'RELTX', f'seq={seq} TIMEOUT (no ACK in {to}s) type=0x{payload[1]:02x} {label}')
    return ok

def send_reply(s, payload, label='', to=5.0):
    # Post-login server->client reply. When SEND_GAMEPLAY_UNRELIABLE, go UNRELIABLE (pt=0) so it
    # does NOT advance the client's reliable diagnostic array (hard ~32/connection -> CTD). On a
    # LAN this is near-lossless; a dropped reply shows as a stuck spawn, not a crash. Else reliable.
    if SEND_GAMEPLAY_UNRELIABLE:
        return send_unrel(s, payload, label)
    return send_rel(s, payload, label, to)

def get_all_sessions():
    with sl: return [s for s in sids.values() if s.auth_done and not s.closing]

def get_sessions_in_room(room_id):
    """All players currently INSIDE a given game room. The unit of isolation for
    multi-room hosting: chat, roster and (later) position updates are broadcast only
    to the sessions this returns, so nothing leaks between concurrently-hosted rooms."""
    if room_id is None: return []
    with sl:
        return [s for s in sids.values()
                if s.auth_done and not s.closing and s.entered_game
                and s.current_room == room_id]

def assign_player_slot(s, room_id):
    """Allocate a ClientNumber/PlayerIndex for a player entering a room.

    STABILITY (messages38 CTD): the index MUST stay stable for a session across arena
    changes. It was `len(peers)` - pure join order - so when two players switched arenas
    and joined the new one in a different order, their indices SWAPPED (Bigalon 0->1,
    Test2 1->0). But each client still held its ORIGINAL index and each peer's create/62
    still referenced the old one, so the client hit 'Add existing REMOTE_PLAYER Test2
    PlayerIndex=0' (index 0 now claimed by two players) -> the peer object's Client()
    resolved to 0/null -> assertion (o->Number()>=0 && o->Client()!=0) Network.cpp:440 ->
    CTD on BOTH clients on 3D entry. Fix: once a session has an index, KEEP it; only
    recompute if it would actually collide with a peer already in the target room. With
    <=8 players the first-assigned indices never collide, so identities stay put across
    every arena change."""
    peers = [x for x in get_sessions_in_room(room_id) if x is not s]
    taken = {getattr(p, 'client_number', None) for p in peers}
    prev = s.__dict__.get('_assigned_slot')
    if prev is not None and prev not in taken:
        idx = prev                       # keep our stable identity across arena changes
    else:
        idx = 0                          # first free index not already claimed in this room
        while idx in taken:
            idx += 1
    s._assigned_slot = idx
    s.client_number = idx
    s.player_index  = idx
    log('ROOM', f'{s.current_pilot} -> room {room_id} slot ClientNumber={s.client_number} '
                f'PlayerIndex={s.player_index} (peers={len(peers)}, '
                f'{"kept" if prev==idx else "assigned"})')
    return s.client_number, s.player_index

def _maybe_grant_create_entry(s):
    """Auto-join grant for the ARENA CREATOR. Unlike JOIN (client sends 0xc8
    SendEnterToGame -> we reply 201), the CREATE flow sends NO 0xc8 - the client drives
    entry purely off the 1-Hz 0x43 game-connect poll and waits for a JoinToGameAnswer 201
    to clear it (DAT_00c82eb0->0, game active). Without the 201 the poll never stops -> soft
    timeout -> the client exits the game (server.log 14:47:19 create -> ~15s of 0x43 -> exit).
    So on the creator's FIRST 0x43 poll for the room they just created, grant entry exactly
    like the 0xc8 path. Gated by _await_create_entry (set only by the 0xdc create handler)
    so JOIN/lobby polls are untouched, and idempotent via client_granted. Returns True if it
    granted on this call (caller then reports the confirm in GAME mode)."""
    if not getattr(s, '_await_create_entry', False):
        return False
    s._await_create_entry = False
    if s.entered_game or s.client_granted or s.current_room is None:
        return False
    s.entered_game = True
    s.nation = None                                   # "In Menu" until a side is picked
    assign_player_slot(s, s.current_room)
    s.client_granted = True
    send_rel(s, build_join_game_answer_201(s.client_number, s.player_index),
             f'<- JoinToGameAnswer 201 (ClientNumber={s.client_number} '
             f'PlayerIndex={s.player_index} -> GRANT, create auto-join)', to=5.0)
    def _stand_up(_s=s):
        push_player_roster_62(_s, reason='(on create, 0x43 grant)')
        broadcast_player_join_62(_s, reason='(on create, 0x43 grant)')
    threading.Thread(target=_stand_up, daemon=True).start()
    log('CREATE-JOIN', f'201 GRANT on creator 0x43 poll (room {s.current_room}) -> GAME MODE')
    return True

# -- TELEMETRY RELAY (multiplayer flight) ---------------------------------------
# The flying client streams its plane state as UNRELIABLE datagrams (control dword 0,
# pt 0, sz>8) whose payload is the object-update [05 42 00 00 07][tick:2][Number:2 LE]
# [posX:3][posY:3][posZ:3][attitude...][config]. Identity is NOT in the payload - both
# pilots emit object Number 0x0100 by default - so each player is given a GLOBALLY-UNIQUE
# Number at ServerConfirm (next_obj_number). With distinct Numbers we can forward the
# stream VERBATIM to every other flying player in the same room: the receiver sees an
# object Number != its own -> a remote plane. We send on the EXISTING server connection
# (header byte1=0, the same one build_rel uses and the client already accepts), control
# dword 0 (unreliable), per-recipient datagram seq. We normalise to the prefix-less form
# (strip the optional 4-byte [seq][flags] the sz=100 variant carries) so every relayed
# packet is the clean 88-byte 05 42... core.
#
# OPEN QUESTION this is built to answer EMPIRICALLY: does an incoming update for an
# unknown Number lazy-CREATE the remote plane, or must the server first synthesise a
# create (msg 2)? If peers see each other's planes move -> lazy-create works. If not ->
# msg 2 synthesis is the next step. Either outcome is decisive.
RELAY_TELEMETRY = True
# v188 DIAGNOSTIC (reversible): trim discretionary lobby/hangar STATUS echoes to slow the
# reliable-sequence growth on the single VNET connection. The 3rd-respawn CTD is an access
# violation INSIDE vcncNet.dll dispatching a reliable packet at seq ~34 (FA_exe_18372.dmp).
# FA opens exactly ONE connection (login path only; no game-enter second connect), so lobby
# and game share it and the reliable seq climbs ~6-8/cycle. Suppressing the small 0x22/0x39
# echoes (which the client sends repeatedly and does NOT appear to block on) cuts ~3 reliable
# seqs/cycle. KEEP 0x3a (the 113-byte plane list the hangar waits for). If the lobby HANGS
# after a leave, set TRIM_RELIABLE_ECHOES=False - that tells us those echoes ARE awaited and
# the crash is lifecycle- not volume-driven.
TRIM_RELIABLE_ECHOES = True
TRIM_ECHO_SUBS = {0x22, 0x39}

# -- Exit-to-HQ reliable-budget fix (server-side only; client + game files untouched) ------
# vcncNet advances an internal per-packet diagnostic array once per RELIABLE (pt=1) packet the
# client RECEIVES. After ~32 in a session it overruns the registered packet-delivery callback
# pointer (vcncNet .data 0x1002042c); the next reliable delivery does call [garbage] -> CTD.
# Exit-to-HQ is where it tips over (login + a few cycles ~= 32). UNRELIABLE (pt=0) packets do
# NOT advance that array (proven by stable multi-sortie respawn flight). So exit-path control
# messages (0xDA re-attach, exit 0x3a hangar list) go UNRELIABLE with resend-on-loss: continued
# 0x43 poll => re-attach didn't land => resend; empty hangar => client re-requests 0x3a => re-echo.
# On a LAN this is effectively lossless and keeps the reliable seq from climbing. False = revert.
SEND_EXIT_UNRELIABLE = False
# Round 2: extend the unreliable treatment to the per-spawn-cycle reliable sends (StartPlace
# GRANT, ServerConfirm, generic echo) so the reliable seq PLATEAUS after login instead of
# climbing ~4/cycle toward the ~32 limit. Single small packets; on a LAN unreliable delivery is
# near-lossless. If a reply is ever dropped the symptom is a stuck spawn (NOT a CTD), and we add
# progress-based resend then. False reverts this layer to reliable.
SEND_GAMEPLAY_UNRELIABLE = False

# --- Flight recorder ----------------------------------------------------------------------
# The reliable-channel stall (client freezes mid-flight, reliable RX goes silent while
# unreliable telemetry coasts on stale data) leaves no client-side log - FA only opens a new
# messagesNN.log per launch, and the hang prevents the world-entry lines from flushing. So the
# server is the only witness. This recorder keeps a small per-session ring of the most recent
# reliable messages (both directions) plus the tail of unreliable telemetry, and dumps it to a
# dedicated file the instant STALL-WATCH fires - turning every future freeze into hard data
# (exact last reliable msg each way, and the telemetry state at the moment of the stall).
FLIGHT_RECORDER   = True     # master switch (also toggleable live via `rec` console command)
FLIGHT_REC_RELMAX = 40       # reliable msgs (each direction) kept per session
FLIGHT_REC_UNRMAX = 24       # trailing unreliable telemetry packets kept per session
FLIGHT_REC_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'flightrec')

def _rec_decode_telem(data):
    """Decode the useful trend fields from an unreliable telemetry datagram for the flight
    recorder: the object-update tick (a smoothly advancing counter) and Number (object id).
    Returns a short 'tick=.. Number=..' string, or '' if this isn't a 0x42 object update.
    Never raises. Cheap - only runs on the small trailing ring, not every packet path."""
    try:
        core = data.find(b'\x05\x42\x00\x00\x07')   # object-update marker (handles sz=96 and sz=100)
        if core < 0 or core + 9 > len(data):
            return ''
        tick = int.from_bytes(data[core+5:core+7], 'little')
        num  = int.from_bytes(data[core+7:core+9], 'little')
        return f'tick={tick} Number={num}'
    except Exception:
        return ''

def _rec(s, direction, kind, detail):
    """Append one event to a session's flight-recorder ring. direction: 'C->S' or 'S->C'.
    kind: short tag (RELRX/RELTX/UNREL/EVENT). detail: compact human string. Never raises."""
    if not FLIGHT_RECORDER:
        return
    try:
        buf = getattr(s, '_rec_rel', None)
        if buf is None:
            return
        (s._rec_unrel if kind == 'UNREL' else s._rec_rel).append(
            (time.time(), direction, kind, detail))
    except Exception:
        pass

def _rec_dump(s, reason):
    """Flush a session's flight-recorder rings to logs/flightrec/<pilot>_<ts>.log. Merges the
    reliable and unreliable rings in time order. Returns the path written, or None."""
    if not FLIGHT_RECORDER:
        return None
    try:
        rel = list(getattr(s, '_rec_rel', []) or [])
        unr = list(getattr(s, '_rec_unrel', []) or [])
        if not rel and not unr:
            return None
        os.makedirs(FLIGHT_REC_DIR, exist_ok=True)
        pilot = (getattr(s, 'current_pilot', None) or 'unknown')
        safe = re.sub(r'[^A-Za-z0-9_.-]', '_', str(pilot))
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(FLIGHT_REC_DIR, f'{safe}_{ts}.log')
        merged = sorted(rel + unr, key=lambda e: e[0])
        t0 = merged[0][0] if merged else time.time()
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f'# Flight recorder dump - {pilot} - {reason}\n')
            f.write(f'# {datetime.now().isoformat()}  rel={len(rel)} unrel={len(unr)}\n')
            f.write(f'# t=seconds since first captured event\n#\n')
            for (t, d, k, det) in merged:
                f.write(f'[{t - t0:+7.3f}] {d:3} {k:6} {det}\n')
        return path
    except Exception as e:
        log('REC', f'dump failed: {e}')
        return None

_TELEM_MARK = b'\x05\x42\x00\x00\x07'
# When relaying, stamp the object tick to the RECIPIENT's own latest conductor tick
# minus this small lead, so the receiver's move loop (FUN_007e4a20 ->
# nMoveCycles=(short)(recvTick-objTick)) sees a small POSITIVE delta = the object is a
# couple cycles behind -> smooth dead-reckon-forward interpolation. 0 already gives a
# small +delta (the recipient's tick is from a few ms ago); a tiny lead adds margin so
# we never cross into the <-12 'future' error window that snapped the plane.
RELAY_TICK_LEAD = 0

# -- msg 2 CREATE-OBJECT (remote plane) --------------------------------------
# Reversed from FA.exe: msg-2 dispatch LAB_007e4e00 + NetPlane ctor @0x4f2850.
# Payload = [1 skip byte] + records.  Plane object record = 41 bytes:
#   [0]      tag = 0x80 | (Type & 0xf) | ((nation & 7) << 4)
#            bit7 (0x80) = HUMAN-owned flag (FUN_004f26b0 'test al,al; jns' @0x4f2714):
#            SET -> GamerClientScore[St] looked up (FUN_004f2560) + bound to the plane
#            (FUN_00427530 -> plane+0x128): name tag renders, kills score to the pilot.
#            CLEAR -> DRONE branch: plane+0x128=0 -> NO name tag, no score (pre-v202 bug).
#            bit7 requires GamerClientScore[St] non-null (created by the tag-0 client
#            record) else the create is rejected ('Trying to create network plane for
#            Human') / null-deref @0x4f286b; the slot persists after first spawn, so
#            object-only re-creates are safe.
#   [1]      plane_type   (PLN_INFO id; FUN_004c46d0 lookup - MUST be valid or CTD)
#   [2]      (unused by ctor)
#   [3]      skin         -> NetPlane+0xb30
#   [4..27]  24B = 6xfloat32 position+orientation -> NetPlane+0xaf0
#   --- trailer @ +28 (13B) ---
#   [28..29] St  (owner ClientNumber, u16)   [30..31] ONumber (u16)   [32..40] 0
# Delivered inside a msg-13 batch (real host: in 13 { 62, 62, 2 }).
SEND_CREATE_OBJECT = True    # emit msg 2 so the remote plane exists (relay then drives it)
PLANE_OBJ_TYPE     = 1       # object Type (HeaderSize 28). If CTD / no plane, try 8.
PLANE_TYPE_ID      = 1       # PLN_INFO plane id - TUNE: must be a plane in the loaded set.
DEFAULT_SKIN       = 0

def build_object_record(st, onumber, nation, plane_type, pos, skin):
    """41-byte PLANE object record (Type 1/8, HeaderSize 28 + 13-byte trailer).
    tag=0x80|Type|nation @[0] (bit7=human-owned: name tag + score binding - v202),
    PLN_INFO id @[1], skin @[3], 6xfloat32 pos/orient @[4:28],
    St (owner ClientNumber u16) @[28], ONumber u16 @[30]."""
    rec = bytearray(41)
    rec[0] = 0x80 | (PLANE_OBJ_TYPE & 0x0f) | ((nation & 7) << 4)   # v202: bit7 = HUMAN-owned
    rec[1] = plane_type & 0xff
    rec[3] = skin & 0xff
    px, py, pz = pos
    struct.pack_into('<6f', rec, 4, px, py, pz, 0.0, 0.0, 0.0)   # position + orientation
    struct.pack_into('<H', rec, 28, st & 0xffff)                 # St (owner ClientNumber)
    struct.pack_into('<H', rec, 30, onumber & 0xffff)            # ONumber
    return bytes(rec)

def build_client_record(st, player_index, name, squadron=0):
    """41-byte CLIENT (owner station) record - Type 0, HeaderSize 35 + 6-byte trailer.
    Layout PROVEN from the client-create parser FUN_004f25b0:
        tag=0 @[0] | Squadron u16 @[1] | name asciiz @[3] |
        St u16 @[35] (the NET::CLIENT<*,512> index - MUST be <512) | PlayerIndex u32 @[37]
    Registers the remote pilot's station so the object record's owner St resolves."""
    rec = bytearray(41)
    rec[0] = 0x00                                                # tag 0 -> client-create path
    struct.pack_into('<H', rec, 1, squadron & 0xffff)           # Squadron
    nb = (name or 'Player').encode('latin1', 'replace')[:31]
    rec[3:3 + len(nb)] = nb                                      # name asciiz (35B header)
    struct.pack_into('<H', rec, 35, st & 0xffff)                # St (client/station number)
    struct.pack_into('<I', rec, 37, player_index & 0xffffffff)  # PlayerIndex
    return bytes(rec)

def build_create_object_2(st, onumber, nation, player_index=0, name='Player',
                          plane_type=None, pos=None, skin=DEFAULT_SKIN, with_client=True):
    """msg 2 CREATE-OBJECT. First spawn = 83-byte [0x02]+client(41)+object(41) (the real
    'in 2'83'): registers the owner NET::CLIENT station THEN the plane bound to it.
    Respawn (with_client=False) = 42-byte [0x02]+object(41) ('in 2'42'). The 0x02 msg-id
    IS the handler's skip byte - NO extra byte (an extra 0 -> tag 0 -> client-create path
    -> bounds-crash; that was the v187 first-attempt CTD on Test1)."""
    pt = PLANE_TYPE_ID if plane_type is None else plane_type
    obj = build_object_record(st, onumber, nation, pt, pos or (0.0, 0.0, 0.0), skin)
    body = bytes([0x02])
    if with_client:
        body += build_client_record(st, player_index, name)
    body += obj
    return build_msg13(body)

def send_create_object_for(src, dst, with_client=True):
    """Tell dst to spawn a NetPlane bound to src's object Number, so src's relayed
    telemetry (same Number) has a 3D object to drive. First create per peer sends the
    full client+object form (registers src's station on dst); re-creates after a respawn
    are object-only (the station persists). reliable (msg 13)."""
    if src.my_obj_number is None:
        return False
    if not with_client:
        # OBJECT-ONLY re-create (airfield change / re-entry): dst may STILL hold this
        # object number. The client ASSERTs !Objects[N] on create (Network.cpp:391) ->
        # creating over a live object is a hard CTD (messages42: dup ONumber=257). Send a
        # bare type-3 OBJECT delete FIRST (same thread -> ordered before the create) so the
        # create lands on an empty slot; if the object was already gone, the delete is a
        # harmless no-op. client_number=None -> the NET::CLIENT station is left intact.
        _predel = build_delete_object_3(onumber=src.my_obj_number, client_number=None)
        send_rel(dst, _predel,
                 f'<- pre-delete obj 0x{src.my_obj_number:04x} on {dst.current_pilot} (re-create resync)',
                 to=3.0)
    pkt = build_create_object_2(st=src.client_number, onumber=src.my_obj_number,
                                nation=(src.nation or 0),
                                player_index=src.player_index,
                                name=(src.current_pilot or 'Player'),
                                plane_type=getattr(src, 'plane_type', PLANE_TYPE_ID),
                                with_client=with_client)
    _form = 'client+object' if with_client else 'object-only'
    send_rel(dst, pkt, f'<- CreateObject 2 ({_form}: {src.current_pilot} St={src.client_number} '
                       f'PI={src.player_index} ONumber={src.my_obj_number} -> {dst.current_pilot})', to=3.0)
    log('CREATE2', f'create-object({_form}) {src.current_pilot} St={src.client_number} '
                   f'ONumber=0x{src.my_obj_number:04x} plane={getattr(src, "plane_type", PLANE_TYPE_ID)} -> {dst.current_pilot}')
    return True

def build_parachuter_record(body, st, onumber, owner_obj=None):
    """23-byte PARACHUTER object record (Type 2) = the CLIENT'S OWN 10-byte body + a 13-byte trailer.

    *** NOTHING HERE IS INVENTED ANY MORE. *** Two CTDs came from me authoring these bytes. The
    bailing client already sends the correct body in its parachute out-4, and we simply copy it.

    The out-4 payload is  [sub=4][ident u16][record BODY of HeaderSize bytes][2 trailing].
    Proof: for a PLANE out-4, pl[7] is the tag (0x91 = human|type1|nation1) and pl[8] is the PLN_INFO
    id - which is exactly the `s.plane_type = pl[8]` this server has relied on since v201. So the
    out-4 body IS the object-record body. For a parachute (HeaderSize 10) the real body is:

        82 80 00 01 00 00 00 00 00 00
        [0] 0x82  tag: TYPE 2, human-owned, nation 0   (I had guessed 0x92 - wrong nation)
        [1] 0x80                                        (I had guessed 0x00 - wrong)
        [2:4] i16 = the PLANE's ONumber -> FUN_004f2530 -> score obj -> PILOT NAME + RANK
        [9] 0     model                                 (I had guessed 1 - wrong)

    Three wrong bytes out of ten; any one of them could be the crash. So: copy the body verbatim and
    only append the trailer, which is the one part the SERVER owns (the client cannot know the object
    number the server will assign).

    Trailer (13 bytes, starts at HeaderSize - see the record loop at LAB_007e4e00):
        [10:12] St       (owner ClientNumber u16)
        [12:14] ONumber  (the parachuter's number, assigned by us)
        [14:23] zero
    """
    b = bytes(body)[:PARACHUTER_HEADER_SIZE]
    b = b + b'\x00' * (PARACHUTER_HEADER_SIZE - len(b))       # defensive: always exactly HeaderSize
    if PARA_DEPLOY_BYTE9 is not None and len(b) > 9:
        # v259: body[9] -> ctor param_6 (deploy/model). 0=freefall, 1=deployed canopy, >=2=cargo.
        _bb = bytearray(b); _bb[9] = PARA_DEPLOY_BYTE9 & 0xFF; b = bytes(_bb)
        log('PARA', f'record body[9] set to {PARA_DEPLOY_BYTE9} (deploy/model selector) '
                    f'-> body={hx(b)}')
    if PARA_FIX_OWNER_REF and owner_obj is not None and len(b) > 3:
        # v261: body[2:4] is the OWNER object number the factory (FUN_004f26b0 case 2) resolves via
        # FUN_004f2530 -> objtable[n] -> the owner's GamerClientScore, then FUN_00427530 binds it to
        # chute+0x128 = the NAME TAG. The bailing client's out-4 body carries ITS OWN LOCAL plane
        # number here (e.g. 0x0101), which does NOT match the peer-visible number the server assigned
        # the plane -> the peer's lookup hits the wrong/empty slot -> no name. (byte9==0 masked this
        # via the ctor's strcpy fallback; byte9>=1 skips that, exposing it.) Overwrite [2:4] with the
        # PEER-VISIBLE plane object number (src.my_obj_number) so the bind resolves and the pilot name
        # renders on the deployed canopy - matching the real game (every chute is named).
        _bb = bytearray(b); struct.pack_into('<H', _bb, 2, owner_obj & 0xffff); b = bytes(_bb)
        log('PARA', f'record body[2:4] set to owner plane 0x{owner_obj & 0xffff:04x} '
                    f'(name bind) -> body={hx(b)}')
    rec = bytearray(b) + bytearray(13)
    struct.pack_into('<H', rec, PARACHUTER_HEADER_SIZE + 0, st & 0xffff)        # St      @ [10]
    struct.pack_into('<H', rec, PARACHUTER_HEADER_SIZE + 2, onumber & 0xffff)   # ONumber @ [12]
    return bytes(rec)

def send_parachuter_telemetry(src):
    """v254: give the parachuter object a POSITION by CLONING the plane's last real telemetry packet
    and retargeting only the ONumber field to the parachuter.

    *** We author NOTHING. *** The type-7 telemetry packet is 88 bytes and its position encoding is
    not fully reverse-engineered (the smooth fields are scattered - likely unaligned floats or a
    bit-packed form; the v243 '3x u16' was a good-enough approximation for a crash MOVEMENT test but
    is NOT the true field). Hand-building it is exactly the guess that CTD'd the client five times on
    the create record. So instead we take the PLANE's most recent real telemetry - a packet the
    bailing client itself produced microseconds earlier, every byte valid - and change only bytes
    [7:9], the ONumber, to the parachuter's number. That answers the client's 'get coord for object
    258' request with a real, self-consistent position at the plane's location.

    Result: the canopy appears at the plane's position (correct - that's where the pilot jumped). It
    does not descend on its own yet (that needs the altitude field, which we haven't safely located),
    but a static-then-removed canopy at the right place is a real improvement on invisible, and it
    cannot crash - every byte is one the client already accepted.
    """
    if not SEND_PARACHUTER_TELEM:
        return
    tel = getattr(src, 'last_plane_telem', None)
    pnum = getattr(src, 'para_obj_number', None)
    if not tel or pnum is None or len(tel) < 9:
        return
    relayed = bytearray(tel)
    struct.pack_into('<H', relayed, 7, pnum & 0xffff)      # ONLY change: ONumber -> parachuter
    _sent = 0
    for p in get_sessions_in_room(src.current_room):
        if p is src or not getattr(p, 'flying', False):
            continue
        # re-stamp the tick to the recipient's clock, exactly like a normal relay (known-safe form)
        rt = getattr(p, 'last_telem_tick', None)
        outb = bytearray(relayed)
        if rt is not None:
            struct.pack_into('<H', outb, 5, (rt - RELAY_TICK_LEAD) & 0xFFFF)
        seq = getattr(p, '_relay_seq', 0) & 0xFF
        p._relay_seq = seq + 1
        pkt = bytes([0x00, 0x00, 0x20, seq, 0x00, 0x00, 0x00, 0x00]) + bytes(outb)
        try:
            sock.sendto(pkt, p.addr)
            _sent += 1
            log('PARA', f'  -> sent {len(pkt)}B to {p.current_pilot}@{p.addr} '
                        f'onum=0x{pnum:04x} pkt={hx(pkt[:20])}...')
        except OSError as e:
            log('PARA', f'  -> sendto FAILED to {p.current_pilot}@{p.addr}: {e}')
    log('PARA', f'telemetry for parachuter 0x{pnum:04x} ({src.current_pilot}) cloned from the '
                f'plane\'s last packet -> room {src.current_room}, {_sent} peer(s) sent')

def send_parachuter_create_for(src, dst):
    """Tell dst to create the NetParachuter for src's bailed-out pilot. The record is the client's own
    out-4 body plus our trailer, so the tag shows the PILOT's name and rank (the body points at the
    pilot's plane, which resolves the score object) rather than an aircraft type.

    v257: optionally PRIME the pilot's score block first. The 2009 ground truth shows object-only
    parachuter creates ('in 2'24') preceded by one or two 'in 25'46' score blocks - our bare create
    ('in 13'27 { in 2'24 }') has none. The parachuter's deploy/canopy state may depend on a valid
    score binding, so we send dst a msg-25 for src's pilot immediately before the create. Gated by
    PARA_PRIME_SCORE so it can be turned off if it makes no difference."""
    body = getattr(src, 'para_body', None)
    if not body or getattr(src, 'para_obj_number', None) is None:
        return False
    if PARA_PRIME_SCORE:
        try:
            send_stat_block_25(src, reason=f'(parachuter prime -> {dst.current_pilot})', dst=dst)
        except Exception as _e:
            log('PARA', f'score-prime skipped: {_e}')
    rec = build_parachuter_record(body, st=src.client_number, onumber=src.para_obj_number,
                                  owner_obj=src.my_obj_number)
    pkt = build_msg13(bytes([0x02]) + rec)      # -> the client logs  in 2'24
    send_rel(dst, pkt, f'<- CreateObject 2 (PARACHUTER: {src.current_pilot} '
                       f'ONumber=0x{src.para_obj_number:04x} -> {dst.current_pilot})', to=3.0)
    log('PARA', f'create-parachuter {src.current_pilot} St={src.client_number} '
                f'ONumber=0x{src.para_obj_number:04x} rec={len(rec)}B '
                f'body={hx(bytes(body))} -> {dst.current_pilot}')
    return True
    """23-byte PARACHUTER object record (Type 2). *** SIZE PROVEN FROM THE BINARY. ***

    v248 sent a 41-byte PLANE-shaped record here and it CTD'd the peer. The msg-2 record loop
    (LAB_007e4e00) shows exactly why - every record is [HeaderSize bytes of body][13-byte trailer],
    and HeaderSize is looked up PER TYPE from a table at 0xa30c98 (stride 3 dwords):

        mov   al, [edi]                    ; rec[0] = tag
        and   eax, 0xf                     ; TYPE = tag & 0x0f
        lea   ebx, [eax + eax*2]           ; TYPE * 3
        mov   esi, [ebx*4 + 0xa30c98]      ; HeaderSize
        movzx eax, word ptr [esi+edi+2]    ; ONumber = *(u16*)(rec + HeaderSize + 2)
        add   esi, edi                     ; param_1 = rec + HeaderSize   (the TRAILER)
        push  edi                          ; param_2 = rec               (the BODY)
        call  ...                          ; -> FUN_004f26b0(trailer, body)
        lea   edi, [edi + ebx + 0xd]       ; ADVANCE: rec += HeaderSize + 13

    The table reads:  TYPE 0 (client) = 35 -> 48   TYPE 1/8 (plane) = 28 -> 41
                      TYPE 2 (PARACHUTER) = 10 -> *** 23 ***
    and 23 is exactly what the 2009 session log shows on the wire ('in 2'24' = 1 + 23; and
    'in 2'65' = 1 + 41 + 23 for a client+parachuter pair). Sending 41 meant the loop advanced 18
    bytes too far and parsed a bogus record out of the tail -> the documented tag-0 bounds-crash.

    LAYOUT (body 10 + trailer 13):
        [0]      tag = 0x80 | Type(2) | nation<<4.  bit7 = HUMAN-owned: the handler looks up
                 GamerClientScore[St] and binds it, which is what puts the PILOT'S NAME and RANK on
                 the canopy instead of an aircraft tag. (The station already exists from the plane's
                 client record, so the 'no GamerClientScore' assert can't fire.)
        [2:4]    i16 OWNER OBJECT NUMBER -> FUN_004f2530() -> the score object. The ctor
                 (FUN_004a8c20) copies the pilot's name from owner+0x154 and binds the score.
        [9]      model: 0/1 = ParaTrooper, >1 = ParaCargo. The 2009 log always loads
                 PLANES\PARA\ParaTrooperlod0.Q6, so 1.
        [10:12]  St (owner ClientNumber, u16)   <- TRAILER starts at HeaderSize, NOT at 28
        [12:14]  ONumber (u16) - the PARACHUTER's own number
        [14:23]  rest of the trailer, zero
    [1], [4:8] and [8] are passed to the ctor but not yet identified; left 0.
    """
    rec = bytearray(PARACHUTER_HEADER_SIZE + 13)              # 10 + 13 = 23
    rec[0] = 0x80 | (PARACHUTER_OBJ_TYPE & 0x0f) | ((nation & 7) << 4)
    struct.pack_into('<h', rec, 2, owner_obj & 0x7fff)        # must be >= 0 or the score is skipped
    rec[9] = model & 0xff
    struct.pack_into('<H', rec, PARACHUTER_HEADER_SIZE + 0, st & 0xffff)        # St      @ [10]
    struct.pack_into('<H', rec, PARACHUTER_HEADER_SIZE + 2, onumber & 0xffff)   # ONumber @ [12]
    return bytes(rec)

def _dead_v250_send_parachuter_create_for(src, dst):
    # *** DEAD CODE - superseded by send_parachuter_create_for above (v251). ***
    # Renamed rather than deleted only because it is a 60-line block and surgical deletion over a
    # flaky filesystem link is riskier than leaving it inert. It is never called. Safe to delete.
    """Tell dst to create the NetParachuter for src's bailed-out pilot, bound to src's PLANE object
    so the tag shows the pilot's name and rank (not the aircraft type). Without this the peer has no
    object to render and the parachute is simply invisible - which is exactly what was happening:
    "Create NetParachuter" appears in NEITHER client's log, ever."""
    if getattr(src, 'para_obj_number', None) is None or src.my_obj_number is None:
        return False
    rec = build_parachuter_record(st=src.client_number, onumber=src.para_obj_number,
                                  nation=(src.nation or 0), owner_obj=src.my_obj_number)
    pkt = build_msg13(bytes([0x02]) + rec)          # object-only form; the station already exists
    send_rel(dst, pkt, f'<- CreateObject 2 (PARACHUTER: {src.current_pilot} '
                       f'ONumber=0x{src.para_obj_number:04x} owner-plane=0x{src.my_obj_number:04x} '
                       f'-> {dst.current_pilot})', to=3.0)
    log('PARA', f'create-parachuter {src.current_pilot} St={src.client_number} '
                f'ONumber=0x{src.para_obj_number:04x} bound to plane 0x{src.my_obj_number:04x} '
                f'-> {dst.current_pilot}')
    return True

def build_delete_object_3(onumber=None, client_number=None, x=0.0, z=0.0):
    """In-game msg type 3 (object/client DELETE) - handler FUN_007e3bb0 @ 0x7e3bb0.
    Drops the rendered NetPlane from the in-game OBJECT table (ARR<NET::OBJECT*,2048>
    @ worldobj+0x203). Lobby msg-63 REMOVE only clears the roster/REMOTE_PLAYER, NOT
    the in-world object - this is the only thing that removes the 3D plane on peers.
    Wire layout (decompiled):
      [0]   u8  = 3
      [1:5] f32 = X ref-coord  (0.0 -> ABS<thresh -> NO death effect = silent removal)
      [5:9] f32 = Z ref-coord  (0.0)
      [9:]  u16 LE entries, looped until len-9 consumed (2 bytes each):
              val & 0x8000 == 0 -> delete OBJECT number = val        (index < 2048)
              val & 0x8000 != 0 -> delete CLIENT number = val&0x7fff (index < 512),
                                   cascades to all that client's objects.
    Delete the object FIRST, then the client, so the client-delete finds no objects
    (avoids the 'client have objects: maybe crash' branch). Wrapped in the msg-13 batch
    container + byte-exact framing, exactly like create_object_2 (type 2)."""
    body = bytearray([0x03])
    body += struct.pack('<ff', x, z)
    if onumber is not None:
        body += struct.pack('<H', onumber & 0x7fff)                    # delete OBJECT (top bit clear)
    if client_number is not None:
        body += struct.pack('<H', (client_number & 0x7fff) | 0x8000)   # delete CLIENT (cascade)
    return build_msg13(bytes(body))

def build_scored_delete_object_3(onumber, x=0.0, z=0.0):
    """Type-3 delete carrying a SCORED-kill tail so the recipient (the KILLER) runs the
    NET::OBJECT ExitData path and credits the kill on its own scoreboard.
    RE (this is the whole reason the killer never scored before):
      * FUN_007e3bb0 (type-3 handler) calls an object's delete method (vtable+0x10) ONLY
        when the entry has >2 bytes after the id (uVar4>2). Our bare delete is exactly
        [id:2] -> method skipped -> plane removed, no score.
      * vtable+0x10 = FUN_004f8f20 'ExitDataArrive'. It reads exitByte@+2 = (MEC<<4)|EEC.
        EEC (low nibble) sets the entry size via its return: EEC=3 -> returns 0xc -> 12-byte
        entry. MEC (high nibble)=5 -> the kill-score branch (FUN_00478640), gated on
        vtable+0xc==0 (true for a REMOTE object = the victim on the killer's screen), so
        it credits THIS client from its own local damage list. The victim's real exit
        byte was 0x53 = MEC 5 | EEC 3 - exactly that combo.
      * Entry = [id:2][0x53][9 bytes] = 12B; the 9 tail bytes aren't read on the MEC=5
        path (credit is local), so they're zero filler to reach 12B.
    Body = [03][X:f32=0][Z:f32=0][id:2][0x53][00*9] = 21B (client logs 'in 3'21'). X/Z=0
    keeps it a silent removal (no death-effect call), same as the bare delete."""
    body  = bytearray([0x03])
    body += struct.pack('<ff', x, z)
    body += struct.pack('<H', onumber & 0x7fff)   # object id, top bit clear
    body += bytes([0x53])                          # exit byte: MEC=5 (score) | EEC=3 (12B entry)
    body += bytes(9)                               # filler -> entry = 12B (unused on MEC=5 path)
    return build_msg13(bytes(body))

# -- v228: EXIT-TAIL DELETE (generalised) --------------------------------------
# FUN_007e3bb0 (the type-3 handler) only calls an object's ExitDataArrive (vtable+0x10 =
# FUN_004f8f20) when the entry carries MORE THAN 2 BYTES after the id. Our BARE delete is exactly
# [id:2], so the method is skipped -> the plane vanishes and NO statistics are touched. That is the
# in-game stat feed we were missing.
#
# ExitDataArrive decodes the exit byte as  EEC = b & 0xf,  MEC = b >> 4  and - crucially - RETURNS
# THE ENTRY SIZE, chosen by EEC. The size we send MUST match, or the handler's parse loop desyncs
# and walks off the entry (peer CTD). The table below is lifted straight from its switch:
EXIT_EEC_ENTRY_SIZE = {
    0x0: 3,  0x1: 3,          # -> MEC switch: 1/7 and 8/0xc do announce + effects
    0x2: 4,
    0x3: 12, 0x4: 12, 0x5: 12, 0x7: 12, 0x8: 12, 0x9: 12,   # parse exit struct, then MEC:
                                                            #   4        -> kill announcement (names)
                                                            #   5,6,0xb  -> FUN_00478640 MISSION EVENT
    0xc: 4,
    0xd: 13,
    0xe: 6,
}

def build_exit_delete_object_3(onumber, exit_byte, entry=None, x=0.0, z=0.0):
    """v229: a type-3 delete carrying the victim's REAL EXIT ENTRY, so every recipient runs
    ExitDataArrive AND can attribute the kill.

    *** v229 - THE TAIL IS NOT FILLER. *** v228 (and build_scored_delete_object_3 before it) zero-
    filled the 9 tail bytes on the claim that "the tail isn't read on the MEC=5 path". That was
    WRONG. ExitDataArrive calls FUN_004f8d10 on EVERY 12-byte form BEFORE the MEC switch, and that
    parser reads the tail:
        entry+0 u16 : the exiting object's id
        entry+2 u8  : EXIT byte = (MissExitCode << 4) | ScoreEvent
        entry+3 u16 : *** the HUNTER - the object number that killed it *** (0xffff = none)
        entry+5 u16 : (0xffff = none)
        entry+7 u32 :
        entry+11 u8 : PPT type (low 5 bits)
    Live proof - Test2 shot down by Bigalon (run 073215):
        03 | 01 01 | 53 | 00 01 | 00 00 | 00 00 00 00 | 0c
             id=257  exit  ^^^^^ hunter = 0x0100 = 256 = Bigalon's object
    We were sending zeros there, so the killer's client saw hunter=0 and had nothing to credit.
    THAT is why a kill never registered.

    So: pass the victim's ORIGINAL entry bytes through verbatim. `entry` is taken straight out of
    the client's own delete-notify ([sub 0x03][id u16][exit][tail...]) and re-emitted after the
    [03][X][Z] header the type-3 handler expects. The entry length still has to agree with what
    ExitDataArrive returns for this EEC (EXIT_EEC_ENTRY_SIZE) or its parse loop desyncs -> peer CTD.
    Falls back to a zeroed tail only if the caller has no real entry.
    """
    size = EXIT_EEC_ENTRY_SIZE.get(exit_byte & 0xf)
    if size is None or size < 3:
        return None                                  # unknown EEC -> don't risk a desync
    body = bytearray([0x03])
    body += struct.pack('<ff', x, z)                 # X/Z = 0 -> silent removal, no death effect
    if entry is not None and len(entry) >= size:
        body += bytes(entry[:size])                  # the victim's REAL entry (hunter intact)
    else:
        body += struct.pack('<H', onumber & 0x7fff)  # fallback: id + exit + zero tail
        body += bytes([exit_byte & 0xff])
        body += bytes(size - 3)
    return build_msg13(bytes(body))

# -- msg 33 (0x21) SCORE-EVENT / kill credit ---------------------------------
# v203. The AUTHORITATIVE kill-credit message the 2009 live host sent (messages04): after a
# victim's 'in 3'21' delete (MEC=5,EEC=3 = shot down by enemy), the host sent the KILLER
# a separate 'in 33'14' ScoreEvent. Decoded from FUN_004f9ad0 -> FUN_004f9b0f (ScoreEvent
# handler, VNet_Rcv.cpp:0x364):
#   payload (14B) = [0x21][b1][PlayerIndex:u16 LE][Type:u8][9B tail]
#     * PlayerIndex @[2:4] -> FUN_004f2530 resolves the SCORED player (the killer). It is
#       the killer's PlayerIndex, NOT an object number (the log's 'Number=%i' prints the
#       resolved player's object, which is why the capture looked like the killer's obj).
#     * Type @[4]:  MEC = Type & 0x0f  (LOW nibble),  EEC = Type >> 4  (HIGH nibble)
#       -- opposite nibble order to msg 3's exit byte (msg3 = (MEC<<4)|EEC). The handler
#       ASSERTS EEC in {2,3} on the MEC==1 branch, runs the kill-credit path, and sets
#       killer_plane+0xbf = 1 (kill tallied). The awarded POINTS are NOT in the payload ->
#       the killer's client computes them from its own local damage list (same source the
#       scored-delete MEC=5 path uses); msg 33 is purely the TRIGGER.
#     * b1 @[1] and the 9B tail are not read on the MEC=1/EEC=3 credit path -> zero filler.
#   For a confirmed enemy-player kill: MEC=1, EEC=3 -> Type = (3<<4)|1 = 0x31.
#   MEC/EEC codes (2009 ExitDataArrive/ScoreEvent census, messages04):
#     MEC: 1=alive/credit 2=collision 5=shot-down-by-fire 9=crashed/ditched 10=disconnect
#     EEC: 0=no-enemy(self/terrain) 3=enemy-player 12/13=other-cause 1/2/4=special
# Framed standalone-reliable via build_ingame_pkt (the client routes the 0x21 id through the
# VNET table exactly as it did inside the 2009 host's msg-13 batch).
MSG_SCORE_EVENT_33 = 0x21

# v224: msg-33 ScoreEvent codes. TYPE byte = (MEC << 4) | EEC (MEC high, EEC low - see the handler
# at 0x004f9ae0). MEC = MissExitCode, EEC = ExitEventCode.
#   EEC MUST NOT BE 1: EEC==1 is the announce-only branch (asserts MEC in {2,3}, prints the kill
#   message and jumps past the scoring code) - that swap is exactly what broke kill counting.
#   MEC then selects the mission event: 1 -> event 0x26 + score_obj+0x2fc=1 (a shot-down kill,
#   matching the client's own "MissExitCode=1, ScoreEvent=1" scored exit); 4 -> event 0x26;
#   5 -> event 0x25. Tune here if the HUD still doesn't tick.
SCORE33_MEC = 1              # -> type byte 0x13 with EEC=3
SCORE33_EEC = 3

# v226: RELAY the client's own msg-33 EXIT-EVENT to the other players in the room.
# Msn_Exit.cpp (FUN_0045d930) shows the dying plane's ExitEvent carries a HITS LIST - who hit it and
# each hitter's damage share - which is how FA attributes a kill. The receiving handler (0x004f9ae0)
# is what ticks each client's Current Life / Current Game statistics. We were SWALLOWING it (v222's
# NO_ECHO_TYPES), so no client ever ran its stat pipeline -> kills, deaths and planes-lost all stuck
# at 0. Relay it verbatim to the peers; NEVER echo it back to the sender (the sender re-ingesting its
# own 0xFFFF object index is the ARR<NET::OBJECT*,2048>[65535] bounds CTD).
RELAY_EXIT_EVENT_33 = True

# v228: carry the victim's EXIT TAIL on the type-3 delete sent to peers. The type-3 handler
# (FUN_007e3bb0) only calls ExitDataArrive (FUN_004f8f20) when the entry has >2 bytes after the id,
# so a BARE delete removes the plane and touches NO statistics. With the tail, each recipient runs
# its stat pipeline (and on the MEC 5/6/0xb branch credits the kill from its OWN damage list).
# The entry size is derived from EEC via EXIT_EEC_ENTRY_SIZE - the handler's own table - because a
# size mismatch desyncs its parse loop and CTDs the peer. Set False to fall back to bare deletes.
EXIT_TAIL_DELETE_TO_PEERS = True

def build_score_event_33(player_index, mec=None, eec=None):
    """msg 33 ScoreEvent - credit a confirmed kill to `player_index` (the killer).

    WIRE (confirmed from the handler at 0x004f9ae0, VNet_Rcv.cpp):
        [0]   0x21 msg id
        [1]   unused
        [2:4] u16 LE PlayerIndex   <- handler: movzx eax, word[payload+2] -> score-obj-by-PI getter
        [4]   TYPE byte: HIGH nibble = MEC, LOW nibble = EEC
        [5:]  tail (>=9B): +5 u16, +7 u16, +9 u32 objnum, +13 PPT-type byte. Total 14B.
    The handler logs it as "ScoreEvent. Number=%i. MEC=%i, EEC=%i." - grep the client log for that
    line to confirm what it actually decoded.

    *** v224 BUG FIX - THE NIBBLES WERE SWAPPED ***
    We used to emit ((eec<<4)|mec). The handler does:
        cl = type & 0x0f   -> EEC     (LOW  nibble)
        al = type >> 4     -> MEC     (HIGH nibble)
    so our MEC=1/EEC=3 went out as 0x31 and the client read it as MEC=3, EEC=1 - the exact swap.
    EEC==1 is the ANNOUNCE-ONLY branch (it asserts MEC in {2,3}, prints the kill message via
    string 0x83 and then JUMPS PAST the scoring code). That is why a kill produced at most a chat
    line and NEVER incremented the HUD / in-game statistics.

    The scoring path needs EEC != 1, and then MEC selects the mission event:
        MEC==1 -> vtable[+0x14] check, then FUN_00478640(event 0x26) and score_obj+0x2fc = 1
        MEC==4 -> FUN_00478640(event 0x26)
        MEC==5 -> FUN_00478640(event 0x25)
    MEC=1 matches the client's own scored exit (its log shows "MissExitCode=1, ScoreEvent=1" for a
    shot-down, vs MissExitCode=26 for a solo crash), so MEC=1/EEC=3 -> type byte 0x13 is the
    enemy-player kill credit.
    """
    mec = SCORE33_MEC if mec is None else mec
    eec = SCORE33_EEC if eec is None else eec
    body = bytearray([MSG_SCORE_EVENT_33])
    body += bytes([0x00])                                  # b1 (unused on credit path)
    body += struct.pack('<H', player_index & 0xFFFF)       # killer PlayerIndex
    body += bytes([((mec & 0xf) << 4) | (eec & 0xf)])      # TYPE: MEC high, EEC low  (v224: was swapped)
    body += bytes(9)                                       # tail filler -> 14B ('in 33'14')
    return build_ingame_pkt(bytes(body))

def send_score_event_to_killer(killer, mec=None, eec=None):
    """Send the killer an authoritative msg-33 ScoreEvent so its in-game scoreboard ticks
    the kill (independent of whether its local damage list survived the relay). Reliable."""
    if killer is None or getattr(killer, 'player_index', None) is None:
        return
    mec = SCORE33_MEC if mec is None else mec
    eec = SCORE33_EEC if eec is None else eec
    pkt = build_score_event_33(killer.player_index, mec=mec, eec=eec)
    threading.Thread(target=lambda: send_rel(killer, pkt,
                     f'<- SCORE_EVENT 33 (credit kill to {killer.current_pilot} '
                     f'PI={killer.player_index}, MEC={mec} EEC={eec} -> type=0x{((mec & 0xf) << 4) | (eec & 0xf):02x})',
                     to=3.0), daemon=True).start()
    log('SCORE33', f'ScoreEvent -> {killer.current_pilot} PI={killer.player_index} '
                   f'(MEC={mec},EEC={eec} -> type byte 0x{((mec & 0xf) << 4) | (eec & 0xf):02x})')

# -- Combat scoring constants ----------------------------------------
KILL_SCORE_POINTS   = 100    # flat points for an air kill (global scoring); tune to taste
ACE_KILLS_PER       = 5      # v219: career kills per 'ace' (classic 5-kill ace). Used by pilot_aces()
                             # to derive the msg-88 aces value from the DB career kills. Set 0 to
                             # always report 0 aces.
SEND_ACE_RANK_88    = True   # v219: send an authoritative msg-88 (AceOrRankChangedCB) with the pilot's
                             # REAL career aces/rank READ FROM THE DB. The score object's aces (+0x50)
                             # and rank (+0x30) are set ONLY by msg 88; without it they hold
                             # uninitialised memory -> the garbage '96 Aces'/bogus-rank on the
                             # scoreboard after a team-swap re-entry. Sent on spawn AND on team/room
                             # change, because the client's score object PERSISTS across those
                             # transitions and re-announces its (garbage) ace status at the change.
                             # NOTE: a team/room change must NOT zero a pilot's real score - we
                             # RE-READ the career values from the DB and re-push them. Set False to
                             # disable.
SEND_SCORE_EVENT_33 = False  # v242: OFF. This sent the killer a SECOND, separate credit event
                             #   (msg-33 ScoreEvent) on top of the exit-tail delete. It was added
                             #   back in v203 when the kill wasn't registering AT ALL - but v229 made
                             #   the exit entry carry the real HUNTER, so ExitDataArrive now credits
                             #   the kill on its own. Two events for one kill is almost certainly why
                             #   "Fighters Assists" tracked "Fighters Destroyed" exactly: the client
                             #   scored the kill once and the duplicate as an assist. An assist should
                             #   only count when you DAMAGED a target that SOMEONE ELSE killed.
                             #   Flip back to True if kill credit regresses.
SEND_PARACHUTER_TELEM = False # v256: OFF. Telemetry is the WRONG mechanism for a parachuter and
                             #   was actively harmful. v255 proved the client receives our cloned
                             #   plane-telemetry but can't map it to the type-2 canopy object -> it
                             #   logs "Get coord for missing object 0" and ignores it. The 2009 ground
                             #   truth shows a real parachuter gets NO telemetry at all - it is created
                             #   with a seeded position and FREE-FALLS locally on each client. So we
                             #   send none. See PARA_SERVER_DELETE for the real lifecycle.
PARA_SERVER_DELETE  = True   # v256: end the canopy the way a real server does - a type-3 "Server
                             #   require delete object N" after the descent completes. Without it the
                             #   client culls the canopy as a stale/disconnected object (bsr=0) at
                             #   ~28s; with it the client removes it cleanly (bsr=1, server-required)
                             #   when it 'lands'. This is the same delete path we use for planes.
PARA_DESCENT_SECONDS = 20    # v256: how long the canopy free-falls before the server lands it. The
                             #   2009 log shows 5-21s scaling with bail ALTITUDE; 20s is a safe
                             #   fixed value for now (a high bail). TODO: derive from the plane's
                             #   last-known altitude once the type-7 altitude field is located.
PARA_PRIME_SCORE    = True   # v257: send the peer a msg-25 score block for the bailing pilot right
                             #   before the parachuter create, matching the 2009 wire ('in 25'46'
                             #   blocks precede object-only parachuter creates). May be what lets the
                             #   remote canopy bind identity and DEPLOY (open) rather than just fall.
                             #   Set False if it makes no difference.
MSG20_INSTRUMENT    = False  # v258: log the FULL bytes of every in-game msg-20 (type 0x14). 2009
                             #   showed 'in 20' is a SERVER->CLIENT entity-state broadcast (1820x,
                             #   13-129 bytes, only 8 client replies - not a poll). We capture it to
                             #   learn the state format that must drive the pilotless plane + the
                             #   parachuter descent/deploy after a bail. Pure logging, no behaviour
                             #   change. Set False once the format is understood.
PARA_DEPLOY_BYTE9   = 0      # v259: record body byte[9] = ctor param_6 = the parachuter DEPLOY/model
                             #   selector. RE'd from the master object factory FUN_004f26b0 case 2:
                             #     FUN_004a8c20(body[8], owner, *(body+4), (body[0]&0x70)>>4, body[9])
                             #   ctor param_6 = body[9] drives model + canopy:
                             #     0    = ParaTrooper, FREEFALL, no canopy (the client's own body value)
                             #     1    = ParaTrooper, canopy DEPLOYED (net-create -> FUN_004a6780 sets
                             #            0x324=1); name-tag code flips 0x63 -> 0x70
                             #     >=2  = ParaCargo model, N troops, deployed
                             #     None = leave the client's body byte[9] untouched (freefall)
                             #   The deploy is a CREATE-TIME property, NOT a per-object update msg -
                             #   parachuters ignore both msg-7 (coord) and msg-12 (state). Set to 1 to
                             #   TEST whether the peer renders an OPEN canopy.
PARA_FIX_OWNER_REF   = True   # v261: overwrite parachuter record body[2:4] with the PEER-VISIBLE plane
                             #   object number (src.my_obj_number) so the factory name-bind resolves
                             #   the owner and the pilot NAME renders on the chute. The client's own
                             #   out-4 body carries its LOCAL plane number there, which doesn't match
                             #   the number the server assigned the plane on the peer -> no name.
                             #   Needed for byte9>=1 (deployed) chutes, which skip the ctor's name
                             #   fallback. Matches the real game: every canopy (pilot/paratrooper/
                             #   cargo) is named. Set False to revert to the verbatim client body.
ADD_PLAYER_NOTEAM_NEUTRAL = True  # v260: encode a no-team player's AddPlayer-62 camp as 0xff (handler
                             #   -> camp=-1 'no side' / In Menu) instead of 0 (=US). Fixes Bug A: a
                             #   player who hasn't picked a side showed under US in peers' rosters until
                             #   they chose a team. msg 63 still sets the real side on team-select.
                             #   Set False to revert to the old camp=0 behaviour if -1 mis-buckets.
PARA_TELEM_BURST    = 8      # v254 (unused in v256; kept for the disabled telemetry path)
PARA_TELEM_INTERVAL = 0.5    #   ...spaced this many seconds apart (covers a dropped packet or a
                             #   late create; stops early if the parachuter is removed).
SEND_SCORED_DELETE_TO_KILLER = True   # send the killer a score-tail delete so the kill
                                      #   registers in-game; toggle off for bare deletes.
SEND_PARACHUTER     = True   # *** v253: BACK ON - and this time we KNOW what was crashing. ***
                             #   Bigalon's client log settles it. The CREATE WAS NEVER THE PROBLEM:
                             #       in 2'24
                             #       Receive create object 258
                             #       Create NetParachuter. St=0, ONumber=258
                             #       <<< LOAD OBJECT (PLANES/PARA/ParaTrooperlod0.Q6) >>>
                             #   v251's record parses perfectly and the canopy gets built. I spent
                             #   three versions fixing a record that was fine by the end of the second.
                             #   THE CRASH IS IN THE TELEMETRY THAT FOLLOWS. The ServerConfirm makes
                             #   the bailing client start transmitting the canopy, its telemetry packet
                             #   grows from 84 to 118 bytes, and OUR RELAY REWRITES BYTE 5 OF IT with a
                             #   conductor tick - into a layout we have never parsed. The client then
                             #   reads that tick back as an object index:
                             #       Exception in Fighter Ace engine: bounds error
                             #       class ARR<class NET::OBJECT *,2048>[20983] 0..2047
                             #   20983 is TICK-sized, not object-sized. We crashed it with our own
                             #   re-stamp, not with the parachuter record.
PARA_SEND_CONFIRM   = False  # v253: OFF - this is the one that kills the client. Confirming the
                             #   parachuter makes its owner transmit it, and that bigger telemetry
                             #   form is what we then corrupt. v253 also stops re-stamping unknown
                             #   forms (TELEM_RESTAMP_MAX_LEN), but I am NOT switching both back on at
                             #   once - one variable at a time, given the record so far.
                             #   Consequence: the canopy is CREATED and VISIBLE on peers, but does not
                             #   move (its owner never transmits it). That is a real improvement over
                             #   "invisible", and it cannot crash anyone.
                             #   Turn this on ONLY after a clean run, to test whether the verbatim
                             #   relay now carries the canopy safely.
PARA_SEND_CREATE    = True   # v253: ON - proven safe by Bigalon's own log (the object is built and
                             #   the ParaTrooper model loads).
_SEND_PARACHUTER_TELEM_v254_DEAD = True # v256: DEAD - superseded by SEND_PARACHUTER_TELEM=False above.
                             #   CLONING the plane's last real telemetry packet and retargeting only
                             #   the ONumber. This answers the client's msg-6 'get coord for object
                             #   258' request (which we were swallowing -> 'Unsupported message 6' ->
                             #   canopy never rendered). Every byte is a real packet the client made
                             #   microseconds earlier - nothing is authored, so it cannot CTD. The
                             #   canopy appears at the plane's position; it does not self-descend yet
                             #   (altitude field not safely located). Flip False to disable.
                             #   Two CTDs came from me AUTHORING the parachuter record. v250 fixed the
                             #   SIZE (23 = HeaderSize 10 + 13, proven from the type table at 0xa30c98
                             #   and matching the 2009 wire's `in 2'24`) but the CONTENTS were still my
                             #   guesses - and three of the ten body bytes were wrong.
                             #   THE CLIENT SENDS US THE CORRECT BODY. Its parachute out-4 is
                             #   [sub=4][ident u16][record BODY of HeaderSize bytes][2 trailing]:
                             #       82 80 00 01 00 00 00 00 00 00
                             #   (tag 0x82 = type2|human|nation0 - I had 0x92; [1] = 0x80 - I had 0;
                             #    model [9] = 0 - I had 1; only [2:4] = the plane's ONumber was right)
                             #   So we now COPY the body verbatim and append only the 13-byte trailer,
                             #   which is the one part the server owns (it assigns the object number).
                             #   Flip to False to disable parachutes entirely.
                             #   v248 built the parachuter as a 41-byte PLANE-shaped record. It is
                             #   23 BYTES. The msg-2 record loop (LAB_007e4e00) reads a per-TYPE
                             #   HeaderSize from a table at 0xa30c98 and advances by HeaderSize + 13:
                             #       TYPE 0 (client)      HeaderSize 35 -> 48
                             #       TYPE 1/8 (plane)     HeaderSize 28 -> 41
                             #       TYPE 2 (PARACHUTER)  HeaderSize 10 -> 23   <<<
                             #   The 2009 session log agrees exactly: 'in 2'24' = 1 + 23, and
                             #   'in 2'65' = 1 + 41 + 23 (a client + parachuter pair).
                             #   Sending 41 made the loop advance 18 bytes too far and parse a bogus
                             #   record out of the tail -> the documented tag-0 bounds-crash. That is
                             #   also why "Create NetParachuter" never appeared in the victim's log:
                             #   it died in the record LOOP, before the type switch ever ran.
                             #   St/ONumber live in the TRAILER at rec[10]/rec[12] - not rec[28]/[30].
                             #   Flip to False to disable parachutes entirely.
PARACHUTER_OBJ_TYPE  = 2     # create-object Type nibble (FUN_004f26b0 case 2 = "Create NetParachuter")
PARACHUTER_HEADER_SIZE = 10  # from the type table at 0xa30c98; record = HeaderSize + 13 = 23
SEND_STAT_BLOCK_25  = True   # v236: BACK ON. msg 25 (0x19) writes 20 dwords at score+0x30 via
                             #   FUN_004f65a0 -> FUN_004f4570. v233 disabled it because the probe
                             #   showed nothing - but that was read on the IN-FLIGHT screen, which is
                             #   client-computed session state. The HQ SCORES screen (Latest/Career)
                             #   DOES display the rank, i.e. score+0x30 = f0 of this very block, so it
                             #   reads this structure and the other 19 fields should fill its rows.
SEND_CAREER_ON_HQ   = True   # v237: also push msg 88 + msg 25 whenever the client opens the HQ /
                             #   hangar screen (its 0x3a plane-catalog request). Previously both were
                             #   sent ONLY from the plane-spawn path, so reading HQ -> SCORES without
                             #   flying first showed 0 everywhere simply because nothing had ever been
                             #   sent. That - not a real negative - is why the v236 probe read all 0:
                             #   neither test run contained a single plane spawn.
CAREER_PUSH_DEBOUNCE_S = 2.0 # don't re-push more often than this (the hangar re-requests 0x3a a lot)
KILL_CREDIT_WINDOW  = 30.0   # s: LAST-RESORT fallback only - credit the most-recent OTHER shooter
                             #   within this window. This one is a GUESS, so a clock is appropriate.

# ── v247: EVENT-BASED KILL ATTRIBUTION (no time windows) ──────────────────────
# The kill belongs to whoever the VICTIM'S OWN CLIENT says hit it, and that fact is established the
# MOMENT THE VICTIM REPORTS THE DAMAGE (msg 28) - not when the wreck finally reaches the ground.
# Those two moments can be minutes apart: bail out at 20,000 feet and the empty plane glides for a
# very long time. v246 latched the attribution but still EXPIRED IT ON A TIMER, which is the wrong
# model - any window is just a guess about how long a plane takes to fall, and a high-altitude kill
# will always be able to outlast it.
# So the latch is keyed to the OBJECT and held until THAT OBJECT's delete-notify arrives. No clock.
#   set     : on every msg-28 damage report  (victim object -> hunter object)
#   marked  : on the bail (parachute msg-4)  - purely so the log can say why
#   consumed: when the delete-notify for that object number arrives
#   dropped : when the object number is reused by a new spawn (numbers are recycled)
PENDING_KILL = {}            # ONumber -> {'killer': ONumber, 'at': ts, 'why': 'damage'|'bail'}

# -- v227: which own-plane removals actually count as a DEATH -------------------
# The trailing byte of the msg-3 delete-notify ([.. 0x03][ONumber u16 LE][EXIT byte]) is NOT a
# bitfield - it is the very byte Msn_Exit.cpp builds (FUN_0045d930):
#       EXIT = (MissExitCode << 4) | ScoreEvent
# (MEC is truncated to 4 bits on the wire, so the nibble is MissExitCode & 0xf.)
# DECODED FROM LIVE RUNS:
#   0xa0 -> MEC nibble 0xa, SE 0 : MissExitCode 26 = CRASH.  (26<<4)&0xff == 0xa0 - exact match
#                                  with the client's own "MissExitCode=26, ScoreEvent=0" log.  DEATH.
#   0x11 -> MEC nibble 0x1, SE 1 : re-fly / plane swap. Proven in run 070240: the player was ALONE
#                                  in the arena (so it cannot be a shot-down) and the StartPlace
#                                  request arrives 22ms BEFORE this removal.               NOT a death.
#   0x22 -> MEC nibble 0x2, SE 2 : seen, not yet characterised.                            not a death.
#   0x80 -> MEC nibble 0x8, SE 0 : seen, not yet characterised.                            not a death.
# v225 gated on "bit 0x80 set" which happened to give the right answer for a crash, but that was a
# coincidence of 0xa0/0x80 rather than the real semantics. Classify on the MEC nibble instead, and
# log the decode for every removal so new codes (notably a real SHOT-DOWN MEC, still unobserved) can
# be identified from the logs and added here.
DEATH_MEC_NIBBLES = {0xa, 0x5, 0x6}   # MissExitCode & 0xf values that mean the pilot actually died
                                      #   0xa = MissExitCode 26  -> CRASH (solo)
                                      #   0x5 = SHOT DOWN by a player (exit byte 0x53).
                                      #   0x6 = KILLED BY AA / AI. New in v243, straight off the wire:
                                      #         exit 0x63 -> MEC&0xf=6, SE=3, hunter=0xffff (no player).
                                      #         Run 230703 23:26:16 - flak got the user.
AI_KILL_MEC_NIBBLES = {0x6}           # ...and of those, the ones inflicted by AI/ground fire rather
                                      # than by another player. A loss here goes to "Planes Lost to AI"
                                      # (msg-25 f13) instead of "Planes Lost" (f4). The HQ screen adds
                                      # the two, so the total is right either way - but the breakdown
                                      # is what the game actually tracks.

# -- v243: WAS THE PLANE FLYING WHEN IT WAS REMOVED? ---------------------------
# THE PROBLEM: an undamaged CRASH and a clean PARKED EXIT are byte-identical on the wire (both
# MissExitCode 26 -> exit byte 0xa0), and neither produces a msg 28, so the v232 damage rule can't
# see the crash at all. That's why flying into the ground never counted.
# THE SIGNAL: the telemetry carries a quantised world position at body[0:6] (3x u16). Straight from
# run 230703, the last 4 seconds before each removal:
#     23:08:17  (4526, 64457, 3906) x8 samples, delta EXACTLY 0   -> parked on the runway
#     23:21:07  deltas +551 +572 +633 +647 +712 +791 per sample   -> IN FLIGHT -> this is the crash
#     23:29:08  (34787, 53731, 62007) x8 samples, delta 0         -> landed, parked
# A parked plane reports movement of EXACTLY ZERO, sample after sample; a flying one moves by
# hundreds per tick. The separation is enormous, so this is a robust test and not a fudge.
CRASH_MOVEMENT_WINDOW_S = 3.0   # look back this far when asking "was it moving?"
CRASH_MOVEMENT_MIN      = 64    # total |delta| across the 3 axes over the window. Parked = 0, so
                                #   anything above idle jitter means airborne. The measured value is
                                #   LOGGED on every removal, so tune it from real numbers if a slow
                                #   taxi ever trips it.
COUNT_EXIT_TO_HQ_AS_DEATH = False
DEATH_CONFIRM_DELAY = 4.0    # s: a crash and an EXIT-TO-HQ carry the SAME byte (both MEC 26), so the
                             #   solo death credit is deferred and cancelled if the player leaves the
                             #   arena inside this window. Must exceed the observed removal ->
                             #   back-to-lobby gap (~2.8s). A respawn does NOT cancel it (a genuine
                             #   death respawns ~2s later).
LIVE_ACE_TRACKING   = True   # v222: SERVER-AUTHORITATIVE ace status. FA's rule is a LIVE one -
                             #   ACE_KILLS_PER (5) kills WITHOUT dying earns an ace, and DYING WIPES
                             #   YOUR ACES. The server owns it end-to-end: the DB `aces` column is the
                             #   single source of truth (seeded via the web admin editor), a per-session
                             #   `kills_since_death` streak counter drives the awards, and every change
                             #   is re-stated to the client with msg 88. Set False to freeze aces at
                             #   whatever the DB holds (no live awards, no reset-on-death).

# -- v223: RANK LADDER (score -> rank index) ----------------------------------
#
# WHY THE SERVER OWNS THIS. Reverse-engineering + the official manual agree:
#   * Rank is an INDEX 0..12 (13 ranks). The client hard-clamps it: FUN_00428770 does
#     `if (0xc < rank) rank = 0xc` before looking the name up.
#   * The rank NAME is rendered BY THE CLIENT from its own localized string array (table at
#     0xbf666c, stride 8 -> string index 0x303 + 2*i, via PARR<char const*>::operator[]). The
#     strings are not even in FA.exe. => We only ever send the INDEX; the client prints the name.
#     The RANK_NAMES below are therefore ONLY for our logs and the web admin - purely cosmetic.
#   * An exhaustive scan of .data/.rdata found NO score->rank threshold table anywhere in the
#     client. The original VR-1 host computed rank and pushed it in msg 88's rank byte
#     (AceOrRankChangedCB). So the ladder is ours to define.
#   * Manual (Scores Screen): "Rank - Your pilot's rank. Some arenas are restricted to pilots of
#     certain ranks, to keep competition fair."
#
# RANK_THRESHOLDS[i] = the minimum career score to hold rank i. Must be ascending, 13 entries
# (index 0..12). Rank is recomputed from score after every kill/death and re-stated via msg 88.
# ***** SUPERSEDED BY v249 ***** The invented ladder that used to live here - 13 made-up steps, with
# names like 'Recruit' and 'Air Marshal' that the game has never had, and a flat 50-point death - is
# gone. The REAL ladder, plane values and kill formula are defined immediately below, straight from
# the game's own published scoring page.

# ══════════════════════════════════════════════════════════════════════════════
# OFFICIAL FIGHTER ACE SCORING  (facfs.com/scoring, revised 01/02/2001)
# ══════════════════════════════════════════════════════════════════════════════
# Everything below v249 is straight from the game's own published scoring page. Up to v248 all of
# this was INVENTED (a flat 100 per kill, a 50-point death, and a 13-step rank ladder I made up),
# and it was badly wrong - our thresholds were about 10x too generous, which is why 3,583 points had
# AC2E_Bigalon wearing Lt.Colonel's rank when the real ladder makes that a 2nd Lieutenant.
#
# RANK. The page lists nine ranks with a 1-based "Rank Value". The CLIENT's rank index is that value
# MINUS ONE - proven by our own probes: we sent f0=5 and the client rendered "Major" (Rank Value 6),
# f0=6 rendered "Lieut. Colonel" (Rank Value 7), and rank 0 renders "Cadet" (Rank Value 1).
#       idx  RankValue  Rank                    Score
#        0       1      Cadet                   0 -   999
#        1       2      Sergeant             1000 -  1999
#        2       3      Second Lieutenant    2000 -  3999
#        3       4      First Lieutenant     4000 -  5999
#        4       5      Captain              6000 -  9999
#        5       6      Major               10000 - 13999
#        6       7      Lieutenant Colonel  14000 - 21999
#        7       8      Colonel             22000 - 29999
#        8       9      Brigadier General   30000 - 46000
RANK_THRESHOLDS = [0, 1000, 2000, 4000, 6000, 10000, 14000, 22000, 30000]
RANK_NAMES = [   # cosmetic only (logs / web admin) - the CLIENT prints its own localized name
    'Cadet', 'Sergeant', 'Second Lieutenant', 'First Lieutenant', 'Captain',
    'Major', 'Lieutenant Colonel', 'Colonel', 'Brigadier General',
]
RANK_VALUE = lambda idx: max(1, min(len(RANK_THRESHOLDS), int(idx) + 1))   # the page's 1-based value

# AIR-TO-AIR KILL = value of the plane you shot down  +  a RANK BONUS:
#     "Target-pilot's rank value is divided by the attacker-pilot's rank value, then multiplied
#      by 100.  Example: (Capt / LtCol) x 100 = score bonus."
# So killing UP the ladder pays; farming Cadets as a General barely does.
RANK_BONUS_SCALE = 100

# LOSING POINTS (the page's list, verbatim):
#     Crash .............................. lose the cost of the plane
#     Pilot death ........................ lose 100 points
#     Crash-land in friendly territory ... lose 1/2 the cost of the plane
#     Crash-land in enemy territory ...... lose 100 points PLUS the cost of the plane
#     Bail out over friendly territory ... lose the cost of the plane
# They are separate EVENTS that combine: a plane destroyed costs its value, and a dead pilot costs a
# further 100. (Bailing out over ENEMY territory counts as a death - the page says so under "Pilot
# Deaths" - but we cannot yet tell friendly from enemy ground, so a bail costs the plane only.)
PILOT_DEATH_PENALTY = 100    # "Pilot death: Lose 100 points"

# TABLE 1 - the value of each aircraft. Straight from the page where it lists the plane; FA 4.20 has
# 121 aircraft and the 2001 table covers about half, so the rest are reasoned from their nearest
# listed variant and marked. Values are the points the KILLER gains and the OWNER loses.
PLANE_VALUE_NAMES = {
    # ---------- verbatim from the official table ----------
    'P-40C': 95, 'P-39D': 130, 'P-47D': 165, 'P-38G': 170, 'F4U-1c': 195, 'F4U-4': 195,
    'F6F-3': 190, 'P-51D': 160, 'P-38L': 180, 'TBF-1c': 310, 'A-20Gu': 350, 'A-20Gs': 350,
    'B-25J': 350, 'B-17G': 600,
    'Hurr-IIC': 130, 'Typhoon': 175, 'Spit-Vb_LF': 135, 'Spit-Vb_F': 135, 'Spit-IXc': 170,
    'Spit-IXe': 170, 'Spit-XIV': 180, 'Tempest': 185, 'Mosquito_B_IV': 300,
    'Mosquito_FB_VI': 350, 'Lancaster': 550,
    'I-16': 100, 'LaGG-3': 130, 'La-5FN': 130, 'La-7': 160, 'Yak-1b': 130, 'Yak-3': 150,
    'Yak-9U': 155, 'P-39Q': 150, 'IL-2': 180, 'Pe-8': 650, 'Tu-2': 350,
    'Bf-109E-4/B': 115, 'Bf-109F-4/B': 135, 'Bf-109G-6/R2': 145, 'Bf-109G-6/R6': 145,
    'Bf-109K-4': 175, 'FW-190A-4/U3': 150, 'FW-190A-8/R6': 160, 'FW-190A-8/R3': 160,
    'FW-190A-8/R2': 160, 'FW-190D-9': 165, 'Ju-88': 300, 'Ju-87D-3': 180, 'Ju-87G-2': 180,
    'Do-217E-2': 500, 'Do-217J-1': 500,
    'A6M2': 115, 'A6M5a': 125, 'Ki-43-IIa': 150, 'Ki-61': 150, 'J2M3': 155, 'N1K2-J': 160,
    'Ki-84-1a': 165, 'Ki-84-1c': 165, 'G4M2': 360, 'B5N2': 250, 'Ki-67': 360, 'D3A': 145,
    # ---------- NOT in the 2001 table (FA4.20 additions); nearest listed variant ----------
    'P-40E-1': 100, 'Tomahawk': 90, 'Kittyhawk': 95, 'Kittyhawk-Ia': 95,   # P-40 family (B=90, C=95)
    'F4F-3': 120, 'F4F-4': 125, 'Martlet_I': 120,                          # Wildcat family
    'F4U-1a': 180, 'F4U-4C': 195,                                          # Corsair family
    'Hurr-Ia': 110, 'Hurr-IIb': 130, 'Hurr-IID': 130,                      # Hurricane family
    'Spit-Ia': 120, 'Seafire': 150,                                        # Spitfire family
    'Mosquito_B_IX': 300, 'Mosquito_"Tse-Tse"': 350, 'Mitchell_II': 350, 'Mitchell_III': 350,
    'Avenger_II': 310, 'DB-7B': 350, 'B-25D': 350, 'Dauntless': 200, 'SBD-2': 200, 'B-29': 700,
    'MiG-3': 130, 'Yak-9UT': 155, 'Pe-2': 300, 'Tu-4': 600, 'IL-10': 200, 'Li-2': 200,
    'He-111': 350, 'Ju-52/3m': 200, 'FW-190F-8': 160, 'FW-190D-12': 170,
    'Bf-109E-1/B': 115, 'Bf-110C-4': 200, 'Bf-110G-2': 200, 'Ta-152H-1': 185, 'HA-200': 90,
    'A6M7': 130, 'Ki-100': 160, 'Ki-44-IIc': 150, 'Ki-44-IIc37': 150, 'G5N1': 400,
    'C-47A': 200, 'Dakota_Mk.II': 200, 'L2D2': 200,
    # jets / post-war - no 2001 values exist at all; priced as top-end fighters
    'Me-262A-1': 250, 'Me-163B': 200, 'J9Y': 250, 'MiG-15bis': 250, 'MiG-9': 230,
    'F-86E': 250, 'Meteor_F1': 230, 'Tunnan': 230, 'Ouragan': 220, 'DH.100': 220,
    'FH-1_Phantom': 220, 'Pulqui': 220,
}
PLANE_VALUE_DEFAULT_FIGHTER = 150   # anything unlisted (shouldn't happen; logged at startup)
PLANE_VALUE_DEFAULT_BOMBER  = 300

# TABLE 2 - ground/AI targets. "The score you receive for destroying these units is equal to its cost
# value. If using bombs destroys a moving ground unit, the score is quadrupled." Recorded now so the
# numbers are here when ground scoring is wired up; nothing consumes this yet.
GROUND_TARGET_VALUES = {
    'ammo_bunker': 100, 'hardened_ammo_bunker': 150, 'large_ammo_bunker': 120,
    'fuel_tank': 50, 'hardened_fuel_tank': 100,
    'ammo_factory': 300, 'fuel_factory': 450, 'plane_factory': 300, 'tank_factory': 300,
    'smokestack': 20,
    'barracks': 50, 'church': 100, 'hangar': 150, 'headquarters': 100, 'house': 20,
    'rail_yard': 150, 'shed': 10,
    'truck': 10, 'tank_min': 35, 'tank_max': 85,
}
GROUND_BOMB_MULTIPLIER = 4   # "If using bombs destroys a moving ground unit, the score is quadrupled"

# ASSISTS (not yet implemented - see the changelog): "the kill is awarded to the attacker who did the
# MOST damage. If the other attacker did 20% OR MORE damage as well, he will be awarded an Assist."
# That is the real rule the user described, and it needs per-attacker damage accumulation from msg 28.
ASSIST_DAMAGE_FRACTION = 0.20

DEATH_SCORE_PENALTY = 50     # DEPRECATED by v249 - superseded by PILOT_DEATH_PENALTY + plane cost.
                             # Left defined so any stale reference still resolves.

def plane_value(plane_id):
    """v249: the official point value of an aircraft (Table 1). This is what a killer GAINS for
    shooting it down and what its owner LOSES for losing it."""
    try:
        name = PLANE_ROSTER[int(plane_id)]
    except (TypeError, ValueError, IndexError):
        return PLANE_VALUE_DEFAULT_FIGHTER
    v = PLANE_VALUE_NAMES.get(name)
    if v is not None:
        return v
    return (PLANE_VALUE_DEFAULT_BOMBER if is_bomber_plane(plane_id)
            else PLANE_VALUE_DEFAULT_FIGHTER)

def kill_score(victim_plane_id, victim_rank, killer_rank):
    """v249: the OFFICIAL air-to-air kill score.
           value of the plane  +  (target rank value / attacker rank value) * 100
    Rank VALUE is the page's 1-based number, i.e. our 0-based rank index + 1. Killing UP the ladder
    pays; a General farming Cadets barely scores. Returns (total, base, bonus) for logging.
    """
    base  = plane_value(victim_plane_id)
    bonus = int(round(RANK_VALUE(victim_rank) / RANK_VALUE(killer_rank) * RANK_BONUS_SCALE))
    return base + bonus, base, bonus

def rank_for_score(score):
    """v223: map a career score onto a rank INDEX 0..12 using RANK_THRESHOLDS.
    Returns the highest rank whose threshold the score has reached. Clamped to the client's
    hard ceiling of 12 (FUN_00428770)."""
    try:
        sc = int(score)
    except (TypeError, ValueError):
        return 0
    rank = 0
    for i, need in enumerate(RANK_THRESHOLDS):
        if sc >= need:
            rank = i
        else:
            break
    return min(max(rank, 0), 12)

def db_apply_score_delta(name, delta, bomber=False):
    """v223/v242: add `delta` points to a pilot's career score, recompute their RANK, persist both.

    v242: FA keeps TWO scores - Fighter Score and Bomber Score - and which one you feed depends on
    WHAT YOU WERE FLYING when you earned the points, not on what you shot down. So `bomber` selects
    the column (`bomber_score` vs `score`). RANK is computed from the COMBINED total, since it is a
    single ladder.
    Returns (new_total, new_rank, old_rank) so the caller can log a promotion/demotion.
    """
    if not name:
        return (0, 0, 0)
    conn = sqlite3.connect(DB_PATH)
    have = {r[1] for r in conn.execute("PRAGMA table_info(pilots)").fetchall()}
    _col = 'bomber_score' if (bomber and 'bomber_score' in have) else 'score'
    _bs  = 'COALESCE(bomber_score,0)' if 'bomber_score' in have else '0'
    row = conn.execute(f"SELECT COALESCE(score,0), {_bs}, COALESCE(rank,0) "
                       f"FROM pilots WHERE pilot_name=?", (name,)).fetchone()
    if not row:
        conn.close(); return (0, 0, 0)
    f_score, b_score, old_rank = row[0] or 0, row[1] or 0, row[2] or 0
    if _col == 'bomber_score':
        b_score = max(0, b_score + int(delta))          # never negative
    else:
        f_score = max(0, f_score + int(delta))
    new_total = f_score + b_score
    new_rank = rank_for_score(new_total)
    if 'bomber_score' in have:
        conn.execute("UPDATE pilots SET score=?, bomber_score=?, rank=? WHERE pilot_name=?",
                     (f_score, b_score, new_rank, name))
    else:
        conn.execute("UPDATE pilots SET score=?, rank=? WHERE pilot_name=?",
                     (f_score, new_rank, name))
    conn.commit(); conn.close()
    return (new_total, new_rank, old_rank)

def score_on_death(victim, death_payload, hunter_obj=None, victim_obj=None):
    """Persist a death into the DB and apply the LIVE ace rule (server-authoritative).

    KILLER ATTRIBUTION (v233 - now EXACT):
    The victim's own client names its killer. The delete-notify's exit ENTRY carries the HUNTER
    object number at entry+3 (proven live: Test2's shot-down entry was
    `01 01 | 53 | 00 01 | ...` -> hunter = 0x0100 = 256 = Bigalon's object). So when we have it we
    credit the pilot who actually owns that object - correct for any number of players.
    Only if the hunter is absent/unresolvable do we fall back to the old heuristic (the most recent
    OTHER pilot who relayed a msg-28 within KILL_CREDIT_WINDOW), which is exact for a 1v1 duel but
    only an approximation in an N-player furball.

    TWO DEATH FORMS, BOTH COUNT:
      * long >=14B 'shot-down' form  -> a SCORED kill: victim dies, a killer is credited.
      * short 8B crash/exit form     -> a SOLO death: victim dies, NO killer.
    The victim ALWAYS dies; only the KILLER-attribution needs the long form.

    LIVE ACE RULE (FA's own, confirmed by the manual): ACE_KILLS_PER (5) kills WITHOUT dying earns an
    ace; DYING WIPES YOUR ACES. The DB `aces` column is the single source of truth, a per-session
    `kills_since_death` streak drives the awards, and every change is re-stated via msg 88.
    """
    scored = len(death_payload) >= 14        # long form = shot down by someone
    killer = None
    # v249: capture the victim's object and whether they BAILED **before** the attribution step pops
    # the latch. A bail costs the plane only - the pilot walked away - whereas dying in the cockpit
    # costs a further 100.
    _vo0 = victim_obj if victim_obj is not None else getattr(victim, 'my_obj_number', None)
    _bailed = bool((PENDING_KILL.get(_vo0) or {}).get('why') == 'bail') if _vo0 is not None else False

    # 1) EXACT: the victim's exit entry named its killer (long form only).
    if hunter_obj is not None and hunter_obj > 0 and hunter_obj != 0xffff:
        for p in get_sessions_in_room(victim.current_room):
            if p is not victim and getattr(p, 'my_obj_number', None) == hunter_obj:
                killer = p
                log('KILL', f'attribution: EXACT - victim named hunter obj 0x{hunter_obj:04x} '
                            f'-> {p.current_pilot}')
                break

    # 2) v247: THE LATCH - the victim's own client already told us who hit it (msg 28), and we held
    # that against the OBJECT. This is the path that credits a BAILOUT, and it has NO clock: the
    # empty plane can glide for ten minutes from 20,000 feet and the kill still belongs to whoever
    # shot it down. Consumed here, so it can never be double-counted.
    if killer is None:
        _vo = victim_obj if victim_obj is not None else getattr(victim, 'my_obj_number', None)
        _pk = PENDING_KILL.pop(_vo, None) if _vo is not None else None
        if _pk:
            _hb = _pk['killer']
            for p in get_sessions_in_room(victim.current_room):
                if p is not victim and getattr(p, 'my_obj_number', None) == _hb:
                    killer = p
                    log('KILL', f'attribution: LATCHED ({_pk["why"]}) - obj 0x{_hb:04x} hit '
                                f'obj 0x{_vo:04x} {time.time() - _pk["at"]:.1f}s ago and the plane '
                                f'has now gone down -> {p.current_pilot}')
                    break
            if killer is None:
                log('KILL', f'attribution: latch for obj 0x{_vo:04x} named obj 0x{_hb:04x}, but no '
                            f'session owns that object any more -> no credit')

    # 3) FALLBACK: most-recent shooter inside the credit window. Weakest of the three - a guess, not
    #    a fact - so it only runs when the first two find nothing.
    #    v244: no longer gated on `scored`. That gate meant a SHORT-form death (i.e. a bailout) could
    #    never be attributed at all, which is exactly how Bigalon lost his 3rd kill.
    if killer is None:
        now = time.time(); best = 0.0
        for p in get_sessions_in_room(victim.current_room):
            if p is victim:
                continue
            t = getattr(p, 'last_fired_at', 0.0)
            if t and (now - t) <= KILL_CREDIT_WINDOW and t > best:
                best = t; killer = p
        if killer is not None:
            log('KILL', f'attribution: FALLBACK - nothing named a hunter, crediting the most recent '
                        f'shooter {killer.current_pilot} (within {KILL_CREDIT_WINDOW}s)')

    # ---- VICTIM: always dies. Count it and break the ace streak. ----
    victim.k_deaths = getattr(victim, 'k_deaths', 0) + 1
    victim.kills_since_death = 0

    # v242: AIRCRAFT CLASS decides which columns this kill feeds - and the two questions have
    # DIFFERENT answers:
    #   what the KILLER was flying -> Fighter Score  vs Bomber Score   (points)
    #   what the VICTIM was flying -> Kills>Fighters vs Kills>Bombers  (the kill breakdown)
    # s.plane_type is the PLANE_ROSTER id straight from the spawn packet, so we already know both.
    _victim_bomber = is_bomber_plane(getattr(victim, 'plane_type', None))
    _killer_bomber = is_bomber_plane(getattr(killer, 'plane_type', None)) if killer else False

    # v243: WHO took the plane down - a player, or AA / AI ground fire?
    # The exit code says so outright: MEC nibble 6 (exit byte 0x63, hunter=0xffff) is an AA/AI kill,
    # seen live in run 230703 when flak got the user. Those losses belong in "Planes Lost to AI"
    # (f13), not "Planes Lost" (f4). Anything with no creditable player killer AND an AI exit code
    # counts as lost-to-AI; a solo crash keeps the ordinary player-side column.
    _exitb = death_payload[7] if len(death_payload) > 7 else 0
    _mec   = (_exitb >> 4) & 0xf
    _lost_to_ai = (killer is None) and (_mec in AI_KILL_MEC_NIBBLES)

    if killer is not None:
        killer.k_kills = getattr(killer, 'k_kills', 0) + 1
        killer.k_score = getattr(killer, 'k_score', 0) + KILL_SCORE_POINTS
        db_credit_kill(killer.current_pilot, victim.current_pilot, 0,
                       victim_is_bomber=_victim_bomber)          # counters only
    else:
        db_credit_kill(None, victim.current_pilot, 0, lost_to_ai=_lost_to_ai)
        log('DEATH', f'{victim.current_pilot} lost a plane to '
                     f'{"AA/AI ground fire" if _lost_to_ai else "no creditable shooter"} '
                     f'(exit=0x{_exitb:02x}, MEC&0xf={_mec}) -> '
                     f'{"planes_lost_ai" if _lost_to_ai else "planes_lost"} +1')

    # ---- v249: OFFICIAL SCORING. Points are no longer a flat 100 per kill and 50 per death.
    #   KILL  = value of the plane you shot down  +  (target rank value / your rank value) x 100
    #   LOSS  = the cost of your plane, and a further 100 if the PILOT died
    # The points land in the FIGHTER or BOMBER score depending on what the KILLER was flying (v242);
    # rank is recomputed from the COMBINED total, since it is a single ladder.
    if killer is not None and killer.current_pilot:
        _ks = db_get_pilot_stat25(killer.current_pilot)
        _vs = db_get_pilot_stat25(victim.current_pilot) if victim.current_pilot else {'rank': 0}
        _pts, _base, _bonus = kill_score(getattr(victim, 'plane_type', None),
                                         int(_vs.get('rank', 0)), int(_ks.get('rank', 0)))
        killer.k_score = getattr(killer, 'k_score', 0) + _pts
        _sc, _rk, _old = db_apply_score_delta(killer.current_pilot, _pts, bomber=_killer_bomber)
        _pn = (PLANE_ROSTER[killer.plane_type]
               if isinstance(getattr(killer, 'plane_type', None), int)
               and 0 <= killer.plane_type < len(PLANE_ROSTER) else '?')
        _vn = (PLANE_ROSTER[victim.plane_type]
               if isinstance(getattr(victim, 'plane_type', None), int)
               and 0 <= victim.plane_type < len(PLANE_ROSTER) else '?')
        log('SCORE', f'{killer.current_pilot} +{_pts} = {_base} ({_vn}) + {_bonus} rank bonus '
                     f'[{RANK_NAMES[min(int(_vs.get("rank",0)), len(RANK_NAMES)-1)]} / '
                     f'{RANK_NAMES[min(int(_ks.get("rank",0)), len(RANK_NAMES)-1)]}] '
                     f'-> {"BOMBER" if _killer_bomber else "FIGHTER"} score (flying {_pn}) '
                     f'| total {_sc}')
        if _rk != _old:
            _nm = RANK_NAMES[_rk] if 0 <= _rk < len(RANK_NAMES) else '?'
            log('RANK', f'{killer.current_pilot} PROMOTED rank {_old} -> {_rk} ({_nm}) '
                        f'at score {_sc}')

    # The victim loses the cost of their aircraft, and a further 100 if the PILOT died. A BAIL-OUT
    # costs the plane only - the pilot walked away (over friendly ground at least; the page counts a
    # bail over ENEMY territory as a death, but we cannot yet tell friendly ground from enemy).
    if victim.current_pilot:
        _plane_cost = plane_value(getattr(victim, 'plane_type', None))
        _loss = _plane_cost + (0 if _bailed else PILOT_DEATH_PENALTY)
        _sc, _rk, _old = db_apply_score_delta(victim.current_pilot, -_loss, bomber=_victim_bomber)
        log('SCORE', f'{victim.current_pilot} -{_loss} = {_plane_cost} (plane)'
                     f'{"" if _bailed else f" + {PILOT_DEATH_PENALTY} (pilot death)"}'
                     f'{" [BAILED OUT - pilot survived]" if _bailed else ""} | total {_sc}')
        if _rk != _old:
            _nm = RANK_NAMES[_rk] if 0 <= _rk < len(RANK_NAMES) else '?'
            log('RANK', f'{victim.current_pilot} DEMOTED rank {_old} -> {_rk} ({_nm}) '
                        f'at score {_sc}')

    # DYING WIPES THE VICTIM'S ACES (live rule, server-authoritative).
    if LIVE_ACE_TRACKING and victim.current_pilot:
        _prev = db_get_pilot_career(victim.current_pilot)[4]
        db_set_pilot_aces(victim.current_pilot, 0)
        if _prev:
            log('ACE', f'{victim.current_pilot} DIED -> aces {_prev} -> 0 (streak reset)')

    # ---- KILLER: every ACE_KILLS_PER kills WITHOUT dying earns an ace. ----
    if killer is not None and LIVE_ACE_TRACKING and killer.current_pilot:
        # *** v241: THE STREAK LIVES IN THE DB, NOT IN THE SESSION. ***
        # db_credit_kill has just incremented `kills_in_a_row` (and zeroed the victim's), so that
        # column IS the current run. We used to count a SEPARATE per-session `kills_since_death`
        # that reset to 0 on every login, so any streak already in the DB - whether seeded by the
        # admin or carried over from an earlier session - was silently ignored. With
        # kills_in_a_row=3 seeded, two more kills took the DB to 5 (correct) but the session counter
        # only reached 2, so the ace never fired. Two sources of truth, and we were reading the
        # wrong one. Now there is only one.
        _st = db_get_pilot_stat25(killer.current_pilot)
        _streak = int(_st['kills_in_a_row'])
        killer.kills_since_death = _streak          # session mirror, kept in sync for logging
        if ACE_KILLS_PER > 0 and _streak and _streak % ACE_KILLS_PER == 0:
            _a = int(_st['aces'])
            db_set_pilot_aces(killer.current_pilot, _a + 1)
            log('ACE', f'{killer.current_pilot} earned an ACE '
                       f'({_streak} kills in a row without dying) -> aces {_a} -> {_a + 1}')
        else:
            _next = ((_streak // ACE_KILLS_PER) + 1) * ACE_KILLS_PER if ACE_KILLS_PER else 0
            log('ACE', f'{killer.current_pilot} kills in a row: {_streak} '
                       f'(next ace at {_next})')

    vs = db_get_pilot_stats(victim.current_pilot) or (0, 0, 0)
    if killer is not None:
        ks = db_get_pilot_stats(killer.current_pilot) or (0, 0, 0)
        log('KILL', f'{killer.current_pilot} destroyed {victim.current_pilot} '
                    f'(+{KILL_SCORE_POINTS}) | {killer.current_pilot}: '
                    f'score={ks[0]} kills={ks[1]} deaths={ks[2]} | '
                    f'{victim.current_pilot}: score={vs[0]} kills={vs[1]} deaths={vs[2]}')
    else:
        _why = 'no creditable shooter' if scored else 'solo crash/crashland'
        log('KILL', f'{victim.current_pilot} died ({_why}) | {victim.current_pilot}: '
                    f'score={vs[0]} kills={vs[1]} deaths={vs[2]}')

    # Re-state the authoritative aces/rank to both parties so the change shows immediately.
    # Sent on daemon threads: send_ace_rank_88 -> send_rel blocks for its ACK (to=3.0), and
    # score_on_death runs on the packet-RX path - a blocking send here would stall reception.
    if SEND_ACE_RANK_88:
        def _restate(_sess, _reason):
            try:
                send_ace_rank_88(_sess, reason=_reason)
                send_stat_block_25(_sess, reason=_reason)   # v230: refresh the scoreboard counters too
            except Exception as e:
                log('ACE88', f'[warn] post-death/kill 88 failed: {e}')
        threading.Thread(target=_restate, args=(victim, '(death: aces wiped)'), daemon=True).start()
        if killer is not None:
            threading.Thread(target=_restate, args=(killer, '(kill)'), daemon=True).start()

    return killer   # credited shooter (or None) -> caller sends it the SCORED delete

def broadcast_object_delete_3(s, reason='', clear_peer_created=True,
                              followup_pkt=None, followup_label='', killer=None,
                              exit_byte=None, exit_entry=None):
    """Remove s's NetPlane (object + client station) from every peer in the room.

    clear_peer_created: True for exit-to-HQ (we wiped our whole world, so peers must
    re-create themselves on us when we return); False for an in-place death+respawn
    (we KEEP the peers' objects, so forcing them to re-create would duplicate a live
    object on the peer).

    followup_pkt: optional reliable packet (the msg-63 REMOVE) sent to each peer
    IMMEDIATELY AFTER the type-3 delete, on the SAME thread, so it always carries a
    higher reliable sequence than the delete. The NetPlane holds a pointer to the
    REMOTE_PLAYER, so the plane must be deleted BEFORE the player is freed or a FLYING
    peer use-after-frees the dangling plane (messages03: flying Test2's world died on
    'Test1 leaving game' before any DelObject)."""
    if s.my_obj_number is None or s.current_room is None:
        return
    # SINGLE entry only (object). A 2nd entry trips the handler's variable-length branch
    # and crashes the PEER ('Length=-1', messages77: 'delete object 257' OK then bogus
    # 'delete object 640'). Object-delete alone removes the rendered NetPlane from world +
    # minimap; msg-63 REMOVE (in handle_leave_arena) clears the roster.
    pkt = build_delete_object_3(onumber=s.my_obj_number, client_number=None)
    # v228: EXIT-TAIL DELETE. FUN_007e3bb0 only calls ExitDataArrive when the entry has >2 bytes
    # after the id, so our BARE delete silently removed the plane and touched NO statistics - that
    # is why kills / deaths / planes-lost never ticked in-game. Send every peer a delete carrying
    # the victim's REAL exit byte ((MEC<<4)|ScoreEvent, straight off the client's own delete-notify)
    # with the entry size EEC demands, so each client runs its stat pipeline. On the MEC 5/6/0xb
    # branch the credit is computed from each client's OWN damage list, so this is broadcast to all
    # peers rather than to a guessed killer.
    epkt = None
    if EXIT_TAIL_DELETE_TO_PEERS and exit_byte is not None:
        epkt = build_exit_delete_object_3(s.my_obj_number, exit_byte, entry=exit_entry)
        if epkt is not None:
            _hunter = (struct.unpack_from('<H', exit_entry, 3)[0]
                       if (exit_entry is not None and len(exit_entry) >= 5) else None)
            log('EXITTAIL', f'{s.current_pilot} delete carries exit=0x{exit_byte:02x} '
                            f'(MEC={exit_byte >> 4} EEC={exit_byte & 0xf}, '
                            f'entry={EXIT_EEC_ENTRY_SIZE.get(exit_byte & 0xf)}B'
                            + (f', hunter=0x{_hunter:04x}' if _hunter is not None else ', synthesised')
                            + ') -> all peers')
        else:
            log('EXITTAIL', f'{s.current_pilot} exit=0x{exit_byte:02x} has an unknown EEC '
                            f'({exit_byte & 0xf}) - no size in the handler table, sending bare delete')
    # v229: the killer no longer gets a special ZERO-FILLED scored delete - that was the bug. The
    # real entry (with the HUNTER object id at +3) is what lets a client attribute the kill, so the
    # killer gets the same verbatim exit entry as everybody else. spkt is kept only as a fallback
    # for the case where we somehow have no real entry to relay.
    spkt = (build_scored_delete_object_3(s.my_obj_number)
            if (killer is not None and SEND_SCORED_DELETE_TO_KILLER and epkt is None) else None)
    _dlabel = (f'<- DeleteObject 3 ({s.current_pilot} ONumber=0x{s.my_obj_number:04x} '
               f'St={s.client_number}) {reason}')
    s.__dict__.pop('_created_peers', None)   # re-entry must re-create us on peers
    for sess in get_sessions_in_room(s.current_room):
        if sess is s:
            continue
        # v190: our exit-to-HQ did 'DelObject -1' - the client wiped EVERY object from its
        # world, including each still-flying peer's plane. The relay only re-creates a peer's
        # object on us when our addr is ABSENT from that peer's _created_peers, so drop it now;
        # else on our re-fly the peer keeps streaming telemetry for an object id we never
        # re-created -> 'Get coord for missing object N' -> world-build hang/CTD (messages98).
        # The relay's 'flying' filter holds these re-creates until our ServerConfirm, so the
        # CREATE lands first, then telemetry. _client_created_peers stays intact: DelObject
        # removes only the OBJECT; the NET::CLIENT station persists -> object-only re-create.
        if clear_peer_created:
            pcp = sess.__dict__.get('_created_peers')
            if pcp is not None:
                pcp.discard(s.addr)
            # ARENA-CHANGE CTD (messages39): the comment below was half-right - for an
            # in-arena DEATH the client keeps the peer's NET::CLIENT station (object-only
            # re-create is correct). But on BACK-TO-LOBBY / arena change (clear_peer_created)
            # the leaving client tears its whole world down - the peer's log shows
            # 'del CLIENT <n>' deleting our station, not just our object. If we leave
            # _client_created_peers intact, our re-entry sends an OBJECT-ONLY create whose
            # owner St references a station the peer already deleted -> o->Client()==0 ->
            # assertion Network.cpp:440 -> CTD on the peer. So on a world-teardown exit we
            # must also forget the station, forcing a full client+object re-create next time.
            ccp = sess.__dict__.get('_client_created_peers')
            if ccp is not None:
                ccp.discard(s.addr)
        # v191: send the type-3 DELETE then the optional followup (msg-63 REMOVE) on ONE
        # thread, in that order, so DELETE always gets the lower reliable seq -> a flying peer
        # tears down the NetPlane BEFORE its REMOTE_PLAYER is freed (no dangling-plane CTD).
        # v229: EVERY peer (killer included) gets the victim's VERBATIM exit entry - it carries the
        # HUNTER object id at +3, which is what a client needs to attribute the kill. Zero-filling
        # that tail (v228 and earlier) is exactly why kills never registered.
        _is_killer = (sess is killer and spkt is not None)
        if epkt is not None:
            _delpkt = epkt
            _dl2 = _dlabel + f' [EXIT-ENTRY 0x{exit_byte:02x}]' + (' [killer]' if sess is killer else '')
        elif _is_killer:
            _delpkt, _dl2 = spkt, _dlabel + ' [SCORED->killer, synthesised]'
        else:
            _delpkt, _dl2 = pkt, _dlabel
        def _send(_s=sess, _del=_delpkt, _dl=_dl2, _fu=followup_pkt, _fl=followup_label):
            send_rel(_s, _del, _dl, to=3.0)
            if _fu is not None:
                send_rel(_s, _fu, _fl, to=3.0)
        threading.Thread(target=_send, daemon=True).start()
    log('DELETE3', f'{s.current_pilot} ONumber=0x{s.my_obj_number:04x} St={s.client_number} '
                   f'-> peers in room {s.current_room} {reason}')

# -- v234: TELEMETRY OPCODES -------------------------------------------------
# The flying-state object update is [bc][T][00][00][OPCODE][tick u16][ONumber u16][state...].
# The client emits TWO forms and they are byte-identical in the header:
#     0x07 -> one position sample     (e.g. sz=98)
#     0x08 -> the SAME thing plus one extra 9-byte sample block (e.g. sz=107)
# Live capture (run 092257), same object 0x0101, same tick and ONumber offsets:
#     05 62 00 00 07 f1c4 0101 ...   <- 0x07
#     05 f2 00 00 08 6bc4 0101 ...   <- 0x08
# We only ever matched 0x07. At 09:35:52 AC2E_Bigalon's client switched to emitting 0x08, so the
# relay stopped recognising his telemetry ENTIRELY. Two things then broke, and together they are
# exactly the reported bug ('Test2 disappeared from Bigalon's game, telemetry stopped'):
#   1. Bigalon's updates were no longer forwarded to Test2.
#   2. Worse - we harvest each player's CONDUCTOR TICK from their telemetry and use it to re-stamp
#      the packets we relay TO them. Bigalon's tick froze at 13868 and never advanced, so we kept
#      relaying Test2's telemetry re-stamped with a DEAD tick. Bigalon's client saw Test2's updates
#      as ever-more-stale and dropped them -> TEST2 VANISHED from his world.
# Since the header (tick @5:7, ONumber @7:9) is identical, 0x08 relays exactly like 0x07 - the extra
# block is opaque payload we forward verbatim.
TELEM_OPCODES = (0x07, 0x08)
TELEM_RESTAMP_MAX_LEN = 100  # v253: only re-stamp the telemetry FORM WE KNOW. The single-object
                             #   plane packet has always been <= ~100 bytes. Once a pilot bails and
                             #   also owns a parachuter, the packet grows (Bigalon saw his inbound
                             #   telemetry go 84 -> 118 bytes the moment the canopy existed) and its
                             #   layout is NOT the one we parse. Writing our tick into byte 5 of that
                             #   bigger packet made the client read a TICK where it expected an object
                             #   index:
                             #       Exception in Fighter Ace engine: bounds error
                             #       class ARR<class NET::OBJECT *,2048>[20983] 0..2047
                             #   20983 is tick-sized, not object-sized. Anything outside the known
                             #   form is now relayed BYTE-FOR-BYTE. We do not rewrite bytes we cannot
                             #   parse - that is the same mistake as hand-authoring the record.
STALE_TICK_WARN_S = 3.0      # warn if we re-stamp using a peer tick this old (the failure above was
                             #   silent for ~3 minutes; never let a frozen tick go unnoticed again)

def relay_telemetry(src, data):
    """Forward src's flying-state datagram to other flying players in the same room."""
    pl = data[8:]
    # The flying-state object-update appspace = [bc][T][00][00][07][tick u16][ONumber u16]...
    # T's LOW nibble is 0x2 (appspace-data channel); T's HIGH nibble is the SIZE
    # (Size = bc*16 + T>>4), so it VARIES with payload length - Test1's update is 86B (T=0x62)
    # while Test2's is 84B (T=0x42). The old check pinned T to 0x42 AND blindly stripped a
    # 4-byte prefix whenever pl[:2]!=0x0542, which MANGLED Test1's prefix-less 0x05 0x62 stream
    # ((00 00 07 ...) != marker -> early return -> Test1 never relayed -> peers couldn't see
    # Test1). Match the SIZE-INDEPENDENT signature instead (cmd==0x0000, opcode 0x07, T low
    # nibble 0x2), scanning offset 0 (no prefix) and 4 (sz=100 [seq][flags] prefix).
    _telem = None
    for _off in (0, 4):
        c = pl[_off:]
        if (len(c) >= 9 and c[2] == 0 and c[3] == 0
                and c[4] in TELEM_OPCODES and (c[1] & 0x0f) == 0x02):
            _telem = c
            break
    if _telem is None:
        return                          # not a flying-state object update (e.g. pre-spawn 00c2)
    pl = _telem
    # Record the SENDER's own conductor tick (telemetry[5:7]). We use each player's
    # latest tick to re-stamp packets we relay TO them, so the tick lands on THEIR clock.
    src.last_telem_tick = int.from_bytes(pl[5:7], 'little')
    src.last_telem_time = time.time()
    # v243: and the quantised world POSITION (body[0:6] = 3x u16, i.e. pl[9:15]). This is what tells
    # a CRASH apart from a clean parked exit - the two are byte-identical in the exit packet, so the
    # only way to know the plane was flying is to look at whether it was actually moving.
    if len(pl) >= 15:
        try:
            # v248: only track the PLANE's position. After a bail the parachuter transmits under its
            # own object number, and letting the canopy's drift feed the crash test would be
            # measuring the wrong body entirely.
            _onum_t = int.from_bytes(pl[7:9], 'little')
            if _onum_t == getattr(src, 'my_obj_number', None):
                _p = struct.unpack_from('<HHH', pl, 9)
                _now = time.time()
                _hist = src.__dict__.setdefault('_pos_hist', [])
                _hist.append((_now, _p))
                _cut = _now - CRASH_MOVEMENT_WINDOW_S
                while _hist and _hist[0][0] < _cut:
                    _hist.pop(0)
                # v254: keep the PLANE's most recent COMPLETE telemetry packet. If this pilot bails,
                # we clone this exact packet for the parachuter (retargeting only the ONumber) so the
                # canopy gets a valid position from a byte-for-byte real packet - never a hand-built
                # one. See send_parachuter_telemetry.
                src.last_plane_telem = bytes(pl)
        except struct.error:
            pass
    peers = [x for x in get_sessions_in_room(src.current_room)
             if x is not src and getattr(x, 'flying', False)]
    if not peers:
        return
    for p in peers:
        if SEND_CREATE_OBJECT and src.my_obj_number is not None:
            _cp = src.__dict__.setdefault('_created_peers', set())
            if p.addr not in _cp:
                _cp.add(p.addr)
                # The NET::CLIENT station is created ONCE per peer and PERSISTS across
                # death/respawn/exit-to-HQ (type-3 deletes only the OBJECT, never the
                # client). So only the FIRST create per peer carries the client record;
                # re-creates are object-only - else the peer hits 'Client N already exist'
                # on the duplicate station -> CTD (messages94: in 2'83 after respawn).
                _ccp = src.__dict__.setdefault('_client_created_peers', set())
                _wc = p.addr not in _ccp
                if _wc:
                    _ccp.add(p.addr)
                # Fire the create OFF the RX thread: send_create_object_for blocks up to
                # 3s waiting for the reliable ACK; doing that inline froze the whole
                # server for 3s mid-flight (no beacons/ACKs) -> the peer's keepalive
                # desynced -> FATALLOSTCONNECTION ~30s later (messages54.log).
                threading.Thread(target=send_create_object_for,
                                 args=(src, p), kwargs={'with_client': _wc}, daemon=True).start()
        # Re-stamp the object tick to the RECIPIENT's own latest tick so their move loop
        # sees a small +delta (object slightly behind -> interpolate) instead of the
        # sender's absolute tick, which is skewed ~tens of cycles vs the receiver and
        # tripped the nMoveCycles error that snapped the plane + stalled the sim.
        relayed = bytearray(pl)
        rt = p.last_telem_tick
        if rt is not None:
            # v234: NEVER re-stamp with a DEAD tick. If we stop recognising a peer's telemetry, their
            # last_telem_tick freezes; re-stamping with it makes every relayed packet look
            # progressively staler to that peer until its client drops the object outright (this is
            # precisely how Test2 vanished from Bigalon's world - Bigalon's tick froze at 13868 for
            # ~3 minutes and nothing said a word). Warn loudly, and leave the sender's own tick in
            # place rather than poisoning the packet with a stale one.
            _age = time.time() - getattr(p, 'last_telem_time', 0.0)
            if _age > STALE_TICK_WARN_S:
                if not getattr(p, '_stale_tick_warned', False):
                    p._stale_tick_warned = True
                    log('STALE-TICK', f'[warn] {p.current_pilot} conductor tick FROZEN at {rt} '
                                      f'({_age:.1f}s old) - not re-stamping. Their telemetry is no '
                                      f'longer being recognised; peers will lose sight of objects.')
            else:
                p._stale_tick_warned = False
                struct.pack_into('<H', relayed, 5, (rt - RELAY_TICK_LEAD) & 0xFFFF)
        seq = getattr(p, '_relay_seq', 0) & 0xFF
        p._relay_seq = seq + 1
        pkt = bytes([0x00, 0x00, 0x20, seq, 0x00, 0x00, 0x00, 0x00]) + bytes(relayed)
        try:
            sock.sendto(pkt, p.addr)
        except OSError:
            pass
    # rate-limited so we can see the relay working without flooding the console
    _now = time.time()
    if _now - getattr(src, '_relay_log_ts', 0.0) >= 1.0:
        src._relay_log_ts = _now
        num = int.from_bytes(pl[7:9], 'little')
        rticks = {p.current_pilot: p.last_telem_tick for p in peers}
        log('RELAY', f'{src.current_pilot} obj=0x{num:04x} srcTick={src.last_telem_tick} '
                     f'-> {len(peers)} peer(s) in room {src.current_room} '
                     f'(re-stamp to peer ticks {rticks})')

def _find_room_by_id(room_id):
    for r in db_get_open_rooms():
        if r[0] == room_id:
            return r
    return None

def push_arena_players_213(s, reason=''):
    """Rebuild + broadcast msg 213 for s's room from the live per-session nation state,
    so the Nations list counts and the per-side roster reflect who picked which side.
    Strictly room-scoped: only players inside this room receive it."""
    room_id = s.current_room
    if room_id is None:
        return
    room = _find_room_by_id(room_id)
    if room is None:
        return
    sessions = get_sessions_in_room(room_id)
    counts = [0] * 8
    roster = []
    for sess in sessions:
        nm = sess.current_pilot or 'Player'
        roster.append((nm, sess.nation))
        if sess.nation is not None and 0 <= sess.nation < 8:
            counts[sess.nation] += 1
    pkt = build_arena_players_213(room, counts=counts, names=roster)
    log('TEAM', f'push 213 room={room_id} counts={counts} roster={roster} {reason}')
    for sess in sessions:
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt,
                         f'<- 213 re-push ({reason})', to=3.0), daemon=True).start()

def handle_team_select(s, nation):
    """Client picked / left a side - msg 68 (0x44) = [0x44][nation:1][?:1]. nation 0..7
    is a side index (US=0, GB=1, SU=2, GE=3, JP=4, NU=...); 0xff / out-of-range = leave.
    Msg 68 itself has NO inbound dispatch handler in FA.exe, so it must NOT be echoed.

    SOLVED (v182 -> v183 -> v185): side membership is driven by msg 63 ChangePlayerCB
    op==1 CHANGE-CAMP (FUN_004fa9c0). v175's msg-58 guess was wrong (msg 58 =
    LobbyRcv list). History of fixes:
      v182 CTD: op was inverted - CAMP shipped as 2, but op==1 is camp and op!=1 is
        the DELETE path; op=2 freed a live player object.
      v183 overcorrection: made the 63 peers-only, citing the `iVar12 != DAT_00bfedb4`
        skip. MISREAD - that skip is in a separate 512-entry in-world object scan;
        the rp lookup (FUN_007fcac0) resolves ANY index including the recipient's
        own, and the op==1 path prints the "<pilot> changed to <nation>" chat line.
        Result: own team change never showed in chat (messages09.log).
      v185/v186: 63 is broadcast to ALL room members INCLUDING the sender. The self
        rp ALWAYS exists by team-select time: the msg 201 grant handler
        (FUN_004f88f0) creates the local player's table entry (camp=-1) at join, so
        the self-63 resolves, sets the camp (chat color), and prints the line. The
        v185 0x66-roster experiment is REVERTED - a 62 self-record deletes that
        live local entry -> use-after-free CTD (messages10.log).
    We still record s.nation for chat/roster scoping and the DB layer."""
    if nation is None or nation == 0xff or nation > 7:
        _changed = s.nation is not None
        s.nation = None
        raw = 0xff if nation is None else nation
        log('TEAM', f'{s.current_pilot} LEFT team (raw=0x{raw:02x}) - msg 63 op=CAMP side=0xff')
        # A camp change is a ROSTER event, not a flight event - broadcast whenever the
        # player is still associated with a room, NOT only while entered_game. Exiting a
        # flight to the team-select/HQ screen runs handle_leave_arena which clears
        # entered_game (but KEEPS current_room), so gating on entered_game silently dropped
        # every team change made AT team-select after the first spawn.
        # DEDUP: only broadcast on an ACTUAL side change. On a desynced re-entered channel
        # the client reliably RE-SENDS the same msg-63 every ~5s (its ACK isn't clearing the
        # send-queue); re-broadcasting each retransmit is a reliable send that further
        # perturbs the channel -> 'Test1 joining/leaving' flood -> the client gives up (~30s)
        # -> 10054. A retransmit of the current side is a no-op (s.nation already matches), so
        # skip the re-broadcast and let the bare ACK land.
        if _changed and s.current_room is not None:
            broadcast_player_change_63(s, None, op=CP_OP_CAMP, reason='(team leave)')
    else:
        _changed = s.nation != nation
        s.nation = nation
        log('TEAM', f'{s.current_pilot} joined side {nation} - msg 63 op=CAMP')
        # Broadcast only on an actual change (see the team-leave branch): the first join
        # after entering broadcasts (s.nation was reset to None at SendEnterToGame), while
        # a reliable retransmit of the same join finds s.nation already set -> no re-send.
        if _changed and s.current_room is not None:
            broadcast_player_change_63(s, nation, op=CP_OP_CAMP, reason='(team join)')

# NOTE (Project A): the v219 _push_career_stats_88 team-change pushes were REVERTED - they were
# no-ops. msg 88 matches the client's score object by score+0x24 == PlayerIndex, and that object is
# only created/linked at msg 201 game-entry (FUN_00441110), NOT at team-select time - so a team-
# change 88 found no match and did nothing (confirmed: v219 'no change'). The real fix is the
# LOGIN/ENTRY-TIME FULL-STAT LOAD (the client allocates its score object with operator new and never
# loads the stat fields -> uninitialised garbage). That load message is being reverse-engineered
# separately (see notes.md Project A). The spawn-time send_ace_rank_88 hook is kept (it does set
# aces/rank once the object exists post-spawn), and the DB career-read plumbing is retained for the
# eventual full-stat load.


def _find_room_by_gidx(game_idx):
    """Resolve an open room by its 32-bit GameIndex (LE int). Matches the per-room
    UNIQUE index [room_id&0xff][ff][ff][creator[0]] first; falls back to the legacy
    creator-only index [00 ff ff creator[0]] (newest match) for a client still holding
    the pre-unique value - e.g. a creator's own room before it re-reads the 0xd2 list,
    which db_get_open_rooms orders newest-first so the creator's just-made room wins."""
    rooms = db_get_open_rooms()
    for r in rooms:
        if int.from_bytes(_arena_gameindex(r[2] or r[1] or 'Arena', r[0]), 'little') == game_idx:
            return r
    for r in rooms:
        if int.from_bytes(_arena_gameindex(r[2] or r[1] or 'Arena', 0), 'little') == game_idx:
            return r
    return None

def handle_gamedef_request(s, game_idx, via=''):
    """FA msg 212 - on-demand GAME_DEF for the selected arena ("out 212'5").
    Without the reply the arena-select dialog never populates: blank briefing /
    combat text, empty nations list, Join disabled. Shared by the direct
    (type=0x52 sub=0xd4) and compound-wrapped paths - the compound variant used to
    fall into the blanket inner_type==0x52 drop, which is exactly the intermittent
    'empty description + disabled Join' bug."""
    room = _find_room_by_gidx(game_idx)
    if room is not None:
        pkt = build_gamedef_212(room)
        if pkt is not None:
            send_rel(s, pkt, f'<- GAME_DEF 212 on-demand{via} (room {room[0]} gidx=0x{game_idx:08x})', to=5.0)
        else:
            log('POST-AUTH', f'212 request{via} gidx=0x{game_idx:08x}: LZ build failed')
    else:
        log('POST-AUTH', f'212 request{via} gidx=0x{game_idx:08x}: no matching open room - silent')

def handle_213_request(s, game_idx, via=''):
    """FA msg 213 - arena player-info request (counts + roster). If the requester's
    own room, build from live per-session nation state; otherwise DB roster."""
    room = _find_room_by_gidx(game_idx)
    if room is None:
        log('POST-AUTH', f'213 request{via} gidx=0x{game_idx:08x}: no matching room - silent')
        return
    sessions = get_sessions_in_room(room[0])
    if sessions:
        counts = [0] * 8
        roster = []
        for sess in sessions:
            roster.append((sess.current_pilot or 'Player', sess.nation))
            if sess.nation is not None and 0 <= sess.nation < 8:
                counts[sess.nation] += 1
    else:
        try:
            roster = [(p, None) for p, _ in db_get_pilots_in_room(room[0])]
        except Exception:
            roster = []
        counts = [0] * 8
    send_rel(s, build_arena_players_213(room, counts=counts, names=roster),
             f'<- ArenaPlayers 213{via} (room {room[0]} gidx=0x{game_idx:08x}, {len(roster)} players)', to=5.0)

# -- START-PLACE ALLOCATION ----------------------------------------------------
# Each airfield has several start positions (parking/runway spots). The Fly request
# (msg 23) carries N=0xff = 'assign me a spot'; the old code always granted N=0, so two
# players on the SAME airfield stacked on the SAME spot. Track occupancy per (room,af)
# and hand out the lowest free index so they spread out. Freed on airfield change
# (alloc frees the previous slot first), on leave (msg 64), and on disconnect.
SP_MAX = 8                       # distinct slots to hand out per airfield before reusing 0
_sp_occupied = {}                # (room_id, af) -> set(occupied start-place indices)
_sp_lock = threading.Lock()

def _free_start_place(s):
    room = s.__dict__.get('sp_room'); af = s.__dict__.get('sp_af'); n = s.__dict__.get('sp_n')
    if room is None or af is None or n is None:
        return
    with _sp_lock:
        occ = _sp_occupied.get((room, af))
        if occ is not None:
            occ.discard(n)
            if not occ:
                _sp_occupied.pop((room, af), None)
    s.__dict__['sp_room'] = None; s.__dict__['sp_af'] = None; s.__dict__['sp_n'] = None

def _alloc_start_place(s, af, n_req):
    """Pick a free start-place index on (room, af). Frees the session's previous slot
    first (airfield change / respawn). N=0xff = assign lowest free; an explicit N is
    honoured. Returns the granted index."""
    _free_start_place(s)
    room = s.current_room
    with _sp_lock:
        occ = _sp_occupied.setdefault((room, af), set())
        if n_req != 0xff:
            n = n_req
        else:
            n = 0
            while n in occ and n < SP_MAX:
                n += 1
            if n >= SP_MAX:           # more than SP_MAX players on one airfield - reuse slot 0
                n = 0
        occ.add(n)
    s.__dict__['sp_room'] = room; s.__dict__['sp_af'] = af; s.__dict__['sp_n'] = n
    return n

def handle_fly_start_place(s, af, mid, n, via=''):
    """FLY: msg 23 (0x17) StartPlaceList. The Fly button sends one 3-byte record
    [AF][mid][N] with N=0xff ("give me a start place on airfield AF"). The inbound
    handler FUN_004f6320 parses 3-byte records, logs "SP N %i on AF %i", and for the
    waiting player (WaitingForStartPlaceList): N=0xff -> start place -1 -> DENY path
    (vtable+0x54) - which is what our old echo did, leaving the client hanging at the
    last gate before the cockpit; valid N -> set position, vtable+8 = SPAWN into the
    world (FUN_004e9fa0). So we grant: reply msg 23 with the same record, N assigned.

    Wire form is built byte-identical to the echo framing that demonstrably arrived
    as `in 23'4` / one record (4-byte appspace header, type 0x42) - msg 23 must not
    gain pad bytes, since pad zeros would parse as bogus [AF=0][N=0] records."""
    old_af  = s.__dict__.get('sp_af')
    grant_n = _alloc_start_place(s, af, n)      # distinct spot per player on this airfield
    af_changed = (old_af is not None and old_af != af)
    # v205: DO NOT rebase NET-time here. v204 called s.tsync_rebase() on every fly-grant, which
    # reset the ms counter to 0 mid-session -> the client saw server time jump BACKWARD by the full
    # session-elapsed (~290-327s in messages60) = the SAME 'CRAP backward NET Time' freeze, just
    # caused by the reset instead of the 262s wrap. The NET-time counter must be strictly monotonic
    # for the life of the connection; see build_beacon/tsync for the real (non-resetting) fix.
    s.obj_confirmed = False; s.flying = False   # new spawn -> re-ServerConfirm on its out 4
    # v210 note: the v208/209 HQ-reentry SYNACK re-anchor was REMOVED - it chased the wrong cause.
    # The freeze was the STALE persisted GAME_DEF CreationTime (fixed at serve time now, see
    # build_lz_gamedef), not a missing base re-anchor. Re-sending a SYNACK mid-flight was an
    # unnecessary perturbation. In-arena vs HQ re-entry no longer needs distinguishing here for time.
    s.entered_game = True                       # re-fly after exit-to-HQ stays IN the arena: re-arm
                                                # the msg-4 spawn gate (handle_leave_arena cleared it),
                                                # else the re-join out-4 is swallowed -> no ServerConfirm
                                                # -> no object created -> players invisible to each other
    s.__dict__.pop('_created_peers', None)      # respawn = new ONumber -> re-create on peers
    # In-world AIRFIELD CHANGE: the client rebuilds its world and DelObject's the peers'
    # planes too (the 'Get coord for missing object N' flood) - so each peer must re-
    # advertise its object to us. Drop our addr from every peer's object-created set; the
    # relay then re-creates their object on us OBJECT-ONLY (the NET::CLIENT station
    # persists, so no 'Client already exist' CTD). Same recovery the exit-to-HQ delete
    # path does via clear_peer_created. In-place respawn keeps the same airfield -> no
    # clear -> no duplicate-create.
    if af_changed:
        for _p in get_sessions_in_room(s.current_room):
            if _p is not s:
                _pcp = _p.__dict__.get('_created_peers')
                if _pcp is not None:
                    _pcp.discard(s.addr)
        log('FLY23', f'airfield change ({old_af}->{af}) -> peers re-create objects on {s.current_pilot}')
    if s.__dict__.pop('_rejoin_pending', False):     # re-join only (first join did this at enter)
        # Re-announce US to PEERS - they removed us via msg-63 REMOVE on our exit, so this is
        # a clean re-add (fixes the phantom/garbage scoreboard row).
        broadcast_player_join_62(s, reason='(re-fly)')
        # AND re-push the PEER roster back to US - but ONLY for peers we don't currently hold.
        # Original code skipped this on the assumption "exit-to-HQ keeps our OWN roster intact",
        # which is FALSE when a PEER also exited to HQ: their object was deleted in our world
        # (Server require delete object N), so on our re-entry we have no REMOTE_PLAYER for them,
        # the world-build waits for a peer that never arrives, and BOTH clients hang at 33%
        # loading (messages40: after both exit-to-HQ + a team change, neither got AddPlayer 62
        # and neither spawned). The old use-after-free warning (messages97) was about re-adding
        # a LIVE remote player; we now guard on _created_peers so we only re-advertise peers
        # whose object we actually dropped - a clean re-create, never a duplicate of a live one.
        _cp = s.__dict__.setdefault('_created_peers', set())
        _missing = [p for p in get_sessions_in_room(s.current_room)
                    if p is not s and p.addr not in _cp]
        if _missing:
            records = [(p.player_index, p.nation, p.current_pilot or 'Player') for p in _missing]
            _pkt = build_msg13(build_add_player_62(records))
            send_rel(s, _pkt, f'<- AddPlayer 62 ({len(records)} peer(s)) (re-fly roster rebuild)', to=5.0)
            log('PLAYER62', f're-fly: re-advertised {len(records)} missing peer(s) to '
                            f'{s.current_pilot}: {[p.current_pilot for p in _missing]}')
    pkt = bytes([0x00, 0x42, 0x00, 0x00, 0x17, af & 0xFF, mid & 0xFF, grant_n & 0xFF])
    log('FLY23', f'StartPlace request{via} AF={af} mid={mid} N=0x{n:02x} -> GRANT N={grant_n}')
    threading.Thread(target=lambda: send_reply(s, pkt,
                     f'<- StartPlaceList 23 GRANT (AF={af} N={grant_n})', to=5.0),
                     daemon=True).start()

def handle_leave_arena(s):
    """Client pressed 'back to lobby' - msg 64 (0x40). Msg 64 has NO inbound dispatch
    handler -> must NOT be echoed (echo -> "Unknown Type 64").

    SOLVED (v178) - what the client waits for after the back button:
    The back button fires a UI callback -> FUN_004edf0e -> FUN_004f1b10: full game-globals
    reset + re-arm of the SAME 1-Hz 0x43 connect-poll used at game entry. Data-xrefs on
    the poll timer DAT_00c82eb0 show exactly three poll-stoppers: the 201 join grant
    (FUN_004f88f0), and FUN_004edcf0 - the handler for lobby msg 218 (0xDA), the
    "lobby attach answer" (dispatch slot 0xc82240 -> id (0xc82240-0xc81ed8)/4 = 218).
    FUN_004edcf0 stores session dwords + MyRights (logs "**** MyRights=%i ****"), sets
    DAT_00c82eb0 = 0 (poll STOP) and notifies the lobby UI observers. It's the same
    218'17 every session receives right after login (our reply to 0xde).

    So leaving = re-entering the lobby state machine: clear the in-game state and
    RE-SEND the 0xDA lobby attach answer; the client stops polling and the lobby UI
    takes over (it will then re-request news/arena list itself)."""
    log('LEAVE', f'{s.current_pilot} pressed back-to-lobby (msg 64) - leaving game '
                 f'(room {s.current_room}), clearing in-game state, NOT echoed')
    # v182: tell peers to drop this player's REMOTE_PLAYER object (msg 63 op=REMOVE)
    # BEFORE we clear s.entered_game / s.current_room, so the broadcast still scopes
    # to the room and resolves the player_index. op=0 (CP_OP_REMOVE) -> FUN_004fa9c0
    # remove path (iVar12==0).
    if s.entered_game and s.current_room is not None:
        room_id = s.current_room
        # v191: ORDER MATTERS - the NetPlane holds a pointer to the REMOTE_PLAYER, so the
        # plane (type-3 DELETE) must reach a peer BEFORE the player (msg-63 REMOVE), else a
        # FLYING peer use-after-frees the dangling plane (messages03: a flying Test2 died on
        # 'Test1 leaving game' with no DelObject after it). broadcast_object_delete_3 now
        # sends DELETE then this REMOVE on the same thread (DELETE gets the lower seq). If we
        # never spawned a NetPlane, there's nothing to dangle - just send the REMOVE.
        rem_pkt = build_change_player_63([(s.player_index, s.nation, CP_OP_REMOVE)])
        rem_label = f'<- ChangePlayer 63 REMOVE ({s.current_pilot})'
        if s.my_obj_number is not None:
            broadcast_object_delete_3(s, reason='(back to lobby)',
                                      followup_pkt=rem_pkt, followup_label=rem_label)
            free_obj_number(s.my_obj_number)   # recycle the Number on exit-to-HQ too
        else:
            for sess in get_sessions_in_room(room_id):
                if sess is s:
                    continue
                threading.Thread(target=lambda _s=sess: send_rel(_s, rem_pkt, rem_label, to=3.0),
                                 daemon=True).start()
    s.entered_game = False
    # v260: ARENA ISOLATION - clear current_room on leave so a subsequent arena JOIN resolves the
    # new arena fresh. Previously current_room kept pointing at the OLD room, and the enter handler
    # only resolved a room 'if not s.current_room', so an arena SWITCH left current_room stale ->
    # chat/telemetry/roster kept scoping to the old room -> cross-arena leakage (peers in different
    # arenas saw each other's chat, roster and 3D planes). The leave broadcast above already ran
    # while current_room was still valid, so it's safe to clear now.
    s.current_room = None
    s.room_slot = None
    # v225: this is the exit-to-HQ / back-to-lobby leave. If a solo plane-destroy was credited a
    # few seconds ago and is still sitting on its deferred timer, THAT removal was this exit - not
    # a crash - so cancel the death. (A genuine crash respawns instead of leaving, so its timer
    # fires normally.) Without this, bailing out of the arena counted as a death: one crash logged
    # three deaths in run 004058.
    _cancel_pending_death(s, '(left arena -> exit-to-HQ, not a crash)')
    # ARENA-CHANGE CTD (messages39): the leaving client runs 'del CLIENT Me 0' + 'del
    # CLIENT <n>' for EVERY peer - it destroys its whole world, including all peer
    # NET::CLIENT stations. So on re-entry every peer must be re-created client+object,
    # not object-only. Forget both our object-tracking AND station-tracking for all peers
    # (the reverse direction - peers forgetting US - is handled in broadcast_object_delete_3's
    # clear_peer_created block). Without this, our re-entry sends object-only creates whose
    # owner St points at a station the peer deleted -> o->Client()==0 -> CTD Network.cpp:440.
    s.__dict__.pop('_created_peers', None)
    s.__dict__.pop('_client_created_peers', None)
    _free_start_place(s)       # release the airfield start-place slot we held
    s._rejoin_pending = True   # exit-to-HQ tore down our roster + told peers msg-63 REMOVE; the next
                               # StartPlace must re-exchange msg-62 both ways, else the re-join
                               # camp-change (msg-63) hits a player nobody re-added -> phantom
                               # scoreboard row with garbage score (messages92: 'Unknown RemotePlayer(1)')
    s.client_granted = False   # allow a fresh 201 grant on re-entry
    # v189: KEEP s.nation across exit-to-HQ - the player re-flies under the SAME side
    # without re-sending a camp-change, so clearing it made broadcast_player_join_62 re-add
    # them as camp 0 = US (messages97: 'GBR Test2 leaving' -> 'USA Test2 entering').
    # Clear DB room membership too, or the pilot lingers in db_get_pilots_in_room
    # forever (the stale "Test2 in room 39" roster seen across restarts).
    if s.current_pilot:
        try:
            db_room_leave(s.current_pilot)
        except Exception as e:
            log('LEAVE', f'db_room_leave failed: {e}')
    # The poll stopper: 218 (0xDA) lobby attach answer (FUN_004edcf0 -> DAT_00c82eb0=0)
    if SEND_EXIT_UNRELIABLE:
        # UNRELIABLE so the exit consumes no reliable seq. If lost, the client keeps polling
        # 0x43 and we resend it there (resend-on-poll). entered_game is now False, so the
        # resend/echo gates below are armed until the player re-enters a game.
        s._awaiting_reattach = True
        send_unrel(s, build_da_session_safe(),
                   '<- 0xDA lobby re-attach (UNREL, resend-on-0x43-poll) - stops post-leave poll')
    else:
        threading.Thread(target=lambda: send_rel(s, build_da_session_safe(),
                         '<- 0xDA lobby re-attach (218, Size=15 63-safe) - stops post-leave 0x43 poll',
                         to=5.0), daemon=True).start()

# --- Lobby broadcasts ---------------------------------------------------------

def broadcast_system(message, exclude_sess=None):
    bcast = build_chat_broadcast('Server', message)
    for sess in get_all_sessions():
        if sess is exclude_sess: continue
        threading.Thread(target=lambda _s=sess: send_rel(_s, bcast, '<- sys msg', to=3.0),
                         daemon=True).start()

def build_room_echo_pkt(db_id):
    """Build the type=0x92 sub=0xdc room creation echo for a room in the DB.
    Returns the packet bytes, or None if the room is missing/invalid."""
    try:
        _c = sqlite3.connect(DB_PATH)
        row = _c.execute(
            "SELECT game_def_raw, room_slot, creator_pilot FROM rooms WHERE room_id=? AND status='open'",
            (db_id,)).fetchone()
        _c.close()
        if not row or not row[0]:
            return None
        gdef = bytes(row[0])[:740].ljust(740, b'\x00')
        slot = row[1] or 0x23
        cname = (row[2] or '').encode('ascii', 'replace')[:23] + b'\x00'
        cname = cname.ljust(24, b'\x00')
        # inner data after sub=0xdc: [slot][room_id&0xff][0xff][0xff][creator(24B)][GAME_DEF]
        # GameIndex = bytes[2:6] of [0xdc]+inner_data = [room_id&0xff][0xff][0xff][creator[0]]
        # LE. The low byte (was a fixed 0x00) now carries room_id so two rooms whose
        # creators share a first letter no longer collide - matches _arena_gameindex(
        # creator, db_id) used by the 0xd2 list / 212 / join resolution.
        inner_data = bytes([slot, db_id & 0xff, 0xff, 0xff]) + cname + gdef
        return build_typed_pkt(0x92, bytes([0xdc]) + inner_data)
    except Exception as e:
        log('ROOM-ECHO', f'build failed db_id={db_id}: {e}')
        return None

def send_room_echo(sess, db_id, label=None):
    """Send the 0xdc room creation echo for db_id to a specific session."""
    pkt = build_room_echo_pkt(db_id)
    if pkt is None: return False
    lbl = label or f'<- room echo db_id={db_id}'
    threading.Thread(target=lambda: send_rel(sess, pkt, lbl, to=5.0), daemon=True).start()
    return True

def send_all_room_echoes(sess):
    """Send 0xdc echoes for every open room in the DB to a session.
    Called when a client enters the lobby so its arena list populates."""
    rooms = db_get_open_rooms()
    if not rooms:
        log('ROOM-ECHO', f'no open rooms to advertise to session')
        return
    own_id = sess.current_room
    log('ROOM-ECHO', f'advertising {len(rooms)} room(s) to session (own={own_id})')
    for r in rooms:
        db_id, _name, creator, _acct, _t, slot, _gd = r
        tag = ' [OWN]' if db_id == own_id else ''
        send_room_echo(sess, db_id, label=f'<- room echo db_id={db_id} creator="{creator}"{tag}')

def broadcast_room_creation(db_id, exclude_sess=None):
    """Send the 0xdc echo for a newly-created room to every other authenticated
    session, so their arena lists show the new room."""
    pkt = build_room_echo_pkt(db_id)
    if pkt is None:
        log('ROOM-ECHO', f'broadcast skipped (no pkt) db_id={db_id}')
        return
    n = 0
    for sess in get_all_sessions():
        if sess is exclude_sess: continue
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt, f'<- broadcast new room db_id={db_id}', to=3.0),
                         daemon=True).start()
        n += 1
    log('ROOM-ECHO', f'broadcast room db_id={db_id} -> {n} other session(s)')

def send_active_list(target_sess):
    others = [s.current_pilot for s in get_all_sessions()
              if s.current_pilot and s is not target_sess]
    msg = ('In lobby: ' + ', '.join(others)) if others else 'No other pilots currently in lobby'
    threading.Thread(target=lambda: send_rel(target_sess, build_chat_broadcast('Server', msg),
                                              '<- active list', to=3.0), daemon=True).start()

def broadcast_player_join(pilot_name, exclude_sess=None):
    pkt = build_ui_player_update(pilot_name, is_join=True)
    for sess in get_all_sessions():
        if sess is exclude_sess: continue
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt, f'<- UI ADD [{pilot_name}]', to=3.0),
                         daemon=True).start()

def broadcast_player_leave(pilot_name, exclude_sess=None):
    pkt = build_ui_player_update(pilot_name, is_join=False)
    for sess in get_all_sessions():
        if sess is exclude_sess: continue
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt, f'<- UI REMOVE [{pilot_name}]', to=3.0),
                         daemon=True).start()

def send_initial_ui_list(target_sess):
    for sess in get_all_sessions():
        if sess is not target_sess and sess.current_pilot:
            pkt = build_ui_player_update(sess.current_pilot, is_join=True)
            time.sleep(0.05)
            send_rel(target_sess, pkt, f'<- UI INIT ADD [{sess.current_pilot}]', to=3.0)

# --- Connection handler -------------------------------------------------------

def _reap_stale_sessions(acct, new_sess):
    """Reap any prior session bound to the SAME account (a reconnect after a CTD/timeout).
    On Windows the dead client is never detected on sendto (the failure surfaces as a 10054 on
    recvfrom), so without this the old session's heartbeat thread + lobby-roster entry linger
    as a ghost across reconnects. One account == one live connection here, so any OTHER session
    on this account is stale. new_sess is not yet registered in sids at call time, so it is
    never itself reaped; clean each stale one exactly like a graceful leave so the reconnecting
    client starts fresh (no duplicate pilot in the roster, no orphaned start-place / room row)."""
    with sl:
        stale = [x for x in list(sids.values())
                 if x.account == acct and x is not new_sess and not x.closing]
    for x in stale:
        x.closing = True   # stops its heartbeat/relay loops (they gate on not s.closing)
        try:
            if x.current_pilot:
                broadcast_player_leave(x.current_pilot, exclude_sess=x)
                broadcast_system(f'[{x.current_pilot}] has left')
                db_room_leave(x.current_pilot)
            _free_start_place(x)
            free_client_number(x)   # return the global ClientNumber to the pool
        except Exception as _e:
            log('REAP', f'cleanup error: {_e}')
        with sl:
            sadrs.pop(x.addr, None); sids.pop(x.sid, None)
        log('REAP', f'reaped stale session for account="{acct}" (reconnect) - ghost cleared')

def handle_syn(data, addr):
    acct_row = identify_account_from_syn(data)
    cid=data[1:5]; s=S(cid,addr)
    if acct_row:
        acct, pid_hex, f45_hex, ab_hex = acct_row
        s.account=acct; s.auth64=build_auth64(pid_hex, f45_hex, ab_hex, acct)
        _reap_stale_sessions(acct, s)
        s.auth_payload=build_auth_response(s.auth64)
        pilots=db_get_pilots(acct)
        with sl: active = len([x for x in sids.values() if x.auth_done and not x.closing])
        log('SYN',f'Ready: account="{acct}" {len(pilots)} pilot(s) [sid={s.sid}, active_sessions={active}]')
    else: log('SYN','WARNING: unknown account')
    with sl: sids[s.sid]=s; sadrs[addr]=s
    time.sleep(0.015)
    _now = time.time(); s._ntp_epoch = _now; s._ntp_last_reanchor = _now  # v211: base<->epoch same instant
    synack,fa_s,fa_frac=build_synack(); s.synack_base=(fa_s,fa_frac)   # v209: keep for HQ re-anchor
    sock.sendto(synack,addr); log('TX/SYNACK',f'FA_s=0x{fa_s:08X}')
    time.sleep(0.025)
    sock.sendto(build_beacon(s.nts(),0,sess=s),addr); log('TX/BEACON','idx=0')
    def sp():
        time.sleep(0.05)
        if not s.closing: sock.sendto(build_data(100,s.nsq()),s.addr); log('TX/SYS','cmd=100')
    threading.Thread(target=sp,daemon=True).start()

def login(s):
    log('LOGIN','== v197 AUTH ==')
    if not s.auth_payload: log('LOGIN','No auth payload'); return
    if not send_rel(s,s.auth_payload,'<- cmd=100 auth',to=8.0): return
    log('LOGIN',f'Auth ACKed T+{s.ela():.3f}s')
    s.auth_done=True
    def _hb():
        errors = 0
        _hb_n = 0
        while not s.closing and not s.in_game:
            time.sleep(HEARTBEAT_INTERVAL)
            if not s.closing:
                try:
                    if s.entered_game:
                        # IN-GAME KEEPALIVE. Once in the world the client stops sending
                        # 12-byte time pings and only streams unreliable out 6, so the
                        # server must drive the link itself. The 4-byte 0xd3 NOP does NOT
                        # reset the VCNC 60s connection-alive timer (messages35: the client
                        # received 11x 0xd3 over 60s and still hit FATALLOSTCONNECTION at
                        # exactly 60s after the last reliable packet = the ServerConfirm).
                        # A type-2 0x80 TIME beacon DOES reset it - early lobby survived a
                        # ~19s no-reliable gap on TIME packets alone.
                        # v206: this beacon is ALSO the client's NET-time offset source. The
                        # client holds NET time = own_clock + server_offset and needs a STEADY
                        # beacon stream to keep the offset locked; the beacon A field (18-bit ms,
                        # wraps ~262s) is a small correction, so gaps longer than the wrap make
                        # the correction ambiguous and a respawn re-fit can snap the offset
                        # backward by ~session-elapsed (the 'CRAP backward NET Time' freeze;
                        # run_230020 logged only 2 beacons the whole session -> froze on the 4th
                        # re-fly). Beat at HEARTBEAT_INTERVAL (1s) so the client re-anchors well
                        # inside the wrap window. Logged 1-in-5 to prove cadence without flooding.
                        # v212: RE-ANCHOR DISABLED. v211's periodic SYNACK re-anchor did NOT update
                        # the client's base mid-session (set-base only runs on the connect config
                        # path), so resetting A->0 while the base stayed fixed made server_time drop
                        # by ~elapsed -> a ~100-180s slew that froze mid-slew (run_192643: froze ~57s
                        # after the 180s re-anchor). v211's CORE fix stands (offset 245.8s -> 0.75s,
                        # client now Slews instead of hard-failing). Leaving the base un-reset: A =
                        # elapsed-since-connect climbs monotonically; if it ever nears the 262s wrap
                        # we handle it separately. Gate kept but effectively off (NTP_REANCHOR_S huge).
                        if NTP_REANCHOR_S < 100000 and (time.time() - s._ntp_last_reanchor) >= NTP_REANCHOR_S:
                            _rt = time.time(); s._ntp_epoch = _rt; s._ntp_last_reanchor = _rt
                            _ra_synack, _ra_s, _ra_frac = build_synack()
                            sock.sendto(_ra_synack, s.addr)
                            log('TX/REANCHOR', f'NET-time base re-anchored FA_s=0x{_ra_s:08X} '
                                               f'(epoch reset, A->0) ({s.current_pilot})')
                        # v213: in-game one-way TIME beacons are OFF by default (IN_GAME_BEACON=False).
                        # See the flag's comment: the beacon is what wraps at 262s and it SUPPRESSES
                        # the client's self-healing resync. With it off, the client resyncs via two-way
                        # ping (we answer those in on_pkt) and re-baselines cleanly - no wrap, real lag.
                        if IN_GAME_BEACON:
                            _bseq = s.nts()
                            sock.sendto(build_beacon(_bseq, 0, sess=s), s.addr)
                            _hb_n += 1
                            if (_hb_n % 5) == 1:
                                log('TX/BEACON', f'in-game seq={_bseq} A_ms={tsync_ms(s)} '
                                                 f'({s.current_pilot} n={_hb_n})')
                        else:
                            # v213: no beacon -> send a lightweight keepalive every KEEPALIVE_S to
                            # reset the client's 60s connection-alive timer WITHOUT feeding the time
                            # base or suppressing resync (build_keepalive: sentinel time-index).
                            _now_hb = time.time()
                            if (_now_hb - getattr(s, '_last_keepalive', 0.0)) >= KEEPALIVE_S:
                                s._last_keepalive = _now_hb
                                sock.sendto(build_keepalive(sess=s), s.addr)
                                _hb_n += 1
                                log('TX/KEEPALIVE', f'in-game (no-beacon, resync mode) '
                                                   f'({s.current_pilot} n={_hb_n})')
                        # v215: STATUS request - the real in-game time keeper. Send every
                        # STATUS_INTERVAL_S with base-increment = elapsed ms since the last STATUS.
                        # The client ADDs this to its NET base (FUN_10007d13) -> the base ADVANCES
                        # in-game, tracking real time, so the 18-bit A field's 262s wrap no longer
                        # matters. Also drives the System Status window (loss%, latency, SESSION
                        # TIME). Success signal: client logs 'New server base time' and the session
                        # timer starts counting up (was stuck at 0:00).
                        if STATUS_PACKETS:
                            _now_st = time.time()
                            if s._status_base_epoch is None:
                                s._status_base_epoch = _now_st
                                s._status_last = _now_st
                            if (_now_st - s._status_last) >= STATUS_INTERVAL_S:
                                _incr_ms = int((_now_st - s._status_last) * 1000)
                                s._status_last = _now_st
                                s._status_seq = (s._status_seq + 1) & 0x1FF
                                try:
                                    sock.sendto(build_status_request(s, _incr_ms), s.addr)
                                    _hb_n += 1
                                    if (s._status_seq % 8) == 1:
                                        log('TX/STATUS', f'in-game seq={s._status_seq} '
                                                        f'base_incr={_incr_ms}ms '
                                                        f'connid=0x{(s._status_connid or 0x0240):04x} '
                                                        f'({s.current_pilot})')
                                except OSError:
                                    pass
                    else:
                        sock.sendto(bytes([0,0,0,0xd3]), s.addr)   # lobby heartbeat
                    errors = 0
                except OSError:
                    errors += 1
                    if errors >= 3:   # 3 consecutive failures -> client gone
                        log('SESSION', 'Heartbeat failed 3x - closing session')
                        s.closing = True
                        with sl: sadrs.pop(s.addr,None); sids.pop(s.sid,None)
                        break
    threading.Thread(target=_hb,daemon=True).start()
    deadline=time.time()+300.0   # (kept for reference - no longer bounds the loop, v199)
    while not s.closing:
        cmds=[]
        with s._lock: cmds=list(s.post_auth_cmds); s.post_auth_cmds.clear()
        for cmd,pl in cmds: handle_post_auth(s,cmd,pl)
        time.sleep(0.02)

def parse_e4_selection(pl):
    if len(pl) <= 10: return None, None
    sb = pl[10]
    if sb < 0x20:
        name = pl[11:].split(b'\x00')[0].decode('ascii', errors='replace')
        return name, sb
    else:
        name = pl[10:].split(b'\x00')[0].decode('ascii', errors='replace')
        return name, None

def _handle_chat_pl(s, pl):
    sub = pl[4] if len(pl) > 4 else 0
    if sub == 0xcd:
        raw   = pl[5:] if len(pl) > 5 else b''
        parts = raw.split(b'\x00')
        name  = parts[0].decode('ascii', 'replace')
        msg   = parts[1].decode('ascii', 'replace') if len(parts) > 1 else ''
        sender = s.current_pilot or name
    else:
        slot_char = pl[9]  if len(pl) > 9  else 0
        parts     = pl[10:].split(b'\x00') if len(pl) > 10 else [b'', b'']
        rest      = parts[0].decode('ascii', 'replace')
        msg       = parts[1].decode('ascii', 'replace') if len(parts) > 1 else ''
        reconstructed = (chr(slot_char) + rest) if 0x20 <= slot_char <= 0x7e else rest
        sender = s.current_pilot or reconstructed
    log('CHAT', f'[{sender}]: {msg!r}')
    bcast = build_chat_broadcast(sender, msg)
    sessions = get_all_sessions()
    log('CHAT', f'Broadcasting to {len(sessions)} session(s)')
    for sess in sessions:
        threading.Thread(target=lambda _s=sess: send_rel(_s, bcast, f'<- chat [{sender}]', to=3.0),
                         daemon=True).start()

COMPOUND_CMDS = {530, 578, 4610}

def handle_compound(s, outer_cmd, pl):
    if len(pl) < 5: log('COMPOUND', f'cmd={outer_cmd} too short'); return
    inner = bytes(pl[4:])
    if len(inner) < 5: log('COMPOUND', f'cmd={outer_cmd} inner too short'); return

    inner_type = inner[1]; inner_cmd = (inner[2] << 8) | inner[3]; inner_sub = inner[4]
    log('COMPOUND', f'cmd={outer_cmd}(0x{outer_cmd:04x}) inner '
        f'type=0x{inner_type:02x} cmd={inner_cmd} sub=0x{inner_sub:02x}')

    if inner_type == 0x22 and inner_sub == 0xe2:
        name_raw = inner[6:] if len(inner) > 6 else b''
        new_name = name_raw.split(b'\x00')[0].decode('ascii', 'replace')
        if new_name and s.account:
            slot = db_next_slot(s.account); db_ensure_pilot(new_name, s.account, slot)
            log('COMPOUND', f'Created "{new_name}" slot={slot}')
        threading.Thread(target=lambda: send_rel(s, inner, '<- compound create echo', to=5.0), daemon=True).start()
        return

    if inner_type == 0x42 and inner_sub == 0xe7:
        old_raw  = inner[8:40]  if len(inner) >= 40 else inner[8:]
        new_raw  = inner[40:72] if len(inner) >= 72 else b''
        old_name = old_raw.split(b'\x00')[0].decode('ascii', 'replace')
        new_name = new_raw.split(b'\x00')[0].decode('ascii', 'replace')
        if old_name and new_name and s.account:
            db_rename_pilot(old_name, new_name, s.account)
            log('COMPOUND', f'Renamed "{old_name}" -> "{new_name}"')
        threading.Thread(target=lambda: send_rel(s, inner, '<- compound rename echo', to=5.0), daemon=True).start()
        return

    if inner_type == 0x42 and inner_sub == 0xe3:
        name_raw = inner[8:] if len(inner) > 8 else b''
        pname    = name_raw.split(b'\x00')[0].decode('ascii', 'replace')
        if pname and s.account: db_delete_pilot(pname, s.account)
        data = bytearray(33); data[0]=0xe3; data[1]=0x00; data[2]=0x00; data[3]=0x00
        nb = (pname.encode() + b'\x00') if pname else b'\x00'
        data[4:4+min(len(nb),29)] = nb[:29]
        resp = build_typed_pkt(0x42, bytes(data), bc=2)
        threading.Thread(target=lambda: send_rel(s, resp, '<- compound delete success', to=5.0), daemon=True).start()
        return

    if inner_type == 0x40 and inner_cmd == 5:
        log('COMPOUND', 'inner vcncExitAppSpace -> exit reply')
        pl2=bytearray(80); pl2[0]=4; pl2[3]=0x64
        if not send_rel(s, bytes(pl2), 'exit appspace reply'):
            s.closing = True
            with sl: sadrs.pop(s.addr,None); sids.pop(s.sid,None)
        return

    if inner_cmd == 2:
        log('COMPOUND', 'inner vcncDisconnect -> disconnect reply')
        pl2=bytearray(80); pl2[0]=4; pl2[3]=0x64
        send_rel(s, bytes(pl2), 'disconnect reply')
        return

    if inner_type == 0x12 and inner_sub == 0xe1:
        pilots = db_get_pilots(s.account) if s.account else []
        resp = build_e1_pilot_list(pilots)
        threading.Thread(target=lambda: send_rel(s, resp, '<- compound pilot list', to=5.0), daemon=True).start()
        return

    if inner_type == 0x62 and inner_sub == 0xe4:
        pname, exslot = parse_e4_selection(inner)
        if pname:
            slot = exslot or db_get_pilot_slot(s.account, pname) or 0
            s.current_pilot = pname; s.current_slot = slot
            log('COMPOUND', f'Pilot selected: "{pname}" slot={slot}')
        threading.Thread(target=lambda: send_rel(s, inner, '<- compound pilot select echo', to=5.0), daemon=True).start()
        return

    if inner_sub == 0xcd or (len(inner) > 8 and inner[8] == 0xcd):
        log('COMPOUND', 'inner chat -> _handle_chat_pl')
        _handle_chat_pl(s, inner)
        return

    # -- IN-ARENA CHAT, compound-wrapped (inner sub=0x14) ----------------------
    # Same msg-20 chat as the direct path, but inside a compound (cmd in
    # COMPOUND_CMDS). inner = pl[4:], so inner[4]=sub=0x14, inner[5]=channel,
    # inner[6:]=text. Reflect with PlayerIndex=0 -> renders as the local pilot.
    if inner_sub == 0x14:
        channel = inner[5] if len(inner) > 5 else 0
        text    = bytes(inner[6:]) if len(inner) > 6 else b''
        log('COMPOUND', f'inner sub=0x14 chat -> reflect ch={channel}')
        reflect_chat_20(s, channel, text)
        return

    # -- TEAM / SIDE SELECT, compound-wrapped (inner sub=0x44) -----------------
    # This is how FA actually sends it in the arena lobby (cmd=530). inner[5]=nation.
    if inner_sub == 0x44:
        nation = inner[5] if len(inner) > 5 else 0xff
        log('COMPOUND', f'inner sub=0x44 team-select -> nation=0x{nation:02x}')
        handle_team_select(s, nation)
        return

    # -- LEAVE ARENA / BACK TO LOBBY, compound-wrapped (inner sub=0x40) ---------
    # msg 64 = the back button. No inbound handler -> must NOT be echoed.
    if inner_sub == 0x40:
        log('COMPOUND', 'inner sub=0x40 -> leave-arena (back to lobby), NOT echoed')
        handle_leave_arena(s)
        return

    # -- FLY / START PLACE, compound-wrapped (inner sub=0x17) -------------------
    # [0x17][AF][mid][N]; reply the grant, never echo (echo = deny).
    if inner_sub == 0x17 and len(inner) >= 8:
        handle_fly_start_place(s, inner[5], inner[6], inner[7], via=' (compound)')
        return

    # -- ROOM CREATION (inner type=0x92 sub=0xdc) ------------------------------
    # Always arrives via compound cmd=18.
    # inner layout (from inner[4:] = data):
    #   data[0]=0xdc (sub), data[1]=room_slot (e.g. 0x23), data[2:5]=flags (0x00 0xff 0xff)
    #   data[5:29] = creator pilot name (24-byte null-padded)
    #   data[29:769] = GAME_DEF (740 bytes, confirmed by FA.exe "GAME_DEF size 740")
    # Echo inner -> FA.exe gets "in 220'777" which shows the room locally.
    # Player count starts at 0 - creator enters via VNET::SendEnterToGame (type=0x1d).
    if inner_sub == 0xdc and len(inner) > 33:  # inner_type varies per session (0x92 or 0xa2)
        data      = inner[4:]
        room_slot = data[1] if len(data) > 1 else 0
        creator_raw = data[5:29].split(b'\x00')[0].decode('ascii', 'replace') if len(data) > 5 else ''
        creator   = s.current_pilot or creator_raw
        # Store the FULL GAME_DEF - the old data[29:769] cap truncated it to 740 and the
        # deserialiser ran off the end (Mix.hpp:539). data[29:] = the whole GAME_DEF the
        # client serialised (the inner's appspace data, minus the 29-byte room header).
        game_def  = bytes(data[29:])
        room_id   = db_create_room(creator, s.account or '', game_def, room_slot)
        # One-room-per-creator enforcement (CLOSE the pilot's other open rooms) - now gated
        # behind PERSIST_ROOMS. With unique per-room GameIndexes a creator can hold several
        # rooms at once, and the original 0xce>bc48 worry is moot (0xce is empty). This SQL
        # was silently closing an earlier same-creator room (FFA when TC was made next).
        if creator and not PERSIST_ROOMS:
            _c = sqlite3.connect(DB_PATH)
            _c.execute("UPDATE rooms SET status='closed' WHERE creator_pilot=? AND status='open' AND room_id!=?",
                       (creator, room_id))
            _c.commit(); _c.close()
        s.current_room = room_id
        s.room_slot    = room_slot
        s._await_create_entry = True   # creator drives entry off the 0x43 poll (no 0xc8); grant 201 on it
        if creator:
            db_room_join(room_id, creator, s.account or '')
        log('COMPOUND', f'ROOM CREATED db_id={room_id} slot=0x{room_slot:02x} '
            f'creator="{creator}" name="{extract_name_from_gamedef(game_def)}" '
            f'inner={len(inner)}b data={len(data)}b GAME_DEF={len(game_def)}b '
            f'ver=0x{(bytes(game_def)[gamedef_start(game_def)] if game_def else 0):02x} '
            f'terrain={extract_terrain_from_gamedef(game_def)} '
            f'({TERRAIN_NAMES.get(extract_terrain_from_gamedef(game_def), "?")}) players=1')
        # Exclude creator: chat arriving before the echo disrupts FA.exe state machine
        broadcast_system(f'[{creator}] created a room', exclude_sess=s)
        threading.Thread(target=lambda: send_rel(s, inner, '<- compound echo room create', to=5.0), daemon=True).start()
        # Broadcast new room to all OTHER sessions so their arena lists update
        threading.Thread(target=lambda: broadcast_room_creation(room_id, exclude_sess=s), daemon=True).start()
        return

    # -- ARENA LIST REQUEST (inner sub=0xd2) ----------------------------------
    # 0xd2 = the Arenas-tab room list (real log: out 210 -> in 210'1110). FA.exe
    # often wraps it in a compound. Respond with open rooms, not an echo.
    if inner_sub == 0xd2:
        active_rooms = db_get_open_rooms()
        log('COMPOUND', f'inner sub=0xd2 -> ArenaList ({len(active_rooms)} rooms)')
        # v164: push GAME_DEF (212) per room first so terrain is cached, then the list.
        threading.Thread(
            target=lambda: send_arenalist_with_gamedefs(
                s, active_rooms, '<- compound ArenaList 0xd2'),
            daemon=True).start()
        return

    # -- ROOM CONFIRM POLL (inner sub=0x43) ------------------------------------
    # When room creation goes via compound cmd=18, FA.exe ALSO wraps ALL 0x43 polls
    # in compound (cmd=12434 or cmd=37424). It never sends a direct sub=0x43 in that
    # case, so we MUST respond here with the same 17-byte room status packet.
    # Apply the same 0.5s rate limit as the direct APPSPACE handler.
    if inner_sub == 0x43:
        now = time.time()
        if now - s.last_43_ts < 0.5:
            log('COMPOUND', 'inner sub=0x43 -> rate-limited')
            return
        s.last_43_ts = now
        _maybe_grant_create_entry(s)   # creator's post-create 0x43 poll -> 201 GRANT (enters game)
        if SEND_EXIT_UNRELIABLE and getattr(s,'_awaiting_reattach',False) and not s.entered_game:
            send_unrel(s, build_da_session_safe(), '<- 0xDA re-attach RESEND (compound 0x43 poll)')
        room_slot = getattr(s, 'room_slot', 0)
        rooms = db_get_open_rooms()
        if rooms and (s.current_room or room_slot):
            rid    = s.current_room or rooms[0][0]
            pcount = db_room_player_count(rid)
            slot   = room_slot or (rid & 0xFF)
            resp_data = bytes([0x43, slot, 0x00, 0x00, 0x00, pcount, 0x01,
                               0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            mode = 'GAME' if s.entered_game else 'lobby'
            log('COMPOUND', f'inner sub=0x43 -> {mode} confirm slot=0x{slot:02x} db_id={rid} players={pcount}')
            resp = build_appspace_pkt(resp_data)
            threading.Thread(target=lambda: send_rel(s, resp, f'<- compound 0x43 {mode} confirm', to=3.0),
                             daemon=True).start()
        else:
            log('COMPOUND', 'inner sub=0x43 -> no room yet, not responding')
        return

    # Compound-wrapped VNET::SendEnterToGame (inner type=0x82 sub=0xc8 = msg 200).
    # This run proved the Join sends the 200 INSIDE a compound (cmd=0x0212), not as a
    # bare type=0x82 - so it was hitting "echo inner" below, bouncing the 200 back to the
    # client as "in 200'40" -> FA: "NET::MESSAGE with Unknown Type 200". NEVER echo it.
    # Instead resolve the room from the inner GameIndex (inner[5:9]) and enter game mode,
    # exactly like the direct type=0x82 path, so the 0x43 game-connect poll gets answered.
    if inner_type == 0x82 and inner_sub == 0xc8:
        game_idx = int.from_bytes(inner[5:9], 'little') if len(inner) >= 9 else 0
        pname = (inner[12:44].split(b'\x00')[0].decode('ascii', 'replace').strip()
                 if len(inner) >= 13 else '')
        if not s.current_room:
            for r in db_get_open_rooms():
                if int.from_bytes(_arena_gameindex(r[2] or r[1] or 'Arena', r[0]), 'little') == game_idx:
                    s.current_room = r[0]
                    s.room_slot = (r[5] if len(r) > 5 and r[5] else (r[0] & 0xFF))
                    break
        if pname and s.current_room:
            existing = [p for p, _ in db_get_pilots_in_room(s.current_room)]
            if pname not in existing:
                db_room_join(s.current_room, pname, s.account or '')
        s.entered_game = True
        s.entering_gidx = game_idx
        s.nation = None                       # enters "In Menu" until a side is picked
        assign_player_slot(s, s.current_room)
        log('COMPOUND', f'SendEnterToGame (compound) pilot="{pname}" gidx=0x{game_idx:08x} '
                        f'room={s.current_room} -> GAME MODE, NOT echoed')
        # Same entry GRANT as the direct path: reply msg 201 (0xc9) JoinToGameAnswer.
        # GUARD (RE FUN_004f88f0): the JoinToGameAnswer handler asserts ClientID<0 on
        # entry, so a 2nd 201 while already granted crashes the client. Grant once/entry.
        if s.client_granted:
            log('COMPOUND', 'JoinToGameAnswer 201 already granted this entry - suppressing duplicate')
        else:
            s.client_granted = True
            send_rel(s, build_join_game_answer_201(s.client_number, s.player_index),
                     f'<- JoinToGameAnswer 201 (ClientNumber={s.client_number} '
                     f'PlayerIndex={s.player_index} -> GRANT)', to=5.0)
        # -- PLAYER-OBJECT LAYER (v184) -------------------------------------------
        # 62 advertises peers to the newcomer and the newcomer to peers. Both calls
        # SELF-GATE: with no peers in the room they send nothing, so a lone player's
        # entry is byte-identical to the known-good v182 path.
        # msg 96 (ScoreTable) is DEFERRED - v183 sent it here unconditionally and it
        # crashed arena-join (messages08.log): FUN_004f53b0 frees+reallocates the
        # host-side score-table object mid-entry, before the client's world is stood
        # up, wedging it (3s stall -> WinError 10054). A lone player has nothing to
        # score; seed the board later, after full world-load, not during the grant.
        def _stand_up_player_objects(_s=s):
            push_player_roster_62(_s, reason='(on enter, compound)')
            broadcast_player_join_62(_s, reason='(on enter, compound)')
        threading.Thread(target=_stand_up_player_objects, daemon=True).start()
        return

    # -- ARENA-SELECT DATA REQUESTS, compound-wrapped (inner type=0x52) ---------
    # THE ARENA-LIST RELIABILITY BUG: msg 212 (sub=0xd4, GAME_DEF request) and msg 213
    # (sub=0xd5, player-info request) sometimes arrive compound-wrapped instead of
    # direct. The old blanket inner_type==0x52 rule swallowed them -> no GAME_DEF reply
    # -> empty description + disabled Join until the client happened to re-request
    # directly (tab away and back). Answer them here exactly like the direct path.
    # inner layout: inner[4]=sub, inner[5:9]=GameIndex LE.
    if inner_sub == 0xd4:
        gidx = int.from_bytes(inner[5:9], 'little') if len(inner) >= 9 else 0
        log('COMPOUND', f'inner sub=0xd4 GAME_DEF request gidx=0x{gidx:08x}')
        handle_gamedef_request(s, gidx, via=' (compound)')
        return
    if inner_sub == 0xd5:
        gidx = int.from_bytes(inner[5:9], 'little') if len(inner) >= 9 else 0
        log('COMPOUND', f'inner sub=0xd5 ArenaPlayers request gidx=0x{gidx:08x}')
        handle_213_request(s, gidx, via=' (compound)')
        return

    # Compound inner type=0x52 (sub=0xd7/0xd9): squad/team update - do NOT echo
    if inner_type == 0x52:
        log('COMPOUND', f'inner 0x52/0x{inner_sub:02x} (squad/team update) - not echoed')
        return
    # No-echo messages (see direct path NO_ECHO_SUBS): 0x20 = no-handler status; 0x03 =
    # NET::OBJECT delete notify (echo -> bounds-error crash); 0x45 (msg 69) =
    # SCENE_TAG_MESSAGE - spawn-point selection notify. Its inbound handler asserts
    # Length % sizeof(SCENE_TAG_MESSAGE::PACKED_INFO) == 0 (VNet_Rcv.cpp:1400), so
    # echoing the 2-byte select notify crashes the client (messages03.log).
    # 0x4d (msg 77) = PLANE-PRELOAD COUNTS (handler 0x4f4080 -> FUN_0047a6f0 sets the
    # per-type count array). Echoing the client's 0x4d makes the handler parse garbage
    # -> junk counts -> 'Preload existing planes' hits an unloaded type -> index>=0 assert
    # (Pln_Info.cpp:192, messages21 crash). Swallow it -> count array stays null -> preload
    # early-outs cleanly. Client does not block on it.
    # 0x19 (msg 25) = ACE/RANK/SCORE STATE REPORT (client->server, fire-and-forget). Echoing it
    # back makes the client re-ingest its OWN report as authoritative and RE-EVALUATE ace/rank
    # against its current (garbage/stale at a team-change spawn) stat state -> bogus
    # 'Congratulations! new Ace Status' + 'new Rank' announcements (Test2 log messages46: the EVENT
    # fires on the same line as the echoed 'in 25'7', only when it lands right after InsertPlayer -
    # hence 'sometimes garbage, sometimes clean'). Consume, NEVER echo. v220.
    if inner_sub in (0x20, 0x03, 0x45, 0x18, 0x53, 0x54, 0x4d, 0x19):
        log('COMPOUND', f'inner sub=0x{inner_sub:02x} (notify, must not echo) - swallow')
        return
    # msg 31 (0x1f) compound-wrapped: ground-object damage report - consume, NEVER echo
    # (no client-side inbound handler for 31; echo raises 'Unknown Type 31'). v199.
    if inner_sub == 0x1f and getattr(s, 'entered_game', False):
        _handle_ground_damage_31(s, bytes(inner[5:]), via=' (compound)')
        return
    # Echo-by-default (lobby AND in-game) - matches the session that reached flight
    # (messages16). A blanket in-game swallow instead froze the world build at ~97%
    # (messages20), because the client waits for replies to some build/spawn messages.
    # Only the genuine fire-and-forget crashers are suppressed by the no-echo set above.
    log('COMPOUND', f'unknown inner -> echo inner')
    threading.Thread(target=lambda: send_rel(s, inner, '<- compound echo unknown inner', to=5.0), daemon=True).start()


GROUND_HP = {}   # (room_id, static-object idx) -> accumulated damage from msg 31 (v199, PvE part 1)

# --- PvE SCENE DESTROY (msg 36) -------------------------------------------------
# The authoritative destroy/state message the REAL server sent (2009 messages04):
#   out 28 (hit) + out 31 (ground-damage report)  ->  in 36 (SCENE DESTROY/STATE)
#   -> client: 'You have destroyed GER Birchwood'.
# Handler LAB_004f9d90 wire = [0x24] then Nx7-byte records:
#   [sceneIdx u16 LE][camp u8 (0xFF = neutralized/destroyed)][progress f32]
# progress <= 0 flips the scene captured. Delivered via the in-game VNET dispatch
# (FUN_004f18a0), which passes the TRUE length - so we frame with build_ingame_pkt
# (Size == n), exactly like the live 'in 36'8' (1 record).
MSG_SCENE_STATE_36 = 0x24
SCENE_CAMP_NEUTRAL = 0xFF          # camp byte meaning 'neutralized / destroyed'

# Per-terrain scene->owning-camp table. CONFIRMED from the msg-36 handler decompile
# (0x4f9d90): the record's camp byte at +2 selects the client's message path - 0xFF forces
# the GENERIC 'a bridge' text (msg 0xcb/203), while the scene's REAL camp (0..4) takes the
# NAMED path (msg 0x81/129) that prints 'You have destroyed <owner> <SceneName>'. Camps
# captured verbatim from the client's join-time scene table ('c <sceneIdx> <camp> <val> <name>').
# TRN02 (Mediterrain, 60 scenes):
SCENE_CAMP_BY_TERRAIN = {
    2: {0:1, 1:3, 2:2, 3:0, 4:4, 5:1, 6:3, 7:2, 8:0, 9:4, 10:1, 11:3, 12:2, 13:0, 14:4,
        15:1, 16:1, 17:3, 18:3, 19:2, 20:2, 21:0, 22:0, 23:4, 24:4, 25:1, 26:3, 27:2, 28:0,
        29:4, 30:1, 31:1, 32:0, 33:0, 34:2, 35:2, 36:4, 37:4, 38:3, 39:3, 40:4, 41:4, 42:4,
        43:2, 44:2, 45:2, 46:0, 47:0, 48:0, 49:1, 50:1, 51:1, 52:3, 53:3, 54:3, 55:1, 56:3,
        57:4, 58:2, 59:0},
}

def scene_camp(terrain, scene_idx):
    """Owning camp (0..4) for a scene, or SCENE_CAMP_NEUTRAL if unknown. Sending the real
    camp is what makes the client name the target instead of printing 'a bridge'."""
    return SCENE_CAMP_BY_TERRAIN.get(terrain, {}).get(scene_idx, SCENE_CAMP_NEUTRAL)

# Per-scene health, keyed by (room_id, sceneIdx). Seeded lazily to SCENE_DEFAULT_HP on
# first damage. Only consulted when AUTO_SCENE_DESTROY is enabled (see below).
SCENE_HP = {}
SCENE_DEFAULT_HP = 4000            # weapon dmg accumulates fast (a bomb = thousands); tune live
SCENE_MAX_IDX = 65                 # raw scene-instance array is 0..65 on TRN02 (60 named + extras)

# GATE: automatically decrement scene HP from msg 31 ev=0x05 and emit msg 36 on depletion.
# OFF by default. STATUS (msgs23, 02-Jul): the camp-byte fix works (msg 36 now names a real
# nation+building instead of 'a bridge'), BUT auto-destroy still hits the WRONG building -
# there are three distinct index spaces and we don't yet have the translation between them:
#   A weapon-target (msg-31 ev=0x05 obj, 0..95+)  = the building the player shoots
#   B display/valuable (join 'c' table, 0..59)     = the sorted list the player reads
#   C raw scene-instance (msg-36 sceneIdx)          = what destroys, array [0xc87270]
# We fire msg 36 with sceneIdx = weapon-obj (space A), but msg 36 indexes space C, so e.g.
# shooting Front Airfield (A=40) destroys raw building C=40 ('Storage') on the wrong team.
# The A->C map is built at terrain load into runtime arrays ([0xc85038] display list,
# [0xc87270] raw array) and is exactly the table.goi objIdx->sceneIdx data the .q6 route
# targets. Leave OFF until that translation is obtained (per-building calibration or table.goi).
AUTO_SCENE_DESTROY = False
# ^ default OFF; `autopve on` flips it live for experiments. While the A->C translation is
#   missing it will destroy the wrong building, so keep it off for normal play.

def build_scene_destroy_36(records):
    """Build FA msg 36 (0x24) SCENE DESTROY/STATE. `records` = list of
    (scene_idx:int, camp:int, progress:float). Wire: [0x24] + Nx[u16 LE sceneIdx]
    [u8 camp][f32 progress]. Framed with build_ingame_pkt so the client's Size == the
    true byte count (the in-game VNET dispatch passes real length, NOT bc*16+1; the live
    'in 36'8' = 1 record). camp 0xFF = neutralized/destroyed; progress <= 0 = captured."""
    body = bytearray([MSG_SCENE_STATE_36])
    for scene_idx, camp, progress in records:
        body += struct.pack('<HBf', scene_idx & 0xFFFF, camp & 0xFF, float(progress))
    return build_ingame_pkt(bytes(body))

# --- msg 60 (0x3c) SUPPLY GRANT = the in-world REARM/REFUEL trigger --------------------
# RE'd from the client's msg-60 handler FUN @ 0x5581c0 (reliable dispatch slot 0xc81fc8):
#   edi = raw msg buffer; local player = [0xc6eb98] -> plane obj (esi).
#   edi+3 = FLAGS byte. Observed bits:
#     &1  -> plane vtable[+0x20](1/0) at esi+0x1f4 (enable a supply/ready state)
#     &2  -> call 0x4ebfa0(plane) + [esi+0x4e8]           (resource/ammo path)
#     &4  -> call 0x4eba80(plane) [restores ordnance block esi+0xaf0..0xb04] + 0x4ec5c0
#            [fuel esi+0x500] + 0x4c8690  = THE REARM/REFUEL PATH (fuel + ammo restore)
#     &10/&20 -> alt paths; &20 reads word[edi+6]
#   edi+4 = u16 -> fild -> float  (a fuel/supply AMOUNT)
#   edi+6 = u16 -> a second AMOUNT (ammo?)
# So a msg-60 with flags&4 makes the client REARM/REFUEL IN PLACE - no despawn. Since the rearm is
# client-local and the client does NOT send msg 59 in our setup, we send msg 60 PROACTIVELY to
# trigger the rearm (e.g. from the `resupply` console command when the player is parked+depleted).
# WIRE (best-effort from the handler read-map): body = [0x3c][b1][b2][flags u8][u16 amt][u16 amt2].
# b1/b2 (between type and flags) are not yet pinned - start at 0 and iterate from the client log.
MSG_SUPPLY_GRANT_60 = 0x3c

def build_supply_grant_60(flags=0x04, amount=0xffff, amount2=0xffff, b1=0, b2=0):
    """Build FA msg 60 (0x3c) SUPPLY GRANT. flags=0x04 = the rearm/refuel path (restore fuel+ammo
    in place). amount/amount2 = the u16 fuel/ammo amounts the handler reads at body+4/+6. b1/b2 =
    the two bytes between the type and the flags (handler reads flags at edi+3), not yet pinned -
    default 0, adjust from the live client response. Framed with build_ingame_pkt (real Size)."""
    body = bytes([MSG_SUPPLY_GRANT_60, b1 & 0xff, b2 & 0xff, flags & 0xff]) \
         + struct.pack('<HH', amount & 0xffff, amount2 & 0xffff)
    return build_ingame_pkt(body)

def send_supply_grant_60(sess, flags=0x04, amount=0xffff, amount2=0xffff,
                         b1=0, b2=0, reason=''):
    """v278: send a msg-60 SUPPLY GRANT to ONE session. The client's msg-60 handler applies the
    rearm to whichever plane is LOCAL to the receiving client, so this message must only ever go to
    the pilot it is meant for. Broadcasting it rearms every plane in the room - including pilots who
    are airborne, which rebuilds their plane object mid-flight and FREEZES them (observed on the
    remote host with 4 players: 168 grants, each delivered to 2-4 sessions)."""
    if sess is None:
        return 0
    pkt = build_supply_grant_60(flags, amount, amount2, b1, b2)
    _desc = f'flags=0x{flags:02x} amt={amount} amt2={amount2} b1={b1} b2={b2}'
    threading.Thread(
        target=lambda _s=sess: send_rel(_s, pkt, f'<- SUPPLY_GRANT 60 [{_desc}] {reason}', to=3.0),
        daemon=True).start()
    log('SUPPLY60', f'{getattr(sess, "current_pilot", "?")}: msg 60 [{_desc}] {reason}')
    return 1

def broadcast_supply_grant_60(room_id, flags=0x04, amount=0xffff, amount2=0xffff,
                              b1=0, b2=0, reason=''):
    """Send a msg-60 SUPPLY GRANT to EVERY player in `room_id`. WARNING: this rearms every plane in
    the room, including airborne ones (see send_supply_grant_60). Only for the manual console
    command / single-player testing - the auto-resupply must use send_supply_grant_60."""
    if room_id is None:
        return 0
    sess = get_sessions_in_room(room_id)
    for s in sess:
        send_supply_grant_60(s, flags, amount, amount2, b1, b2, reason)
    log('SUPPLY60', f'room {room_id}: msg 60 broadcast -> {len(sess)} session(s) {reason}')
    return len(sess)

def broadcast_scene_36(room_id, records, reason=''):
    """Send a msg-36 SCENE DESTROY/STATE to every player currently in `room_id`.
    `records` = [(scene_idx, camp, progress), ...]. Reliable (matches the live
    reliable 'in 36'). Returns the number of sessions the packet was sent to."""
    if room_id is None or not records:
        return 0
    pkt = build_scene_destroy_36(records)
    sess = get_sessions_in_room(room_id)
    _desc = ', '.join(f'scene={i} camp=0x{c:02x} prog={p:g}' for i, c, p in records)
    for s in sess:
        threading.Thread(
            target=lambda _s=s: send_rel(_s, pkt, f'<- SCENE_DESTROY 36 [{_desc}] {reason}', to=3.0),
            daemon=True).start()
    log('SCENE36', f'room {room_id}: msg 36 [{_desc}] -> {len(sess)} session(s) {reason}')
    return len(sess)

def _handle_ground_damage_31(s, body, via=''):
    """FA msg 31 (0x1f) - GROUND-OBJECT DAMAGE REPORT, client->server ONLY. The client's
    inbound dispatch slot for 31 (0xc81ed8 + 31*4 = 0xc81f54) is hard-zeroed in
    FUN_004f1240, so 31 must NEVER be echoed or relayed to any client - an inbound 31
    raises 'NET::MESSAGE with Unknown Type 31' (messages17, 01-Jul session).
    Body = N x 6-byte records: [attacker ONumber u16 LE][target static-object idx u8]
    [event u8 (only 0x05 seen)][damage u16 LE]. Observed: strafing bursts dmg 92..1239 on
    objs 129/130 (fuel tanks, Bomber Airfield), one bomb = one msg with two records
    (splash over adjacent objects), player crashing INTO a fuel tank = obj 120 dmg 9976.
    v199: decode, log, accumulate per-object HP in GROUND_HP keyed by (room, obj).
    v200: when AUTO_SCENE_DESTROY is enabled, also drive per-scene HP (SCENE_HP) down and
    emit msg 36 on depletion. GATED OFF until the objidx->sceneIdx mapping is confirmed -
    the raw obj index is used as a PROVISIONAL scene key only inside that gate, never sent
    to a client while the gate is off. Raw hex is logged so a live test can still falsify
    the field layout (2nd interpretation: [00][obj u16][05][dmg])."""
    n = len(body) // 6
    recs = []
    destroyed = []                 # (sceneIdx) that crossed 0 this message (auto path only)
    for i in range(n):
        r = body[i*6:i*6+6]
        atk  = int.from_bytes(r[0:2], 'little')
        obj  = r[2]
        ev   = r[3]
        dmg  = int.from_bytes(r[4:6], 'little')
        key = (s.current_room, obj)
        GROUND_HP[key] = GROUND_HP.get(key, 0) + dmg
        recs.append(f'atk=0x{atk:04x} obj={obj} ev=0x{ev:02x} dmg={dmg} (total={GROUND_HP[key]})')
        # live obj->scene probe: record ev=0x00 reconciliation objects against the armed scene
        probe_observe(s.current_room, obj, ev)
        # weapon-obj correlation: track ev=0x05 real weapon targets
        corr_observe(s.current_room, obj, ev, dmg)
        if AUTO_SCENE_DESTROY and ev == 0x05 and s.current_room is not None and 0 <= obj <= SCENE_MAX_IDX:
            # CONFIRMED (messages21, 02-Jul): the msg-31 ev=0x05 weapon-target `obj` byte IS
            # the msg-36 sceneIdx, identity - single-target anchors obj59->scene59 (Tank
            # Factory) and obj40->scene40 (Front Airfield) both matched the join scene table,
            # and bomb-splash bursts hit the physically-adjacent scenes. ev=0x00 is client
            # reconciliation (echoes our own destroys) and must NOT be counted here.
            scene_idx = obj
            skey = (s.current_room, scene_idx)
            hp = SCENE_HP.get(skey, SCENE_DEFAULT_HP) - dmg
            SCENE_HP[skey] = hp
            if hp <= 0 and skey not in getattr(s, '_scene_destroyed', set()):
                s.__dict__.setdefault('_scene_destroyed', set()).add(skey)
                destroyed.append(scene_idx)
    log('GROUND31', f'{s.current_pilot}{via} {n} rec(s): ' + '; '.join(recs) +
                    f' | raw={body.hex()}' + (f' +tail{len(body)%6}' if len(body)%6 else ''))
    if destroyed:
        _trn = _probe_terrain_for_room(s.current_room)
        broadcast_scene_36(s.current_room,
                           [(sidx, scene_camp(_trn, sidx), 0.0) for sidx in destroyed],
                           reason='(auto from msg 31 ev=0x05)')
        for sidx in destroyed:
            log('AUTOPVE', f'{s.current_pilot} destroyed scene {sidx} camp={scene_camp(_trn, sidx)} '
                          f'(weapon damage crossed threshold)')


# --- PvE OBJ->SCENE LIVE PROBE (no .q6 needed) ------------------------------
# The msg-31 objIdx->msg-36 sceneIdx mapping is captured live using the CLIENT as oracle:
# when the client receives a msg-36 SCENE DESTROY for sceneIdx S, it emits ev=0x00
# msg-31 RECONCILIATION records for the objects belonging to that scene's region
# (observed last session: destroy 46/51 -> client re-reported objs 44-65 with ev=0x00).
# So firing destroy(S) and recording the ev=0x00 objects that come back within a short
# window yields sceneIdx->{objIdx}; inverting gives the objIdx->sceneIdx auto-PvE needs.
# Everything here is inert unless a probe is armed from the console (`probe ...`).
PROBE = {'active': False, 'scene': None, 'room': None, 'until': 0.0,
         'map': {}, 'sweep_thread': None, 'stop': False}
PROBE_LOCK = threading.Lock()
PROBE_WINDOW = 2.5            # seconds to collect ev=0x00 after each destroy
PROBE_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'objscene_map.json')

def _probe_terrain_for_room(room_id):
    """Terrain id for a room, from the rooms table (defaults to DEFAULT_TERRAIN). Used to pick
    the right scene->camp table so msg-36 names the target instead of printing 'a bridge'."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT terrain FROM rooms WHERE room_id=?", (room_id,)).fetchone()
        conn.close()
        if row and row[0] is not None:
            return int(row[0])
    except Exception:
        pass
    return DEFAULT_TERRAIN

def probe_arm(room, scene, window=PROBE_WINDOW):
    with PROBE_LOCK:
        PROBE.update(active=True, scene=scene, room=room, until=time.time() + window)

def probe_observe(room, obj, ev):
    """Called for every msg-31 record. Records ev=0x00 objects against the armed scene."""
    if ev != 0x00:
        return
    with PROBE_LOCK:
        if not PROBE['active'] or PROBE['room'] != room:
            return
        if time.time() > PROBE['until']:
            PROBE['active'] = False
            return
        PROBE['map'].setdefault(PROBE['scene'], set()).add(obj)

def probe_save():
    with PROBE_LOCK:
        by_scene = {str(s): sorted(v) for s, v in PROBE['map'].items()}
        inv = {}
        for s, objs in PROBE['map'].items():
            for o in objs:
                inv[str(o)] = s
    try:
        existing = json.load(open(PROBE_MAP_PATH)) if os.path.exists(PROBE_MAP_PATH) else {}
    except Exception:
        existing = {}
    existing.setdefault('by_scene', {}).update(by_scene)
    existing.setdefault('obj_to_scene', {}).update(inv)
    json.dump(existing, open(PROBE_MAP_PATH, 'w'), indent=1, sort_keys=True)
    return len(inv), PROBE_MAP_PATH

def probe_fire(room, scene):
    """Arm the window then fire a real destroy(scene) so the client reconciles."""
    probe_arm(room, scene)
    broadcast_scene_36(room, [(scene, SCENE_CAMP_NEUTRAL, 0.0)], reason=f'(probe scene {scene})')

def probe_sweep(room, lo, hi, gap=3.0):
    """Walk sceneIdx lo..hi, one destroy each with `gap` seconds between so each scene's
    ev=0x00 reconciliation lands inside its own window. Daemon thread; `probe stop` cancels."""
    def _run():
        for sc in range(lo, hi + 1):
            with PROBE_LOCK:
                if PROBE['stop']:
                    break
            probe_fire(room, sc)
            log('PROBE', f'swept scene {sc} (room {room})')
            time.sleep(gap)
        n, path = probe_save()
        log('PROBE', f'sweep done: {n} objIdx->sceneIdx entries saved to {path}')
    with PROBE_LOCK:
        PROBE['stop'] = False
    t = threading.Thread(target=_run, daemon=True)
    PROBE['sweep_thread'] = t
    t.start()


# --- PvE WEAPON-OBJ -> SCENE CORRELATION PROBE -----------------------------
# Auto-PvE needs weapon-target objIdx (msg-31 ev=0x05, e.g. 130) -> msg-36 sceneIdx. The
# destroy-sweep only exercises ev=0x00 reconciliation (scene-space 0..65), never the weapon
# space, so it cannot yield this. This mode captures it by CORRELATION:
#   1. `corr watch`      arm: every ev=0x05 record's obj is tracked with accumulating damage,
#                        so `corr show` reveals which building you're actually hitting.
#   2. strafe ONE building; its obj (e.g. 130) appears under `corr show` with rising dmg.
#   3. `corr find <obj>` server sweeps destroy over candidate scenes; narrows which scene
#                        silences that obj's ev=0x05 stream (noisy - a helper, not proof).
#   4. `corr map <obj> <scene>`  record an EYE-CONFIRMED anchor (you saw it blow up) to
#                        weapon_map.json. This is the source of truth for auto-PvE.
# Inert unless armed. Reuses broadcast_scene_36.
CORR = {'watch': False, 'weapon': {}, 'find_obj': None, 'find_thread': None,
        'stop': False, 'last05': {}}
CORR_LOCK = threading.Lock()
CORR_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'weapon_map.json')

def corr_observe(room, obj, ev, dmg):
    """Called for every msg-31 record. Tracks ev=0x05 weapon targets + last-seen time."""
    if ev != 0x05:
        return
    with CORR_LOCK:
        if not CORR['watch']:
            return
        w = CORR['weapon'].setdefault(obj, {'hits': 0, 'dmg': 0, 'first': time.time()})
        w['hits'] += 1
        w['dmg'] += dmg
        CORR['last05'][obj] = time.time()

def corr_map_save(obj, scene):
    try:
        existing = json.load(open(CORR_MAP_PATH)) if os.path.exists(CORR_MAP_PATH) else {}
    except Exception:
        existing = {}
    existing.setdefault('weapon_obj_to_scene', {})[str(obj)] = scene
    json.dump(existing, open(CORR_MAP_PATH, 'w'), indent=1, sort_keys=True)
    return CORR_MAP_PATH

def corr_find(room, obj, lo=0, hi=59, gap=4.0):
    """Sweep destroy lo..hi; after each, note whether `obj` (recently active via ev=0x05)
    stops producing new ev=0x05 - a candidate for the scene that removed it. Heuristic only;
    confirm by eye and record with `corr map`."""
    def _run():
        with CORR_LOCK:
            active = obj in CORR['last05']
        log('CORR', f'find obj={obj}: sweeping destroy {lo}..{hi} gap={gap}s '
                    f'(obj {"active" if active else "NOT yet active - strafe it during the sweep!"})')
        candidates = []
        for sc in range(lo, hi + 1):
            with CORR_LOCK:
                if CORR['stop']:
                    break
                last_seen = CORR['last05'].get(obj, 0)
            broadcast_scene_36(room, [(sc, SCENE_CAMP_NEUTRAL, 0.0)],
                               reason=f'(corr find obj {obj} scene {sc})')
            time.sleep(gap)
            with CORR_LOCK:
                new_last = CORR['last05'].get(obj, 0)
                silent = (new_last == last_seen)
                recently_active = (last_seen and (time.time() - last_seen) < gap * 3)
            if silent and recently_active:
                candidates.append(sc)
                log('CORR', f'  candidate: obj {obj} went silent after destroy scene {sc}')
        log('CORR', f'find obj={obj} done. candidate scene(s): '
                    f'{candidates or "none - strafe the target continuously during the sweep"}')
    with CORR_LOCK:
        CORR['stop'] = False
    t = threading.Thread(target=_run, daemon=True)
    CORR['find_thread'] = t
    t.start()


def _fire_server_confirm(s, via='', ident=None):
    """Fire ServerConfirm (msg 5) for the current spawn: stamps the global object
    Number onto the client's plane and starts its sim loop (engine/controls). Idempotent
    per spawn via s.obj_confirmed (reset on each StartPlace grant). The trigger is the
    client's out-4 full-state, which arrives DIRECT (msg-id @ pl[4]) on the first spawn
    and FA type-scan DOUBLE-WRAPPED (msg-id @ pl[8]) on a re-spawn (airfield change) -
    both must reach here or the re-spawned plane stays cold (engine won't start)."""
    if not (SERVERCONFIRM_READY and not s.obj_confirmed):
        return
    _isrc = 'from out-4'             # v198: the client's registration ident is IN its out-4
    if ident is None:                #       payload; a server-side counter drifts (parachute
        ident = s.spawn_ident_next   #       advances the client's ident but is never confirmed).
        _isrc = 'counter fallback'   #       Counter kept only as fallback for a too-short out-4.
    number = next_obj_number()       # GLOBALLY-unique u16 so each player's telemetry id differs
    s.my_obj_number = number; s.obj_confirmed = True; s.flying = True
    # v276: a spawn/respawn (HQ entry OR base change) starts the plane fresh at a base. Reset the
    # auto-resupply position tracking so the new spawn starts a CLEAN static settle - the old
    # object's transit/wind-down position deltas must not leak into the new base's stationary check.
    s.last_pos = None; s.pos_static_since = None
    s.pos_static_samples = 0; s.last_pos_telem_t = 0.0
    s.resupplied_this_stop = False
    s.spawn_time = time.time()       # v279: starts the auto-resupply spawn grace window
    s._left_world = False            # fresh spawn re-arms the exit/leave guard
    s.spawn_ident_next = ident + 1   # keep fallback counter in lock-step with the client
    log('CONFIRM5', f'out 4 spawn{via} -> ServerConfirm Number={number} ident={ident} ({_isrc})')
    threading.Thread(target=lambda nn=number, ii=ident: send_reply(
        s, build_server_confirm_5(nn, ii),
        f'<- ServerConfirm 5 (Number={nn} ident={ii})', to=5.0), daemon=True).start()
    # v219: state the pilot's REAL career aces/rank on the client scoreboard. Those score-object
    # fields (score+0x50 aces, score+0x30 rank) are written ONLY by msg 88; if we never send it they
    # hold whatever the score object had -> the garbage aces/rank seen after a team-swap re-entry.
    # Values are RE-READ FROM THE DB each time (never zeroed), so a spawn/team/room change restores
    # the pilot's true career standing. The score object exists once the create-object's client
    # record has registered the station, which is in place by the time the spawn is ServerConfirmed.
    # v233: a fresh plane is UNDAMAGED. Clear the damage flag on EVERY spawn, unconditionally - the
    # "exited damaged -> death" rule must only ever see damage taken in THIS life. (This was nested
    # inside the SEND_ACE_RANK_88 block, so turning that flag off would silently leave took_damage
    # latched and make every clean exit count as a death again.)
    s.took_damage = False
    # v243: and a fresh plane hasn't moved yet. Drop the old life's position history so the
    # "was it flying?" crash test can't be fooled by the PREVIOUS sortie's movement.
    s.__dict__.pop('_pos_hist', None)
    # v244: and nobody has hit this plane yet. Clear the last-hit attribution so a hunter from the
    # PREVIOUS life can never be credited with a kill in this one.
    # v247: object numbers are RECYCLED, so a latch left over from a previous plane that happened to
    # carry this number must not be inherited by the new one. Drop it.
    PENDING_KILL.pop(getattr(s, 'my_obj_number', None), None)
    # v248: a fresh plane means the previous life's parachuter (if any) is history.
    s.para_obj_number = None
    if SEND_ACE_RANK_88:
        def _send88(_s=s):
            time.sleep(0.5)
            send_ace_rank_88(_s, reason='(spawn init)')
            # v230/v236: msg 25 writes the 20-dword block at score+0x30 - the SAME block whose f0 is
            # the rank the HQ Scores screen displays. So it should drive that screen's Latest/Career
            # rows too (the in-flight Current Life/Current Game screen is client-computed and does
            # NOT read it - that was the wrong screen to probe).
            send_stat_block_25(_s, reason='(spawn init)')
            # v236: (re)state EVERY OTHER player's rank/aces as well. A client only learns a peer's
            # rank if we send that peer's msg 88 to it - without this a freshly-joined client shows
            # every other pilot as rank 0 ('Cdt').
            for _p in get_sessions_in_room(_s.current_room):
                if _p is not _s:
                    send_ace_rank_88(_p, reason='(peer refresh for new spawn)')
        threading.Thread(target=_send88, daemon=True).start()
    if ADD_TEST_PLAYER:
        def _inject(_s=s):
            time.sleep(1.0)
            m62 = build_add_player_62([(1, 0, 'Test2', 0)])
            send_rel(_s, build_msg13(m62),
                     '<- msg 13 { 62 AddPlayer Test2 idx=1 camp=0 }', to=5.0)
            log('SIM13', 'injected remote player Test2 via msg 13{62}')
        threading.Thread(target=_inject, daemon=True).start()

def _cancel_pending_death(s, why=''):
    """v225: cancel a deferred solo-death credit (see _ingame_own_object_removed)."""
    t = getattr(s, '_pending_death', None)
    if t is not None:
        try:
            t.cancel()
        except Exception:
            pass
        s._pending_death = None
        log('DEATH', f'{s.current_pilot} pending death CANCELLED {why}'.rstrip())

def _ingame_own_object_removed(s, tb, stored):
    """Shared handler for a msg-3 (sub 0x03) that removes the player's OWN plane while in the
    arena. It arrives BOTH as a direct tb=0x42/0x52/0x32 message AND wrapped in an outer type=0x06
    (the type-scan form). A CRASHLAND uses the WRAPPED form, so both call sites must route here or
    the crashland respawn is never re-armed and its out 4 gets no ServerConfirm (Conductor error ->
    dead engine -> CTD). Drops the dead plane on peers, stays in the arena, and re-arms
    obj_confirmed/flying. Idempotent via _left_world (cleared on the respawn's ServerConfirm).

    *** v225: NOT EVERY OWN-PLANE REMOVAL IS A DEATH. ***
    v222 made this credit a death unconditionally, which triple-counted: one crash logged THREE
    deaths. The payload is [.. sub=0x03][ONumber u16 LE][REASON byte], and the three cases are:

      REASON 0xa0 / 0x80 (bit 0x80 SET)   = the plane was DESTROYED  -> a real loss.
      REASON 0x11 / 0x22 (bit 0x80 CLEAR) = plane removed WITHOUT being destroyed. This is the
            RESPAWN handoff: the client drops its old plane as it takes a new one. In run
            004058 the StartPlace GRANT arrives in the SAME MILLISECOND as the 0x11 removal
            (log lines 1146 -> 1148). NEVER a death.

    Destroyed (0xa0) still covers two situations that are IDENTICAL on the wire at this instant -
    a genuine crash, and EXIT-TO-HQ (bailing out of the arena). They only differ by what happens
    NEXT: a crash is followed by a respawn, while an exit-to-HQ is followed ~3s later by the
    back-to-lobby leave (run 004058: removal 00:44:24.974 -> 'back to lobby' 00:44:27.756).
    So a SOLO destroy is credited on a short DEFERRED timer and CANCELLED if the player leaves the
    arena inside the window. A respawn does NOT cancel it (a real death is followed by a respawn
    ~2s later, so cancelling on respawn would erase every genuine death).
    A SHOT-DOWN (the long >=14B scored form) is never ambiguous and is credited immediately.
    """
    if (s.entered_game and not getattr(s, '_left_world', False)
            and s.my_obj_number is not None):
        # *** v235: WHICH OBJECT IS THIS DELETE ACTUALLY ABOUT? ***
        # The delete-notify is [.. sub=0x03][ONumber u16 LE][exit][tail...], so the object it names
        # is stored[5:7]. This handler ALWAYS assumed it was the sender's OWN plane and never
        # checked - which is how Test2 vanished from Bigalon's world (run 095012):
        #     Test2 sent  [00320000|030101]  = "delete object 0x0101"  = BIGALON's plane,
        #     a routine peer-view cleanup on Test2's side.
        # We took it as Test2's own removal and BROADCAST A DELETE FOR TEST2'S OBJECT (0x0100) TO
        # BIGALON - so Bigalon's client dutifully deleted Test2 - then cleared Test2's `flying` flag
        # so the relay stopped too. We told the peer to delete the very plane the message was
        # protecting. Verify the ONumber before touching anything.
        _onum = struct.unpack_from('<H', stored, 5)[0] if len(stored) >= 7 else None
        # v248: the PARACHUTER is a second object owned by this same session. Its delete means the
        # pilot has landed / been killed under the canopy - it is NOT the plane going down, so it
        # must not run the death path. Pass it on to peers so the canopy disappears there too.
        if _onum is not None and _onum == getattr(s, 'para_obj_number', None):
            log('PARA', f'{s.current_pilot} parachuter 0x{_onum:04x} removed (landed or killed) '
                        f'-> relaying the delete to peers; the plane (0x{s.my_obj_number:04x}) is '
                        f'unaffected')
            _pdel = build_delete_object_3(onumber=_onum, client_number=None)
            for _peer in get_sessions_in_room(s.current_room):
                if _peer is not s:
                    threading.Thread(target=send_rel, args=(_peer, _pdel,
                                     f'<- delete PARACHUTER 0x{_onum:04x} ({s.current_pilot})'),
                                     kwargs={'to': 3.0}, daemon=True).start()
            s.para_obj_number = None
            return
        if _onum is not None and _onum != s.my_obj_number:
            # NOT the sender's own plane. Find whose it is.
            _peer = next((p for p in get_sessions_in_room(s.current_room)
                          if p is not s and getattr(p, 'my_obj_number', None) == _onum), None)
            if _peer is not None:
                # The sender dropped this PEER's object from its world. Forget that we ever created
                # it there, so the telemetry relay re-creates it on the next update - otherwise the
                # sender would never see that peer again.
                _cp = _peer.__dict__.get('_created_peers')
                if _cp is not None:
                    _cp.discard(s.addr)
                log('PEERDEL', f'{s.current_pilot} dropped PEER object 0x{_onum:04x} '
                               f'({_peer.current_pilot}) from its world -> re-arm create for that '
                               f'peer. NOT a removal of {s.current_pilot}\'s own plane.')
            else:
                log('PEERDEL', f'{s.current_pilot} sent a delete for object 0x{_onum:04x} which is '
                               f'neither its own (0x{s.my_obj_number:04x}) nor any peer\'s -> swallow')
            return

        s._left_world = True
        exitb = stored[7] if len(stored) > 7 else 0
        mec_nib = (exitb >> 4) & 0xf     # MissExitCode & 0xf  (Msn_Exit: (MEC << 4) | ScoreEvent)
        se      = exitb & 0xf            # ScoreEvent / exit form (0..5)
        scored  = len(stored) >= 14      # long form = shot down by someone
        is_death = mec_nib in DEATH_MEC_NIBBLES
        # v229: the client's delete-notify is [.. sub=0x03][id u16][exit][tail...] starting at
        # stored[4], so the ExitDataArrive ENTRY (id + exit + tail, with the HUNTER at +3) is
        # exactly stored[5:5+size]. Relay it VERBATIM - zero-filling that tail is what stopped
        # kills registering.
        _esz = EXIT_EEC_ENTRY_SIZE.get(se)
        exit_entry = (bytes(stored[5:5 + _esz])
                      if (_esz and len(stored) >= 5 + _esz) else None)
        _hunter = (struct.unpack_from('<H', exit_entry, 3)[0]
                   if (exit_entry is not None and len(exit_entry) >= 5) else None)
        log('POST-AUTH', f'msg-3 delete-notify (tb=0x{tb:02x}) = in-arena plane removal '
                         f'(exit=0x{exitb:02x} -> MEC&0xf={mec_nib} SE={se}, '
                         f'{"DEATH" if (is_death or scored) else "not a death"}'
                         f'{", scored" if scored else ""}'
                         + (f', hunter=0x{_hunter:04x}' if _hunter is not None else '')
                         + ') -> drop plane, stay in arena, re-arm confirm')

        _killer = None
        if scored:
            # Shot down - unambiguous (the entry names the HUNTER). Always a death.
            _killer = score_on_death(s, stored, hunter_obj=_hunter, victim_obj=_onum)
        elif is_death:
            # v232: A CRASH AND A CLEAN GROUND EXIT ARE IDENTICAL ON THE WIRE - both MissExitCode 26,
            # both followed by the same 0x3a catalog request, neither producing a leave event. So the
            # exit packet alone can never tell them apart.
            # Two independent signals settle it, and a death needs only ONE of them:
            #   (a) DAMAGE  - msg 28 marked this plane (cleared on every fresh spawn). That is the
            #       client's own rule: exit while damaged and it counts as a death, and the game even
            #       warns you. But msg 28 only ever carries PLAYER-inflicted damage.
            #   (b) v243 MOVEMENT - was the plane actually FLYING when it was removed? A parked plane
            #       reports EXACTLY zero movement, sample after sample; a flying one moves by hundreds
            #       per tick. This is what finally catches the UNDAMAGED CRASH (fly into the ground,
            #       no enemy fire, no msg 28) - which the damage rule alone was blind to.
            _damaged = bool(getattr(s, 'took_damage', False))
            _move    = plane_movement(s)
            _flying  = _move >= CRASH_MOVEMENT_MIN
            if _damaged or _flying or COUNT_EXIT_TO_HQ_AS_DEATH:
                _why = ('DAMAGED' if _damaged else '') + ('+' if _damaged and _flying else '') \
                       + (f'IN FLIGHT (movement={_move})' if _flying else '')
                log('DEATH', f'{s.current_pilot} {_why} at removal (MEC&0xf={mec_nib}) '
                             f'-> counts as a death')
                # v244: CAPTURE the killer here too. This branch used to DISCARD score_on_death's
                # return value, so even when a killer was identified, _killer stayed None and the
                # SCORED DELETE was never sent to them - which is why Bigalon's client never
                # registered the bailout kill even though Test2's client announced it.
                _killer = score_on_death(s, stored, hunter_obj=_hunter, victim_obj=_onum)
            else:
                log('DEATH', f'{s.current_pilot} exited UNDAMAGED and PARKED (MEC&0xf={mec_nib}, '
                             f'movement={_move}) -> clean exit, NOT a death')
        else:
            log('DEATH', f'{s.current_pilot} plane removed with exit=0x{exitb:02x} '
                         f'(MEC&0xf={mec_nib} SE={se}) -> re-fly/plane-swap, NOT a death')

        broadcast_object_delete_3(s, reason='(death)', clear_peer_created=False, killer=_killer,
                                  exit_byte=exitb, exit_entry=exit_entry)
        # v203: the 2009 host's AUTHORITATIVE credit - a separate msg-33 ScoreEvent to the
        # killer, on top of the scored delete. v224: MEC/EEC nibbles fixed (type byte 0x13).
        if _killer is not None and SEND_SCORE_EVENT_33:
            send_score_event_to_killer(_killer)
        free_obj_number(s.my_obj_number)      # recycle this plane's Number for the next spawn
        # Re-arm the spawn-confirm so a crashland respawn (InsertPlayer + out 4 with NO StartPlace)
        # still gets a ServerConfirm. A normal death's StartPlace also resets these - harmless.
        s.obj_confirmed = False; s.flying = False
    else:
        log('POST-AUTH', f'msg-3 delete-notify (tb=0x{tb:02x}) -> swallow, no echo (guarded)')

def _msg20_instrument(s, variant, channel, text, pl):
    """v258: capture the RAW bytes of every in-game msg-20 (type 0x14) AND the other message types
    that correlate with a parachuter's descent in the 2009 log.

    Findings so far (2009 messages04.log):
      * 'in 20' is a SERVER->CLIENT broadcast (1820x, 13-129 bytes, only 8 client replies - NOT a
        poll). Its 'out 20' replies cluster around players ENTERING/JOINING - so msg 20 is largely
        ROSTER/player-state sync, probably NOT the parachuter mechanism.
      * During parachuter 975's descent the non-roster messages were 'in 30'5' (tiny, appears right
        after create and again seconds later - a strong per-object STATE/deploy candidate), plus
        'in 72'/'in 73'. These are logged separately by _ingame_msg_instrument.
    Pure logging, no behaviour change.
    """
    if not MSG20_INSTRUMENT:
        return
    body = bytes(text)
    printable = sum(1 for b in body if 32 <= b < 127 or b in (9, 10, 13))
    ratio = (printable / len(body)) if body else 1.0
    kind = 'CHAT?' if ratio >= 0.75 else 'BINARY/STATE?'
    onums = []
    for i in range(0, len(body) - 1):
        v = int.from_bytes(body[i:i + 2], 'little')
        if v in (getattr(s, 'my_obj_number', -1) or -1,
                 getattr(s, 'para_obj_number', -1) or -1):
            onums.append(f'@{i}=0x{v:04x}')
    _bail = 'BAILED' if getattr(s, 'para_obj_number', None) is not None else 'normal'
    log('MSG20', f'{s.current_pilot} [{variant}] ch={channel} len={len(body)} {kind} '
                 f'ratio={ratio:.2f} state={_bail}'
                 + (f' objs[{",".join(onums)}]' if onums else '')
                 + f' full_pl={hx(bytes(pl))}')

# v258: the in-game message types that correlated with a parachuter's descent in the 2009 log.
# 0x1e=30 (tiny per-object state, the deploy candidate), 0x48=72, 0x49=73, 0x14=20 (roster).
PARA_WATCH_TYPES = {0x1e, 0x48, 0x49, 0x14, 0x1f, 0x28}

def _ingame_msg_instrument(s, sub, pl):
    """v258: while a bail is in progress (parachuter alive), dump the FULL bytes of any watched
    in-game message type, so we can find the one that carries the parachuter descent + deploy state.
    Only fires when this pilot has an active parachuter, to keep the log focused."""
    if not MSG20_INSTRUMENT or getattr(s, 'para_obj_number', None) is None:
        return
    if sub not in PARA_WATCH_TYPES:
        return
    body = bytes(pl)
    pnum = getattr(s, 'para_obj_number', None)
    mine = getattr(s, 'my_obj_number', None)
    hits = [f'@{i}=0x{int.from_bytes(body[i:i+2],"little"):04x}'
            for i in range(len(body) - 1)
            if int.from_bytes(body[i:i + 2], 'little') in (pnum, mine)]
    log('PARAWATCH', f'{s.current_pilot} type=0x{sub:02x}({sub}) len={len(body)} '
                     f'para=0x{(pnum or 0):04x}'
                     + (f' objhits[{",".join(hits)}]' if hits else '')
                     + f' pl={hx(body)}')

# v263: SUPPLY/REPAIR message capture. The 2009 flow at spawn/land is:
#   InsertPlayer(OnGround) -> client 'out 59'19' (supply/startplace request) -> server 'in 60'8'
#   (grant) -> 'Repair PlnID:.. Full=1/0, Load:..' (server-driven rearm/refuel via msg 40'38 / 73'39).
# As the SERVER we RECEIVE 0x3b (59) from the client and must reply 0x3c (60), then send 40/73 to
# rearm. We don't author those bytes - we capture the client's real request first (replay method).
# This logs the FULL bytes of any inbound supply/repair-related sub so we can reverse the format.
SUPPLY_MSG_INSTRUMENT = True   # v264: log ALL reliable-channel messages while a plane is in-arena,
                              #   decoding the prefixed inner sub too, so the real spawn/land/supply/
                              #   repair flow is visible (the 2009 '59/60/40/73' are CONDUCTOR numbers;
                              #   our reliable subs differ - seen: sub=0x60 sz=5 at spawn, prefixed 0x40).
                              #   Set False once the supply/repair messages are identified.
SUPPLY_WATCH_SUBS = None       # None = log everything (in-arena); or a set to filter

# v267 P2a: auto-resupply. When the player parks at an airfield and shuts the engine off, the server
# sends the proven msg-60 supply grant (full repair + rearm). BLIND for all arenas for now - the TC
# per-airfield supply gate is P2b.
AUTO_RESUPPLY = True
AUTO_RESUPPLY_DEBOUNCE = 5.0   # seconds; fire at most once per this window per player
AUTO_RESUPPLY_SETTLE = 2.0     # seconds stationary (ground speed 0) before the resupply fires
AUTO_RESUPPLY_POLL = 0.5       # v272: background poll interval for the stationary check
# v277 SAFETY (remote-server fix): the poll must never mistake a STALE position view for a stationary
# plane. Over a high-latency/lossy link the telemetry stops arriving while the plane is still flying,
# so re-reading the same cached packet looked 'static' and fired a mid-flight rearm (which rebuilds
# the plane object and FROZE the client). So: only judge stationarity from FRESH, NEWLY-ARRIVED
# telemetry, and require several consecutive new packets that all report the same position.
AUTO_RESUPPLY_FRESH = 1.5      # telemetry older than this => we cannot judge; reset + skip
AUTO_RESUPPLY_MIN_SAMPLES = 3  # consecutive NEW telemetry packets with identical position required
# v279: after a spawn/respawn the CLIENT is still building the plane object. A msg-60 that lands in
# that window corrupts it: run 05.50.26 shows 'Create NetPlane ... ONumber=258' followed 4ms later by
# our 'Repair PlnID:5 ... Load:0' and then an 8.5-MINUTE flood of
# 'ERROR: IPC net PlnID:5; Cur:0, New:0, Net:1' (local loadout state never reconciles with the net
# state). So the auto-resupply must stay silent until the freshly spawned plane is fully built.
AUTO_RESUPPLY_SPAWN_GRACE = 10.0  # seconds after ServerConfirm before an auto-grant may fire

def _supply_msg_instrument(s, sub, cmd, pl):
    """v264: capture the spawn/land/supply/repair message flow. Logs every reliable-channel message
    once the pilot is in-arena (entered_game), decoding the PREFIXED inner sub (pl[8]) for cmd!=0
    messages - the 2009 supply flow (in 59/60/40/73) is on the CONDUCTOR numbering; on our reliable
    channel the spawn/supply msgs appear as different subs (e.g. type=0x12 sub=0x60 sz=5 at spawn, a
    prefixed sub=0x40). Logging everything in-arena lets us spot the real supply/repair messages
    instead of guessing their numbers."""
    if not SUPPLY_MSG_INSTRUMENT:
        return
    if not getattr(s, 'entered_game', False):
        return
    body = bytes(pl)
    # decode the prefixed inner sub for cmd!=0 messages (real sub is at pl[8], type at pl[5])
    _prefixed = (cmd and len(body) >= 9 and not (body[2] == 0 and body[3] == 0)
                 and body[6] == 0 and body[7] == 0)
    _inner_type = body[5] if _prefixed and len(body) > 5 else (body[1] if len(body) > 1 else 0)
    _inner_sub = body[8] if _prefixed and len(body) > 8 else sub
    if SUPPLY_WATCH_SUBS is not None and _inner_sub not in SUPPLY_WATCH_SUBS and sub not in SUPPLY_WATCH_SUBS:
        return
    log('SUPPLY-CAP', f'{s.current_pilot} cmd=0x{cmd:04x} '
                      f'{"PFX " if _prefixed else ""}type=0x{_inner_type:02x} sub=0x{_inner_sub:02x} '
                      f'len={len(body)} flying={getattr(s,"flying",False)} pl={hx(body)}')

def _auto_resupply_check(s, sub, pl):
    """v272: gate the auto-resupply on ACTUAL GROUND SPEED = 0, not proxy events. v271 used
    StartPlace/engine/heartbeat signals, which (a) missed a plane that never moved from spawn (no
    new signal) and (b) fired on touchdown while still rolling. v272 uses plane_movement(s) (the
    quantised-position delta already tracked for crash detection): a stationary plane reports
    EXACTLY 0. This fn just maintains at_airfield + a 'moving' observation; the actual fire decision
    is made by a background poll (_resupply_poll) that checks movement==0 for AUTO_RESUPPLY_SETTLE
    seconds. Cancelled implicitly by movement (position changes) or takeoff/despawn."""
    if not AUTO_RESUPPLY:
        return
    if not getattr(s, 'entered_game', False):
        return
    body = bytes(pl)
    # takeoff / despawn clears the parked-airfield association
    if sub == 0x53 and len(body) >= 6 and (body[5] & 1) == 1:   # engine ON
        s.at_airfield = None
        return
    if sub == 0x03:                                             # despawn / exit-to-HQ
        s.at_airfield = None
        return
    # StartPlace request/notify -> we're at an airfield slot. Two framings:
    #   direct:  sub(pl[4]) = 0x17/0x18, AF ident at body[5]
    #   scan:    sub(pl[4]) = 0x00, inner 0x17/0x18 at pl[8], AF ident at body[9] (type-scan wrap)
    _new_af = None
    if sub in (0x17, 0x18) and len(body) >= 8:
        _new_af = body[5]
    elif sub == 0x00 and len(body) >= 12 and body[8] in (0x17, 0x18):
        _new_af = body[9]
    if _new_af is not None:
        # v276: a base change (tab) re-fires StartPlace + a fresh ServerConfirm, i.e. it's a respawn
        # at the new base. Treat it like an HQ entry: reset the position/static tracking so the new
        # base starts a CLEAN settle (the transit drift from the old base won't leak in / block it).
        if _new_af != getattr(s, 'at_airfield', None):
            s.last_pos = None
            s.pos_static_since = None
            s.pos_static_samples = 0
            s.last_pos_telem_t = 0.0
            s.resupplied_this_stop = False
        s.at_airfield = _new_af

def _resupply_poll_loop():
    """v277: background poll gating resupply on the plane's position being STATIC - but ONLY when
    that judgement is backed by FRESH, NEWLY-ARRIVED telemetry.

    v274-v276 compared the cached last_plane_telem on every poll tick. On localhost that was fine
    (telemetry arrives ~every 0.5s), but on a REMOTE server the stream stalls while the plane is
    still flying - the poll then re-read the same cached packet, saw an unchanged position, and
    concluded 'stationary'. That fired a mid-flight msg-60 rearm, which rebuilds the plane object
    and FROZE the client. Staleness must never look like stillness.

    v277 therefore requires all of:
      * telemetry FRESH  - last_telem_time within AUTO_RESUPPLY_FRESH, else reset the clock and skip
      * a NEW packet     - last_telem_time must advance before a sample counts (no double-counting
                           one cached packet across poll ticks)
      * repeated agreement - AUTO_RESUPPLY_MIN_SAMPLES consecutive new packets with the SAME position
      * settled          - position unchanged for AUTO_RESUPPLY_SETTLE seconds
    Any position change, telemetry gap, takeoff, or respawn resets the clock. BLIND (TC gate = P2b)."""
    while True:
        try:
            time.sleep(AUTO_RESUPPLY_POLL)
            if not AUTO_RESUPPLY:
                continue
            now = time.time()
            for s in list(get_all_sessions()):
                if not getattr(s, 'entered_game', False):
                    continue
                if getattr(s, 'at_airfield', None) is None or s.current_room is None:
                    s.last_pos = None; s.pos_static_since = None
                    s.pos_static_samples = 0; s.last_pos_telem_t = 0.0
                    s.resupplied_this_stop = False
                    continue
                tel_t = getattr(s, 'last_telem_time', 0.0)
                # (0) SPAWN GRACE: a freshly spawned plane is still being constructed client-side.
                #     Repairing it mid-build leaves it permanently desynced (IPC net error flood).
                _spawn_t = getattr(s, 'spawn_time', 0.0)
                if _spawn_t > 0 and (now - _spawn_t) < AUTO_RESUPPLY_SPAWN_GRACE:
                    s.last_pos = None; s.pos_static_since = None
                    s.pos_static_samples = 0
                    continue
                # (1) FRESHNESS: a stale view means the plane may be moving and we simply can't see
                #     it (remote-link stall). Never accumulate stillness from it.
                if tel_t <= 0 or (now - tel_t) > AUTO_RESUPPLY_FRESH:
                    s.last_pos = None; s.pos_static_since = None
                    s.pos_static_samples = 0
                    continue
                # (2) NEW PACKET: only evaluate once per actually-received telemetry packet.
                if tel_t <= getattr(s, 'last_pos_telem_t', 0.0):
                    continue
                s.last_pos_telem_t = tel_t
                tel = getattr(s, 'last_plane_telem', None)
                pos = None
                if tel and len(tel) >= 15:
                    try:
                        pos = struct.unpack_from('<HHH', tel, 9)
                    except struct.error:
                        pos = None
                if pos is None:
                    continue
                prev = getattr(s, 'last_pos', None)
                if prev is None or pos != prev:
                    # moving (or first fresh sample) -> restart the stationary clock and re-arm the
                    # one-shot: the plane must come to rest again before it can resupply once more.
                    s.last_pos = pos
                    s.pos_static_since = now
                    s.pos_static_samples = 1
                    s.resupplied_this_stop = False
                    continue
                # (3) same position on a NEW packet -> a genuine stationary observation
                s.pos_static_samples = getattr(s, 'pos_static_samples', 0) + 1
                if s.pos_static_samples < AUTO_RESUPPLY_MIN_SAMPLES:
                    continue
                # (4) settled long enough?
                static_for = now - getattr(s, 'pos_static_since', now)
                if static_for < AUTO_RESUPPLY_SETTLE:
                    continue
                # (5) ONE-SHOT: v276 re-fired every DEBOUNCE seconds for as long as the plane sat
                #     parked (168 grants in one remote session). Fire once per stop; the plane must
                #     move and settle again (or respawn) before another grant.
                if getattr(s, 'resupplied_this_stop', False):
                    continue
                s.resupplied_this_stop = True
                s.last_resupply_at = now
                # (6) TARGETED: only the parked pilot. Broadcasting rearms airborne pilots too.
                send_supply_grant_60(
                    s, flags=0x04, amount=0xffff, amount2=0xffff,
                    reason=f'(auto-resupply: {s.current_pilot} stationary at AF={s.at_airfield})')
                log('RESUPPLY', f'{s.current_pilot} position static {static_for:.1f}s '
                                f'({s.pos_static_samples} fresh samples) at AF={s.at_airfield} '
                                f'(pos={pos}) -> auto msg-60 grant (blind, one-shot)')
        except Exception:
            logx('RESUPPLY', 'poll loop error')

def handle_post_auth(s, cmd, pl):
    bc=pl[0] if pl else 0; tb=pl[1] if len(pl)>1 else 0
    sub=pl[4] if len(pl)>4 else 0
    # *** v246: PREFIXED (cmd != 0) MESSAGES ARE FRAMED 4 BYTES LATER. ***
    # The reliable framing is [bc][T][00][00][sub][...]. But when the packet's `cmd` field is
    # NON-ZERO, the payload carries a 4-byte prefix - [counter u16][cmd u16 BE] - in FRONT of it.
    # The codebase already knew this in two places: the login path reads pl[4:6], and
    # handle_compound does `inner = pl[4:]`. But handle_compound only fires for a HARD-CODED
    # WHITELIST of three cmds (COMPOUND_CMDS = {530, 578, 4610}), so every OTHER cmd!=0 message is
    # parsed from the WRONG OFFSET.
    # That silently ATE THE BAILOUT DELETE (run 083507 @ 08:47:57, cmd=1346 / 0x0542):
    #       normal  delete: [00 42 00 00 | 03 00 01 a0]
    #       bailout delete: [00 00 05 42 | 00 42 00 00 | 03 00 01 50]
    # We read the ONumber as 0x0042 instead of 0x0100, so v235's peer-object check concluded it was
    # "neither its own nor any peer's" and SWALLOWED the whole thing -> the shooter got no kill, and
    # the peer was never told to remove the plane, so it flew on until the client gave up on it.
    # DELIBERATELY NOT RE-FRAMING GLOBALLY: ~10% of reliable messages are prefixed and have been
    # ignored for the entire life of this server (they parse to sub=0x00 and match no handler).
    # Switching them all on at once is exactly how you break a working lobby - one of them decodes
    # to sub=0xd4 = LEAVE. So re-frame the DELETE, which is the demonstrated bug, and LOG every
    # other prefixed message so the rest can be tackled one at a time, on evidence.
    _pfx = (cmd and cmd not in COMPOUND_CMDS and len(pl) >= 9
            and not (pl[2] == 0 and pl[3] == 0) and pl[6] == 0 and pl[7] == 0)
    if _pfx:
        _isub = pl[8]
        if _isub == 0x03:                       # delete-notify - the one we know is broken
            log('REFRAME', f'{s.current_pilot} cmd=0x{cmd:04x} PREFIXED delete-notify '
                           f'[{hx(bytes(pl[:4]))}] -> re-framing from offset 4 '
                           f'(was mis-read as ONumber 0x{int.from_bytes(bytes(pl[5:7]),"little"):04x})')
            pl = pl[4:]
            bc = pl[0]; tb = pl[1]; sub = pl[4] if len(pl) > 4 else 0
        else:
            log('REFRAME', f'[note] {s.current_pilot} cmd=0x{cmd:04x} is a PREFIXED message we are '
                           f'NOT re-framing (inner type=0x{pl[5]:02x} sub=0x{_isub:02x}). It has '
                           f'always been ignored; logged for review.')
    log('POST-AUTH',f'cmd={cmd}(0x{cmd:04x}) type=0x{tb:02x} sub=0x{sub:02x} bc={bc}(p3={bc*16+1}) sz={len(pl)}')
    stored=bytes(pl)
    _h4=hx(stored[:4]) if len(stored)>=4 else hx(stored)
    _d4=hx(stored[4:8]) if len(stored)>=8 else (hx(stored[4:]) if len(stored)>4 else '')
    log('RX/REL/PL', f'  [{_h4}|{_d4}] +{hx(stored[8:8+80]) if len(stored)>8 else ""}')
    _ingame_msg_instrument(s, sub, stored)     # v258: dump watched types while a parachuter is alive
    _supply_msg_instrument(s, sub, cmd, stored)  # v263: capture supply/repair msgs (59/60/40/73)
    _auto_resupply_check(s, sub, stored)         # v267: auto msg-60 resupply on park+engine-off

    if cmd in COMPOUND_CMDS:
        handle_compound(s, cmd, pl); return

    if (len(pl) > 8 and pl[8] == 0xcd) or sub == 0xcd:
        _handle_chat_pl(s, pl); return

    # -- IN-ARENA CHAT (msg 20 / 0x14) ------------------------------------------
    # Sent by the client as [0x14][channel:1][text\0]; channel 0=all,1=team,2=squadron.
    # The FA reliable type-scan cycles the OUTER type per message, so the same chat
    # arrives in different wrappers: DIRECT (sub=pl[4]=0x14, e.g. type=0xe2) or a
    # type-scan double-wrap (outer type 0x01..0x12, inner header, sub at pl[8]=0x14).
    # Compound-wrapped chat (cmd in COMPOUND_CMDS) is caught in handle_compound above.
    # We reflect with PlayerIndex=0 (the player from the 201 grant) so the display
    # handler FUN_004f6030 resolves it to "Test1" instead of logging "unknown player".
    if sub == 0x14:                                            # direct
        channel = pl[5] if len(pl) > 5 else 0
        text    = bytes(pl[6:]) if len(pl) > 6 else b''
        _msg20_instrument(s, 'direct', channel, text, pl)
        reflect_chat_20(s, channel, text); return
    if sub == 0x00 and len(pl) > 10 and pl[8] == 0x14:         # type-scan double-wrap
        channel = pl[9]
        text    = bytes(pl[10:])
        _msg20_instrument(s, 'typescan', channel, text, pl)
        reflect_chat_20(s, channel, text); return

    # -- TEAM / SIDE SELECT (msg 68 / 0x44) -------------------------------------
    # [0x44][nation:1][?:1]; nation 0..7 = side (US=0...), 0xff = leave. No incoming
    # handler in FA.exe -> never echo. Same wrapper variants as chat.
    if sub == 0x44:                                            # direct
        nation = pl[5] if len(pl) > 5 else 0xff
        handle_team_select(s, nation); return
    if sub == 0x00 and len(pl) > 9 and pl[8] == 0x44:          # type-scan double-wrap
        nation = pl[9]
        handle_team_select(s, nation); return

    # -- LEAVE ARENA / BACK TO LOBBY (msg 64 / 0x40) ----------------------------
    # No inbound handler in FA.exe -> never echo (echo -> "Unknown Type 64"). Same
    # wrapper variants as the others.
    if sub == 0x40:                                            # direct
        handle_leave_arena(s); return
    if sub == 0x00 and len(pl) > 8 and pl[8] == 0x40:          # type-scan double-wrap
        handle_leave_arena(s); return

    # -- GROUND-WAR DAMAGE REPORT (msg 31 / 0x1f) - consume + decode, NEVER echo ----
    # Direct form (outer type rotates: 0x72/0xd2/... with sub at pl[4]) and the
    # type-scan double-wrap (sub=0x00, msg-id at pl[8]). Compound form is caught in
    # handle_compound. See _handle_ground_damage_31 for the wire layout + evidence.
    if sub == 0x1f and s.entered_game:
        _handle_ground_damage_31(s, bytes(pl[5:]))
        return
    if sub == 0x00 and len(pl) > 9 and pl[8] == 0x1f and s.entered_game:
        _handle_ground_damage_31(s, bytes(pl[9:]), via=' (scan)')
        return

    # -- NOTIFY MESSAGES, type-scan double-wrapped - must not be echoed ---------
    # 0x03 = NET::OBJECT delete notify (echo -> client-side bounds-error crash),
    # 0x20 = no-handler status (echo -> "Unknown Type 32"). Direct variants are
    # swallowed by NO_ECHO_SUBS below; this catches the wrapped form before the
    # generic echo fallthrough re-sends the whole wrapper.
    if sub == 0x00 and len(pl) > 8 and pl[8] == 0x03:
        # Wrapped NET::OBJECT delete: a CRASHLAND death arrives as outer type=0x06 + inner 0x03,
        # so it MUST run the same in-arena removal path (re-arm the spawn-confirm), not be swallowed
        # - otherwise the crashland respawn's out 4 gets no ServerConfirm and the engine stays dead.
        _ingame_own_object_removed(s, tb, stored)
        return
    if sub == 0x00 and len(pl) > 8 and pl[8] in (0x20, 0x45):
        log('POST-AUTH', f'scan-inner sub=0x{pl[8]:02x} (notify, must not echo) -> swallow')
        return

    # -- FLY / START PLACE (msg 23 / 0x17) --------------------------------------
    # [0x17][AF][mid][N]; N=0xff = request. Reply is the GRANT (see
    # handle_fly_start_place) - echoing the request back denies the spawn.
    if sub == 0x17 and len(pl) >= 8:                           # direct
        handle_fly_start_place(s, pl[5], pl[6], pl[7]); return
    if sub == 0x00 and len(pl) >= 12 and pl[8] == 0x17:        # type-scan double-wrap
        handle_fly_start_place(s, pl[9], pl[10], pl[11], via=' (scan)'); return

    # -- OUT-4 SPAWN STATE, type-scan DOUBLE-WRAPPED (re-spawn / airfield change) --
    # The first spawn's out-4 is DIRECT (msg-id 0x04 @ pl[4], outer type 0x12), caught
    # later in the tb==0x12 block. On a RE-spawn the type-scan rotates the outer type
    # (seen: 0x1e) and double-wraps it: outer hdr | inner appspace hdr [bc][0x12] |
    # 04 01..., so msg-id 0x04 lands at pl[8] and it never enters tb==0x12. Result was
    # ServerConfirm never firing -> re-spawned plane's sim loop never started -> engine
    # stayed cold ('couldn't start engine' after an airfield change). Catch it here,
    # independent of the rotated outer type. out-4 is the client's own state -> never
    # echoed, so swallowing (return) is correct.
    if s.entered_game and len(pl) > 8 and pl[5] == 0x12 and pl[8] == 0x04:
        _ident = struct.unpack_from('<H', pl, 9)[0] if len(pl) >= 11 else None   # v198: client's ident
        _fire_server_confirm(s, via=' (scan)', ident=_ident)
        return

    if cmd == 0:
        if tb == 0x12:
            if sub == 0xe1:
                pilots=db_get_pilots(s.account) if s.account else []
                resp=build_e1_pilot_list(pilots)
                threading.Thread(target=lambda:send_rel(s,resp,'<- pilot list',to=5.0),daemon=True).start(); return
            if sub == 0xde:
                def da_then_echo():
                    da=build_da_session()
                    if not send_rel(s,da,'<- 0xDA',to=5.0): return
                    time.sleep(0.005); send_rel(s,stored,'<- echo 0xde',to=5.0)
                threading.Thread(target=da_then_echo,daemon=True).start(); return
            if sub in (0xce, 0xca, 0xcb):
                if sub == 0xce:
                    active_rooms = db_get_open_rooms()
                    resp = build_ce_room_list(active_rooms)
                    raw_len = len(resp) - 4  # payload after vcncNet header
                    log('CE', f'AppSpaceList: {len(active_rooms)} room(s) -> {raw_len} bytes raw')
                    label = f'<- AppSpaceList ({len(active_rooms)} rooms, {raw_len}B)'
                elif sub == 0xcb:
                    # GameList = THE ARENA LIST (confirmed via FUN_004f03b0).
                    # Respond with open rooms as arena records instead of empty.
                    active_rooms = db_get_open_rooms()
                    resp = build_gamelist(active_rooms)
                    raw_len = len(resp) - 4
                    label = f'<- GameList ({len(active_rooms)} arenas, {raw_len}B, fmt={GAMELIST_FORMAT})'
                else:
                    names = {0xca:'ServerList'}
                    resp = build_empty_room_list(sub)
                    label = f'<- empty {names.get(sub, hex(sub))}'
                threading.Thread(target=lambda:send_rel(s,resp,label,to=5.0),daemon=True).start()
                # NOTE (v151): NO room echo here. List population is done entirely by
                # the 0xcb GameList response above ([0xcb] + per arena [1 byte][name\0],
                # parsed by FUN_004ef8b0). The old send_all_room_echoes() pushed 0x92
                # echoes that drove the client into a room (0x43 polling) instead of
                # leaving it on the Arenas list. Rooms created live by OTHER sessions
                # are still broadcast via the 0xdc create path; steady-state listing is
                # the 0xcb query the client issues when opening the Arenas tab.
                return
            if sub == 0xcd:
                _handle_chat_pl(s, pl); return
            if sub == 0xd2:
                # 0xd2 = THE ARENA LIST request (real log: out 210'1 -> in 210'1110).
                # v164: push each room's GAME_DEF (212) FIRST so the client caches the
                # arena's terrain, then send the list. (Was: list only -> terrain 0 crash.)
                active_rooms = db_get_open_rooms()
                threading.Thread(
                    target=lambda: send_arenalist_with_gamedefs(
                        s, active_rooms, f'<- ArenaList 0xd2 ({len(active_rooms)} rooms)'),
                    daemon=True).start(); return
            # APPSPACE-type outer with inner 0x43 (e.g. [00120000|00120000]+43)
            # type=0x12 is used as the outer type by the retry counter in this case.
            if sub == 0x00 and len(pl) >= 9 and pl[5] == 0x12 and pl[8] == 0xd2 and not s.entered_game:
                log('POST-AUTH','APPSPACE-scan sub=0xd2 -> echo inner')
                threading.Thread(target=lambda: send_rel(s, build_appspace_pkt(bytes([0xd2])),
                                 '<- APPSPACE-scan echo 0xd2', to=3.0), daemon=True).start()
                return
            if sub == 0x00 and len(pl) >= 9 and pl[5] == 0x12 and pl[8] == 0x43:
                now = time.time()
                if now - s.last_43_ts >= 0.5:
                    s.last_43_ts = now
                    _maybe_grant_create_entry(s)   # creator's post-create 0x43 poll -> 201 GRANT
                    if SEND_EXIT_UNRELIABLE and getattr(s,'_awaiting_reattach',False) and not s.entered_game:
                        send_unrel(s, build_da_session_safe(), '<- 0xDA re-attach RESEND (appspace 0x43 poll)')
                    room_slot = getattr(s,'room_slot',0)
                    rooms = db_get_open_rooms()
                    if rooms and (s.current_room or room_slot):
                        rid   = s.current_room or rooms[0][0]
                        pcount= db_room_player_count(rid)
                        slot  = room_slot or (rid & 0xFF)
                        rd = bytes([0x43,slot,0,0,0,pcount,0x01,0,0,0,0,0,0,0,0,0,0])
                        log('POST-AUTH',f'APPSPACE-scan sub=0x43 -> room confirm slot=0x{slot:02x} players={pcount}')
                        resp = build_appspace_pkt(rd)
                        threading.Thread(target=lambda:send_rel(s,resp,'<- APPSPACE-scan 0x43',to=3.0),daemon=True).start()
                    else: log('POST-AUTH','APPSPACE-scan sub=0x43 -> no room yet')
                else: log('POST-AUTH','APPSPACE-scan sub=0x43 -> rate-limited')
                return
            if sub == 0x43:
                # 0x43 poll. In lobby mode this is the room-creation confirm; after
                # VNET::SendEnterToGame (s.entered_game) the client polls it once a second
                # as the game-connect handshake (reliable; the type-scan is its retry). We
                # now ANSWER it in both modes so the client stops retrying and we can drive
                # the game-entry. EXPERIMENT v170: reply with the [0x43][slot][..][players]
                # confirm and observe whether the client advances or wants a scene push next.
                now = time.time()
                if now - s.last_43_ts < 0.5:
                    log('POST-AUTH', 'sub=0x43 -> rate-limited, skipping')
                    return
                s.last_43_ts = now
                _maybe_grant_create_entry(s)   # creator's post-create 0x43 poll -> 201 GRANT
                room_slot = getattr(s, 'room_slot', 0)
                rooms = db_get_open_rooms()
                if rooms and (s.current_room or room_slot):
                    rid    = s.current_room or rooms[0][0]
                    pcount = db_room_player_count(rid)
                    slot   = room_slot or (rid & 0xFF)
                    # data[6]=0x01 (lobby flag in creation); keep it for the first game-mode
                    # test - if the client rejects it we'll vary this byte / the layout.
                    resp_data = bytes([0x43, slot, 0x00, 0x00, 0x00, pcount, 0x01,
                                       0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                    mode = 'GAME' if s.entered_game else 'lobby'
                    log('POST-AUTH', f'sub=0x43 {mode} confirm -> slot=0x{slot:02x} '
                        f'db_id={rid} players={pcount}')
                    resp = build_appspace_pkt(resp_data)
                    threading.Thread(target=lambda:send_rel(s,resp,f'<- 0x43 {mode} confirm',to=3.0),daemon=True).start()
                else:
                    log('POST-AUTH', 'sub=0x43 -> no room, not responding (avoids null crash)')
                return
            if sub == 0x60 and s.entered_game:
                # Bare 0x60 = client REQUESTS the SCORE_TABLE (msg 96). Sent right
                # after the FLY 23 StartPlace grant (messages09.log 06:51:00.782).
                # v184 left it unanswered -> client stalled in the 0x43 poll loop, the
                # launch timer never started, CTD after ~20s. THIS is the correct,
                # solicited send point for 96 - the v183 crash was sending it
                # UNSOLICITED during entry, before the client's world existed.
                log('SCORE96', 'bare 0x60 = ScoreTable request -> answering msg 96 (small populated defs)')
                resp = build_score_table_96(object_groups=SCORE_DEFS_DEFAULT)   # 0..31 type slots,
                #   points in `extra` (= score-def+0xc); ~321B so it fits a single reliable packet.
                threading.Thread(target=lambda: send_rel(s, resp,
                                 '<- ScoreTable 96 (on request)', to=5.0), daemon=True).start()
                return
            if sub == 0x66 and s.entered_game:
                # Bare 0x66 (msg 102): function unknown (no inbound handler slot for
                # 102; the client emits it right after team select). v185 answered it
                # with a 62 roster INCLUDING the requester - FATAL (messages10.log):
                # the msg 201 handler (FUN_004f88f0) already creates the LOCAL
                # player's entry in the player table (FUN_004f3230 + insert, camp=-1),
                # and a 62 record for an existing index DELETES + re-adds it - i.e. it
                # freed the live local player while the GamerClient still pointed at
                # it -> use-after-free -> delayed CTD (~1.7s). Unanswered 0x66 is proven
                # harmless (messages09: client chatted and flew fine). -> swallow.
                log('POST-AUTH', f'bare 0x66 from {s.current_pilot} -> swallow '
                                 f'(unknown fn; harmless unanswered. self-62 barred by invariant)')
                return
            # msg 4 (0x04) = client's FULL object state at spawn - it arrives as type=0x12
            # sub=0x04, so it MUST be caught HERE, before this block's catch-all return.
            # (messages33: with the check placed AFTER the tb==0x12 block the catch-all
            # below swallowed msg 4 and ServerConfirm never fired -> same ~50s freeze.) The
            # first msg 4 after a StartPlace is the ServerConfirm (msg 5) trigger - the gate
            # that stamps the global Number onto the client's plane and starts the sim loop.
            # msg 4/6 are the client's OWN state, never echoed.
            if s.entered_game and sub == 0x04:
                _ident = struct.unpack_from('<H', pl, 5)[0] if len(pl) >= 7 else None   # v198: client's ident
                # v201: PLANE TYPE. The client's out-4 spawn carries its selected plane's
                # index at payload byte[8] (the ordinal into the nation's plane list -
                # F4F-3=0, P-39D=1, P-40C=2, ...). CONFIRMED from a 2-player capture where
                # AC2E_Bigalon flew P-40C(idx2) on spawn-ident 0 and byte[8]=0x02, while
                # Test2 flew F4F-3(idx0) with byte[8]=0x00 (ruling out the earlier
                # ident/plane confound). Store it so send_create_object_for gives peers the
                # RIGHT aircraft instead of the hardcoded P-39D.
                if len(pl) >= 9:
                    s.plane_type = pl[8]
                    log('PLANE', f'{s.current_pilot} selected plane index {pl[8]} (out-4 byte[8])')
                _fire_server_confirm(s, ident=_ident)   # DIRECT out-4; double-wrapped variant caught earlier
                return
            return

        # In-game flight telemetry (msg 83=0x53, 84=0x54, 24=0x18, plus 6=0x06 position
        # stream) arrives wrapped in various outer types (0x22, 0x42, 0x82). The per-type
        # handlers below (0x22, 0x42) echo unknown subs by DEFAULT, so this guard MUST come
        # first: echoing telemetry back makes FA log "NET::MESSAGE with Unknown Type N" and
        # freeze the link (messages22). Lobby unaffected (entered_game False): pilot
        # create/rename/delete (0xe2/0xe3/0xe7) still echo normally.
        if s.entered_game and sub in (0x18, 0x53, 0x54, 0x06):
            log('POST-AUTH', f'in-game telemetry type=0x{tb:02x} sub=0x{sub:02x} -> swallow (no echo)')
            return
        # WRAPPED in-game telemetry: during rapid respawns the client sometimes emits its
        # position/state in the extra-wrapped form `00 00 00 00 00 82 .. <inner@pl[8]>` - pl[1]
        # then reads as sub=0x00, so the direct guard above misses it and it fell through to the
        # generic echo, which bounced it back as a reliable type=0x00. The client's Conductor
        # can't parse a type-0 reliable msg ("Server sent client something it doesn't understand
        # (-102)"), stops ACKing, and the whole reliable channel dies - surfacing as "waiting
        # start place expired" + an empty plane list on the next respawn. Swallow it exactly like
        # the direct telemetry form. Requires pl[5]==0x82 AND an inner telemetry sub at pl[8]
        # (0x18/0x53/0x54/0x06) so it can never collide with the wrapped VNET::SendEnterToGame
        # (pl[5]==0x82, pl[8]==0xc8) handled further below. Same pl[8]-inner convention as the
        # chat/team/leave double-wrap guards above.
        if (s.entered_game and sub == 0x00 and len(pl) > 8
                and pl[5] == 0x82 and pl[8] in (0x18, 0x53, 0x54, 0x06)):
            log('POST-AUTH', f'in-game telemetry (wrapped, inner=0x{pl[8]:02x}) -> swallow (no echo)')
            return

        # In-game COMBAT DAMAGE (msg 28 = sub 0x1c). The shooter's client does its OWN hit
        # detection and emits the per-bodypart hit records as a RELIABLE message ('out 28' /
        # 'You have hit ...'). It must be RELAYED to the other player(s) so the TARGET takes
        # the damage and can die. The old default ECHOED it back to the shooter, which then
        # re-applied its own damage to its LOCAL copy of the target -> over-killed a remote
        # object it doesn't own -> attacker CTD, while the target took nothing (server.log:
        # every 'sub=0x1c -> echo'; messages09: zero 'in 28'). Object ids are GLOBAL (the
        # target id is identical on every client), so forward the bytes as-is, reliably, to
        # each flying peer; no remap/re-stamp needed.
        if s.entered_game and sub == 0x1c:
            s.last_fired_at = time.time()   # stamp shooter for kill attribution on a peer's death
            # v232/v244: DAMAGE TRACKING. The msg-28 record is [VictimNumber i16][HunterNumber i16]
            # [count u8] + count*9B (HitToPlaneCB, FUN_004f3820). Two things come out of it:
            #   * the VICTIM is marked DAMAGED - that (with v243's movement test) separates a real
            #     death from a clean exit. The client's own rule: exit while damaged and it counts.
            #   * v244: WHO HIT THEM. We were parsing the victim and THROWING THE HUNTER AWAY - but
            #     it is the only way to credit a BAILOUT kill. A bailout's delete-notify is the SHORT
            #     form (exit 0x50: MEC nibble 5 = shot down, but ScoreEvent 0 -> a 3-byte entry with
            #     NO hunter field), so the victim never names its killer on the wire. Its own client
            #     knows perfectly well - Test2's log says "HitFrom(Number=256...)" and announces
            #     "AC2E_Bigalon has destroyed You" - it just doesn't tell us. Recording the hunter
            #     here gives us the same fact, exactly.
            try:
                _victim_num = struct.unpack_from('<h', stored, 5)[0]
                _hunter_num = struct.unpack_from('<h', stored, 7)[0]
                for _p in get_sessions_in_room(s.current_room):
                    if getattr(_p, 'my_obj_number', None) == _victim_num:
                        _p.took_damage = True
                        _p.last_damaged_at = time.time()
                        if _hunter_num and _hunter_num > 0 and _hunter_num != _victim_num:
                            # v247: LATCH THE KILL AGAINST THE OBJECT, with no expiry. The victim's
                            # own client has just told us who hit it - that is a FACT, and it stays
                            # true no matter how long the plane takes to come down.
                            PENDING_KILL[_victim_num] = {'killer': _hunter_num,
                                                         'at': time.time(), 'why': 'damage'}
                        log('DAMAGE28', f'{_p.current_pilot} (obj 0x{_victim_num:04x}) is now DAMAGED '
                                        f'by obj 0x{_hunter_num & 0xffff:04x} -> an exit from here '
                                        f'counts as a death, and that hunter holds the kill until '
                                        f'this plane is destroyed')
                        break
            except Exception:
                pass
            peers = [x for x in get_sessions_in_room(s.current_room)
                     if x is not s and getattr(x, 'flying', False)]
            for p in peers:
                threading.Thread(target=lambda _p=p: send_rel(_p, stored,
                                 f'<- DAMAGE 28 relay ({s.current_pilot}->{_p.current_pilot})', to=3.0),
                                 daemon=True).start()
            log('DAMAGE28', f'{s.current_pilot} hit -> relay to {len(peers)} peer(s) '
                            f'in room {s.current_room} ({len(stored)}B)')
            return

        # NET::OBJECT delete-notify (msg 3 / sub=0x03) rides tb=0x42 (del object) or
        # tb=0x52 (del client). The tb==0x42 branch below echoes unknown subs by DEFAULT,
        # so echoing it back = 'Server require delete object' on a bogus id ->
        # ARR<NET::OBJECT*,2048> bounds CTD on the SENDER (messages90). NEVER echo it.
        # It is ALSO the exit-to-HQ signal (this leave sends no msg-64): the first one,
        # while still flying, drives peer plane-removal (type-3) + the 0xDA HQ handoff.
        # _left_world keeps catching the trailing del-client 0x03 after entered_game clears.
        if (s.entered_game or getattr(s, '_left_world', False)) and sub == 0x03:
            # A msg-3 that removes the player's OWN plane WHILE IN THE ARENA is a death
            # (crash / shot / crashland) OR an exit-to-HQ. Routed through the shared helper so the
            # DIRECT (tb=0x42/0x52/0x32) and the type-scan WRAPPED (outer 0x06) forms behave
            # identically - a crashland uses the wrapped form (handled at the scan-inner call site).
            _ingame_own_object_removed(s, tb, stored)
            return

        if tb == 0x22:
            if sub == 0xe2 and s.account:
                name_raw=pl[6:] if len(pl)>6 else b''
                new_name=name_raw.split(b'\x00')[0].decode('ascii',errors='replace')
                if new_name:
                    slot=db_next_slot(s.account); db_ensure_pilot(new_name,s.account,slot)
            threading.Thread(target=lambda:send_rel(s,stored,'<- echo 0xe2',to=5.0),daemon=True).start(); return

        if tb == 0x42:
            if sub == 0xe3:
                name_raw = pl[8:] if len(pl)>8 else b''
                pname = name_raw.split(b'\x00')[0].decode('ascii', 'replace')
                if pname and s.account: db_delete_pilot(pname, s.account)
                data = bytearray(33); data[0]=0xe3
                nb = pname.encode() + b'\x00'
                data[4:4+min(len(nb),29)] = nb[:29]
                resp = build_typed_pkt(0x42, bytes(data), bc=2)
                threading.Thread(target=lambda: send_rel(s, resp, '<- delete success', to=5.0), daemon=True).start(); return
            if sub == 0xe7:
                old_raw = pl[8:40] if len(pl)>=40 else pl[8:]
                new_raw = pl[40:72] if len(pl)>=72 else b''
                old_name = old_raw.split(b'\x00')[0].decode('ascii', 'replace')
                new_name = new_raw.split(b'\x00')[0].decode('ascii', 'replace')
                if old_name and new_name and s.account: db_rename_pilot(old_name, new_name, s.account)
                threading.Thread(target=lambda: send_rel(s, stored, '<- echo rename', to=5.0), daemon=True).start(); return
            threading.Thread(target=lambda: send_rel(s, stored, 'echo type=0x42', to=5.0), daemon=True).start(); return

        if tb == 0x62 and sub == 0xe4:
            pname, explicit_slot = parse_e4_selection(pl)
            if pname:
                slot = explicit_slot or db_get_pilot_slot(s.account, pname) or 0
                s.current_pilot = pname; s.current_slot = slot
                log('POST-AUTH',f'Pilot selected: "{pname}" slot={slot}')
                # NOTE (v151): NO room auto-restore. The real client never auto-joins
                # a room on reconnect - the player lands on the tabbed menu and only
                # sees rooms when they open the Arenas tab (via the 0xcb list). The old
                # restore + 0x92 echo made the client believe it owned/occupied a room
                # and start 0x43 polling, which confounded every list test. The room
                # still exists server-side (db_get_open_rooms) and appears in 0xcb.
                broadcast_system(f'[{pname}] has joined the lobby')
                broadcast_player_join(pname, exclude_sess=s)
                threading.Thread(target=lambda: send_initial_ui_list(s), daemon=True).start()
                threading.Thread(target=lambda: send_active_list(s), daemon=True).start()
            threading.Thread(target=lambda:send_rel(s,stored,'<- echo 0xe4',to=5.0),daemon=True).start()
            return

        if tb == 0x01:
            # Guard: only trigger for real ExitAppSpace notice (len<=5 = no inner data).
            # Type-scan packets also use type=0x01 but have inner data (len=9).
            # Without this guard, type-scan packets kill the session prematurely.
            if len(pl) <= 5:
                log('POST-AUTH','vcncExitAppSpace notice')
                if s.current_pilot:
                    broadcast_player_leave(s.current_pilot, exclude_sess=s)
                    broadcast_system(f'[{s.current_pilot}] has left')
                    db_room_leave(s.current_pilot)
                s.closing=True
                with sl: sadrs.pop(s.addr,None); sids.pop(s.sid,None)
                return
            # else: type-scan packet with inner data - fall through to generic echo

        # type=0x92 sub=0xdc direct path (fallback; normally arrives via compound cmd=18)
        if tb == 0x92 and sub == 0xdc and len(pl) > 33:
            data = pl[4:]
            room_slot = data[1] if len(data) > 1 else 0
            creator_raw = data[5:29].split(b'\x00')[0].decode('ascii','replace') if len(data)>5 else ''
            creator = s.current_pilot or creator_raw
            game_def = bytes(data[29:])   # full GAME_DEF (no 769 truncation)
            room_id = db_create_room(creator, s.account or '', game_def, room_slot)
            s.current_room = room_id; s.room_slot = room_slot
            if creator:
                if not PERSIST_ROOMS:              # one-room-per-creator - gated (see compound path)
                    _c = sqlite3.connect(DB_PATH)  # close stale rooms (direct)
                    _c.execute("UPDATE rooms SET status='closed' WHERE creator_pilot=? AND status='open' AND room_id!=?",
                               (creator, room_id))
                    _c.commit(); _c.close()
                db_room_join(room_id, creator, s.account or '')  # players=1 from first 0x43
            log('POST-AUTH', f'ROOM CREATED (direct) db_id={room_id} slot=0x{room_slot:02x} creator="{creator}" players=1')
            broadcast_system(f'[{creator}] created a room', exclude_sess=s)
            # Echo to creator (existing behavior) + broadcast to all other sessions
            # so their arena lists show the new room.
            threading.Thread(target=lambda:send_rel(s,stored,'<- echo room create',to=5.0),daemon=True).start()
            threading.Thread(target=lambda:broadcast_room_creation(room_id, exclude_sess=s), daemon=True).start()
            return

        # type=0x52: pilot/squad/team update packets (FA.exe -> server only)
        # sub=0xd5 = pilot status (rank, score, faction)
        # sub=0xd7 = team/squad name update (loops if echoed - FA.exe retries indefinitely)
        # sub=0xd9 = related team info (same issue)
        # DO NOT echo: echoing type=0x52 back to FA.exe causes infinite retry loops
        # and fills the squadron page with GAME_DEF garbage when triggered by wrong 0xce data.
        if tb == 0x52:
            if sub == 0xe0:
                # sub=0xe0 = "EnterArena" phase 1 (5 bytes: [0xe0][GameIndex 4B])
                # Sent at type=0x52 just before VNET::SendEnterToGame.
                # GameIndex at pl[5:9] LE.
                if len(pl) >= 9:
                    game_idx = int.from_bytes(pl[5:9], 'little')
                    log('POST-AUTH', f'EnterArena sub=0xe0 GameIndex=0x{game_idx:08x} ({game_idx}) - accepted')
                else:
                    log('POST-AUTH', f'EnterArena sub=0xe0 len={len(pl)} - accepted')
                return
            if sub == 0xd7:
                # sub=0xd7 = FUN_004f0570 "SetArena" (5 bytes: [0xd7][GameIndex 4B])
                # Sets current arena on server. No response needed.
                if len(pl) >= 9:
                    game_idx = int.from_bytes(pl[5:9], 'little')
                    log('POST-AUTH', f'SetArena sub=0xd7 GameIndex=0x{game_idx:08x} - accepted')
                else:
                    log('POST-AUTH', f'SetArena sub=0xd7 len={len(pl)} - accepted')
                return
            if sub == 0xd4:
                # FA message 212 - on-demand GAME_DEF request ("out 212'5"); see
                # handle_gamedef_request. pl[5:9] = GameIndex (LE).
                game_idx = int.from_bytes(pl[5:9], 'little') if len(pl) >= 9 else 0
                handle_gamedef_request(s, game_idx)
                return
            if sub == 0xd5:
                # FA message 213 - arena player-info request; see handle_213_request.
                game_idx = int.from_bytes(pl[5:9], 'little') if len(pl) >= 9 else 0
                handle_213_request(s, game_idx)
                return
            else:
                log('POST-AUTH', f'type=0x52 sub=0x{sub:02x} len={len(pl)} - accepted (not echoed)')
            return

                # VNET::SendEnterToGame - DIRECT FORMAT: bc=2, type=0x82, cmd=0, sub=0xc8=200
        # FA.exe logs: "VNET::SendEnterToGame GameIndex=NNN" + "out 200'40"
        # Pilot name at pl[12:44] (32-byte null-padded, confirmed from capture).
        # DO NOT echo this packet - server echoing type=0x82/sub=0xc8 causes FA.exe
        # to log "NET::MESSAGE with Unknown Type 200" and break the session.
        # After this, stop sending 0x43 responses; FA.exe will exit cleanly via type-scan.
        if tb == 0x82 and sub == 0xc8 and len(pl) >= 44:
            game_idx = int.from_bytes(pl[5:9], 'little') if len(pl) >= 9 else 0
            pname_raw = pl[12:44] if len(pl) >= 44 else pl[12:]
            pname = pname_raw.split(b'\x00')[0].decode('ascii', 'replace').strip()
            # Browse-and-join / arena SWITCH: resolve which room is being entered from the
            # GameIndex in the 200 packet. v260: resolve ALWAYS (not just 'if not current_room'),
            # so switching from one arena to another actually moves the player. If the resolved
            # room differs from the current one, leave the old room first (drop this player's
            # REMOTE_PLAYER + plane from the old arena's peers and the DB) so nothing leaks between
            # arenas - the previous gate left current_room stale on a switch, so chat/telemetry/
            # roster kept scoping to the old arena and peers in different arenas saw each other.
            _resolved_room = None
            for r in db_get_open_rooms():
                if int.from_bytes(_arena_gameindex(r[2] or r[1] or 'Arena', r[0]), 'little') == game_idx:
                    _resolved_room = r[0]
                    _resolved_slot = (r[5] if len(r) > 5 and r[5] else (r[0] & 0xFF))
                    break
            if _resolved_room is not None and _resolved_room != s.current_room:
                if s.current_room is not None:
                    # switching arenas: drop us from the OLD arena cleanly first
                    _old_room = s.current_room
                    try:
                        broadcast_player_leave(s.current_pilot, exclude_sess=s)
                    except Exception:
                        pass
                    if s.my_obj_number is not None:
                        try:
                            broadcast_object_delete_3(s, reason='(switched arena)')
                        except Exception:
                            pass
                    try:
                        db_room_leave(s.current_pilot)
                    except Exception:
                        pass
                    log('POST-AUTH', f'ARENA SWITCH: {s.current_pilot} left room {_old_room} '
                                     f'-> room {_resolved_room} (gidx=0x{game_idx:08x})')
                s.current_room = _resolved_room
                s.room_slot = _resolved_slot
            elif not s.current_room and _resolved_room is not None:
                s.current_room = _resolved_room
                s.room_slot = _resolved_slot
            if pname and s.current_room:
                existing = [p for p,_ in db_get_pilots_in_room(s.current_room)]
                if pname not in existing:
                    db_room_join(s.current_room, pname, s.account or '')
                log('POST-AUTH', f'VNET::SendEnterToGame (direct) pilot="{pname}" gidx=0x{game_idx:08x} room={s.current_room}')
            else:
                log('POST-AUTH', f'VNET::SendEnterToGame (direct) pilot="{pname}" gidx=0x{game_idx:08x} (no room)')
            s.entered_game = True
            s.entering_gidx = game_idx
            s.nation = None                   # enters "In Menu" until a side is picked
            assign_player_slot(s, s.current_room)
            log('POST-AUTH', 'GAME MODE - will answer 0x43 game-connect poll (not echoing 200)')
            # Send the real entry GRANT: msg 201 (0xc9) JoinToGameAnswer. ClientNumber and
            # PlayerIndex are the room-scoped slot (both >= 0 -> grant). This stops the
            # 0x43 poll and moves the client into the arena (handler FUN_004f88f0).
            # GUARD (RE FUN_004f88f0): handler asserts ClientID<0 on entry - a 2nd 201
            # while already granted crashes the client. Grant once per entry.
            if s.client_granted:
                log('POST-AUTH', 'JoinToGameAnswer 201 already granted this entry - suppressing duplicate')
            else:
                s.client_granted = True
                send_rel(s, build_join_game_answer_201(s.client_number, s.player_index),
                         f'<- JoinToGameAnswer 201 (ClientNumber={s.client_number} '
                         f'PlayerIndex={s.player_index} -> GRANT)', to=5.0)
            # -- PLAYER-OBJECT LAYER (v184) ---------------------------------------
            # Now that the local player is granted, stand up the remote-player view:
            #   1. msg 62 -> tell the newcomer about every peer already in the room
            #      (builds a REMOTE_PLAYER object for each - handler FUN_004fa5f0).
            #   2. msg 62 -> tell those peers about the newcomer (live join).
            # Both 62 calls self-gate: no peers -> nothing sent, so a lone player's
            # entry is byte-identical to the known-good v182 path.
            # Side/camp (msg 63) is NOT sent here: nation is still None ("In Menu")
            # until the client picks a side, which drives handle_team_select -> 63.
            # msg 96 (ScoreTable) is DEFERRED - v183 sent it unconditionally here and
            # it crashed arena-join (messages08.log): FUN_004f53b0 frees+reallocates
            # the host-side score-table object mid-entry, before the client's world is
            # stood up, wedging it (3s stall -> WinError 10054). Seed the board after
            # full world-load, not during the grant.
            def _stand_up_player_objects(_s=s):
                push_player_roster_62(_s, reason='(on enter)')
                broadcast_player_join_62(_s, reason='(on enter)')
            threading.Thread(target=_stand_up_player_objects, daemon=True).start()
            # Do NOT echo: echoing type=0x82/sub=0xc8 causes FA.exe "Unknown Type 200"
            return

        # -- WRAPPED VNET::SendEnterToGame -----------------------------------------
        # Outer packet: bc=0, type=RETRY_COUNTER, cmd=0, sub=INNER_BC
        # Inner at pl[4:]: [inner_bc=0x02][inner_type=0x82][0x00][0x00][inner_sub=0xc8]...
        # BUG HISTORY: was inside sub==0x00 && len<=16 gate -> IMPOSSIBLE to trigger.
        #   pl[4]=inner_bc=0x02 != 0x00   AND   len(pl)=48 > 16.
        # FIX: check here with only pl[5]==0x82 and pl[8]==0xc8, ANY outer sub.
        if len(pl) >= 17 and pl[5] == 0x82 and pl[8] == 0xc8:
            pname_raw = pl[16:48] if len(pl) >= 48 else pl[16:]
            pname = pname_raw.split(b'\x00')[0].decode('ascii', 'replace').strip()
            game_idx = int.from_bytes(pl[9:13], 'little') if len(pl) >= 13 else 0
            if pname and s.current_room:
                existing = [p for p,_ in db_get_pilots_in_room(s.current_room)]
                if pname not in existing:
                    db_room_join(s.current_room, pname, s.account or '')
                log('POST-AUTH', f'VNET::SendEnterToGame (WRAPPED) inner_bc=0x{sub:02x} GameIndex=0x{game_idx:08x} pilot="{pname}" room={s.current_room}')
            else:
                log('POST-AUTH', f'VNET::SendEnterToGame (WRAPPED) inner_bc=0x{sub:02x} GameIndex=0x{game_idx:08x} (no room)')
            s.entered_game = True
            log('POST-AUTH', 'GAME MODE (wrapped VNET) - stopping 0x43, not echoing')
            return

        # -- SCAN-INNER PACKET DETECTION ------------------------------------------
        # FA.exe wraps APPSPACE sub-commands in type-scan outer packets:
        #   outer: bc=0, type=RETRY_COUNTER, cmd=0, sub=0x00
        #   inner at pl[4:]: inner[1]=type, inner[3]=cmd_lo, inner[4]=sub
        # These fire every 1s between compound 0x43 retries (every ~13s).
        if sub == 0x00 and len(pl) >= 9 and len(pl) <= 16:
            inner1 = pl[5] if len(pl) > 5 else 0   # inner type byte
            inner3 = pl[7] if len(pl) > 7 else 0   # inner cmd low byte
            inner4 = pl[8] if len(pl) > 8 else 0   # inner sub

            # Inner type=0x52 (pilot/squad status): accept silently - echoing causes loops
            if inner1 == 0x52:
                log('POST-AUTH', f'scan-inner 0x52/0x{inner4:02x} - accepted silently')
                return

            # Inner sub=0xd2: pre-room signal retry via type-scan -> echo it
            if inner1 == 0x12 and inner4 == 0xd2 and not s.entered_game:
                log('POST-AUTH','scan-inner sub=0xd2 -> echo inner')
                threading.Thread(target=lambda: send_rel(s, build_appspace_pkt(bytes([0xd2])),
                                 '<- scan-inner echo 0xd2', to=3.0), daemon=True).start()
                return

            # (VNET wrapped check moved OUT of this block - was dead code here
            #  because inner bc=0x02 makes outer sub=0x02 != 0x00, AND len=48 > 16)

            # Inner APPSPACE sub=0x43: type-scan room confirm poll
            if inner1 == 0x12 and inner4 == 0x43:
                now = time.time()
                if now - s.last_43_ts >= 0.5:
                    s.last_43_ts = now
                    _maybe_grant_create_entry(s)   # creator's post-create 0x43 poll -> 201 GRANT
                    room_slot = getattr(s,'room_slot',0)
                    rooms = db_get_open_rooms()
                    if rooms and (s.current_room or room_slot):
                        rid   = s.current_room or rooms[0][0]
                        pcount= db_room_player_count(rid)
                        slot  = room_slot or (rid & 0xFF)
                        rd = bytes([0x43,slot,0,0,0,pcount,0x01,0,0,0,0,0,0,0,0,0,0])
                        log('POST-AUTH',f'scan-inner sub=0x43 -> room confirm slot=0x{slot:02x} players={pcount}')
                        resp = build_appspace_pkt(rd)
                        threading.Thread(target=lambda:send_rel(s,resp,'<- scan-inner 0x43',to=3.0),daemon=True).start()
                    else:
                        log('POST-AUTH','scan-inner sub=0x43 -> no room yet')
                else:
                    log('POST-AUTH','scan-inner sub=0x43 -> rate-limited')
                return  # never echo these

            # Inner vcncExitAppSpace (inner type=0x40, inner cmd=5)
            if inner1 == 0x40 and inner3 == 0x05:
                log('POST-AUTH','scan-inner vcncExitAppSpace -> exit reply')
                pl2=bytearray(80); pl2[0]=4; pl2[3]=0x64
                if not send_rel(s,bytes(pl2),'exit appspace reply (scan)'):
                    s.closing=True
                    with sl: sadrs.pop(s.addr,None); sids.pop(s.sid,None)
                return

        # Messages that must NEVER be echoed. Two kinds:
        #  - 0x20 (msg 32): no inbound dispatch handler -> echo logs "Unknown Type 32".
        #  - 0x03 (msg 3): NET::OBJECT delete NOTIFY (client -> server "I deleted object
        #    N", e.g. `out 3'3` [03 00 80] right after the back-button teardown's
        #    "del CLIENT Me 0"). Msg 3 DOES have an inbound handler - "Server require
        #    delete object %i" - so echoing it back commands the CLIENT to delete a
        #    bogus object id and crashes the engine: bounds error
        #    ARR<NET::OBJECT*,2048>[29696] (messages01.log, the post-leave crash).
        # In-game telemetry (flight state etc.) is client->server only and has NO inbound
        # dispatch handler; echoing it makes FA log "NET::MESSAGE with Unknown Type N" and
        # drop the link. messages16.log: the client built TRN02, spawned, took off, then
        # died the instant the server echoed 83/84/24 back. 0x18=24, 0x53=83, 0x54=84.
        NO_ECHO_SUBS = {0x20, 0x03, 0x45, 0x18, 0x53, 0x54, 0x4d, 0x21, 0x0e, 0x19}  # 0x4d=msg77 plane-preload counts (echo -> index>=0 crash); 0x21=msg33 bail/eject report (echo of its 0xFFFF object index -> ARR<NET::OBJECT*,2048>[65535] bounds-error CTD, same class as 0x03); 0x0e=msg14 Reassign (v204: client->server object-owner reassign on respawn; FA has NO inbound in-game handler at 0xcbc1c8 -> an echo logs 'Unsupported message 14' and corrupts the object list. The client's own respawn CreateObject already re-binds the object on peers, so the reassign is redundant for us -> swallow.); 0x19=msg25 ace/rank/score state report (v220: client->server, fire-and-forget; echoing it back makes the client re-ingest its own report as authoritative and re-evaluate ace/rank against garbage/stale stats at a team-change spawn -> bogus 'new Ace Status'/'new Rank' announcements - Test2 log messages46. Consume, never echo.)
        # v222: the same message can arrive with its id in the TYPE byte and sub=0x00, which the
        # sub-byte check above cannot see. msg 33 (0x21) SCORE-EVENT does exactly that
        # ('cmd=0 type=0x21 sub=0x00 -> echo' in run 104546), so it was being blind-echoed despite
        # 0x21 already sitting in NO_ECHO_SUBS. Guard the TYPE byte too.
        NO_ECHO_TYPES = {0x21}
        if sub in NO_ECHO_SUBS:
            log('POST-AUTH', f'cmd=0 sub=0x{sub:02x} (notify, must not echo) -> swallow')
            return
        if TRIM_RELIABLE_ECHOES and sub in TRIM_ECHO_SUBS:
            log('POST-AUTH', f'cmd=0 sub=0x{sub:02x} (TRIM_RELIABLE_ECHOES) -> swallow, no echo')
            return
        if sub == 0x3a and SEND_EXIT_UNRELIABLE and getattr(s,'_awaiting_reattach',False) and not s.entered_game:
            # Exit-context hangar plane-list: echo UNRELIABLY (no reliable-seq cost). Empty hangar
            # => client re-requests 0x3a => we re-echo. Normal hangar-entry 0x3a still reliable below.
            log('POST-AUTH', 'cmd=0 sub=0x3a (exit hangar list) -> echo UNRELIABLE')
            send_unrel(s, stored, 'echo 0x3a (exit, UNREL)')
            return

        # -- Per-side CATALOG FILTER (PLANE_FILTER_VIA_CATALOG): trim the echoed 0x3a plane
        # list to the player's current side so each nation sees only its own aircraft, while
        # the GAME_DEF leaves every plane flyable (byte0=0x1f) so side-changes stay light.
        # UPLOAD 0x3a payload = [bc][T][00][00][0x3a][plane_id ...] (flat ONE byte per id);
        # appspace Size = bc*16 + (T>>4) covers the 0x3a sub byte + the ids. The client's
        # DOWNLOAD decoder reads (Size-1)/3 records of 3 BYTES [planeID][ushort], so we MUST
        # re-encode the kept ids as 3-byte records (not 1-byte) - otherwise GE's 26 ids echo
        # as Size=27 -> (27-1)/3 = 8 garbage records, dropping the tail bombers. Reframed via
        # build_ingame_pkt (Size == byte count). Only filters when ON A SIDE (0..4) and the
        # upload carries more than that side's planes; never emits EMPTY (would re-trip the
        # leave/teardown), falling through to verbatim.
        # v237: the client asks for the plane catalog (0x3a) whenever it opens the HQ / hangar
        # screen - which is EXACTLY when the HQ SCORES screen becomes readable. Our career state was
        # only ever pushed from the PLANE-SPAWN path, so looking at HQ -> SCORES without flying first
        # meant nothing had ever been sent and every row read 0. That is precisely why the v236 probe
        # came back "all 0": neither test run contained a single plane spawn (CONFIRM5 = 0), so msg 25
        # never went on the wire. Push the career state whenever the HQ screen opens (debounced).
        if sub == 0x3a and s.entered_game and SEND_CAREER_ON_HQ:
            _now = time.time()
            if _now - getattr(s, '_career_push_at', 0.0) > CAREER_PUSH_DEBOUNCE_S:
                s._career_push_at = _now
                log('CAREER', f'{s.current_pilot} opened the HQ screen (0x3a catalog) '
                              f'-> pushing rank/aces + stat block')
                push_career_stats(s, reason='(HQ screen opened)')

        if sub == 0x3a and PLANE_FILTER_VIA_CATALOG and s.nation is not None and 0 <= s.nation < 5:
            size = pl[0] * 16 + (pl[1] >> 4)
            if 1 <= size and 4 + size <= len(pl):
                ids = list(pl[5:4 + size])
                sc = _session_slot_camp(s)
                kept = [i for i in ids if sc.get(i, 0) == s.nation]
                if kept and len(kept) != len(ids):
                    rec = b''.join(struct.pack('<BH', i & 0xff, CATALOG_RECORD_USHORT & 0xffff) for i in kept)
                    fpkt = build_ingame_pkt(bytes([0x3a]) + rec)
                    log('POST-AUTH', f'cmd=0 sub=0x3a -> side {s.nation} catalog filtered {len(ids)}->{len(kept)} (3-byte recs, {1 + 3 * len(kept)}B)')
                    threading.Thread(target=lambda p=fpkt: send_reply(s, p, 'echo 0x3a (side-filtered, 3B)', to=5.0), daemon=True).start()
                    return

        # Echo-by-default for everything else (lobby AND in-game). The session that
        # reached flight (messages16) echoed in-game build/spawn messages; a blanket
        # in-game swallow instead FROZE the world build at ~97% (messages20) - the client
        # waits for replies to some of them (e.g. the 0x3a plane list, compound 0x4d).
        # Only genuine fire-and-forget crashers are suppressed via NO_ECHO_SUBS above; if
        # a NEW type crashes on echo with "NET::MESSAGE Unknown Type N", add 0xN there.
        # msg 4 (client's OWN object state) must NEVER be echoed. The client's msg-4 RECEIVE
        # path rejects an echoed msg-4 as 'Unsupported message 4' and CORRUPTS its object list,
        # so the next spawn's ServerConfirm is refused ('Confirm object N not found in list ->
        # send delete') and the fresh plane is deleted -> dead engine / teardown. The normal
        # spawn out-4 (type=0x12) is ServerConfirmed earlier; a BAIL-OUT sends the parachute's
        # out-4 as type=0xf2 sub=0x04, which lands here - swallow it, never echo. (messages04:
        # bail -> 'in 4'15' -> 'Unsupported message 4' -> respawn 260 'not found in list'.)
        if sub == 0x04:
            # msg-4 is the client's OWN object state - NEVER echo it (an echoed msg-4 is rejected as
            # 'Unsupported message 4' and corrupts the object list). The plane spawn out-4 (type=0x12)
            # is ServerConfirmed earlier. A BAIL-OUT sends the PARACHUTE's out-4 as type=0xf2 sub=0x04:
            # the client allocates a fresh object Number for the parachute, so the server MUST consume
            # one too - else its global Number counter runs one BEHIND the client's and the next
            # respawn's ServerConfirm carries a stale Number -> the client can't match it ('Confirm
            # object 259 not found in list -> send delete') and deletes the fresh plane (dead engine,
            # teardown). Consume a Number to stay in lock-step; send NO confirm and do NOT advance the
            # spawn ident (the parachute is not a ServerConfirmed spawn), and never echo.
            _pn = next_obj_number()
            # v198: the client registers the parachute under the NEXT ident too - resync the
            # fallback ident counter from the parachute's own out-4 ident field (pl[5:7]) so the
            # counter path can never repeat v197's stale-ident confirm ('Confirm object 258 not
            # found in list, send delete' -> fresh plane deleted, dead engine after respawn).
            _pi = struct.unpack_from('<H', pl, 5)[0] if len(pl) >= 7 else None
            if _pi is not None:
                s.spawn_ident_next = _pi + 1
            log('POST-AUTH', f'msg-4 (type=0x{tb:02x}) parachute/bail object -> Number {_pn} '
                             f'ident={_pi}')
            # *** v248: THE PARACHUTER IS A SECOND OBJECT - CONFIRM IT AND CREATE IT ON PEERS. ***
            # After a bail there are TWO entities (the user's hint; the RE agrees - FUN_004f26b0
            # case 2 is literally "Create NetParachuter"):
            #     the PLANE      - pilotless, keeps the aircraft-type tag, flies on until it crashes
            #     the PARACHUTER - carries the PILOT's name and rank (its record points at the
            #                      plane's object number, which resolves the score object)
            # We were doing NEITHER. We consumed this msg-4 without confirming it, so the bailing
            # client had nothing to transmit (that is the static 2-second keepalive we saw - a client
            # waiting on a confirm that never came, not "stale telemetry"), and we never sent a
            # create-object type 2, so peers had nothing to render. "Create NetParachuter" appears in
            # NEITHER client's log, ever.
            #
            # *** CRITICAL, and almost certainly what broke v197: DO NOT touch my_obj_number,
            # obj_confirmed or flying here. *** A normal spawn-confirm reassigns all three. Doing
            # that for the parachute would make the server believe the player's PLANE *is* the
            # parachute - and the real plane's later delete would then land on an object nobody owns
            # ("Confirm object 258 not found in list, send delete" -> the fresh plane got deleted).
            # The parachuter gets its OWN slot.
            if SEND_PARACHUTER and s.entered_game and s.my_obj_number is not None:
                s.para_obj_number = _pn
                s.para_body = bytes(pl[7:7 + PARACHUTER_HEADER_SIZE])
                log('PARA', f'{s.current_pilot} BAILED OUT -> parachuter is object 0x{_pn:04x} '
                            f'(plane 0x{s.my_obj_number:04x} keeps flying). '
                            f'client body={hx(s.para_body)} ({len(s.para_body)}B) '
                            f'| confirm={PARA_SEND_CONFIRM} create={PARA_SEND_CREATE}')
                # v252: these two are SEPARATELY switchable so the next CTD can be bisected instead of
                # guessed at. Three attempts have failed and we still do not know WHICH of them the
                # client dies on.
                if PARA_SEND_CONFIRM:
                    threading.Thread(target=lambda nn=_pn, ii=_pi: send_reply(
                        s, build_server_confirm_5(nn, ii),
                        f'<- ServerConfirm 5 (PARACHUTER Number={nn} ident={ii})'), daemon=True).start()
                if PARA_SEND_CREATE:
                    for _peer in get_sessions_in_room(s.current_room):
                        if _peer is not s and getattr(_peer, 'flying', False):
                            threading.Thread(target=send_parachuter_create_for,
                                             args=(s, _peer), daemon=True).start()
                    # v256: THE REAL PARACHUTER LIFECYCLE (from the 2009 ground truth).
                    # A real parachuter is NOT positioned by network telemetry. The 2009 client log
                    # shows a create, a local model load, then NOTHING on the wire naming that object
                    # until the SERVER sends a type-3 "Server require delete object N" when the canopy
                    # lands - typically 5-21 s later, scaling with the bail altitude. The client
                    # free-falls the canopy LOCALLY the whole time. Feeding it plane telemetry was
                    # exactly wrong: the client couldn't map a type-7 packet to a parachuter object
                    # and logged "Get coord for missing object 0" (v255). So: NO telemetry, and end
                    # the canopy with a clean server delete so the client removes it as bsr=1 (server-
                    # required) instead of culling it as a stale/disconnected object (bsr=0) at ~28 s.
                    if PARA_SERVER_DELETE:
                        def _para_land(_s=s, _pn2=_pn, _room=s.current_room):
                            time.sleep(PARA_DESCENT_SECONDS)
                            if getattr(_s, 'para_obj_number', None) != _pn2:
                                return                    # already removed / recycled
                            for _peer in get_sessions_in_room(_room):
                                if _peer is _s or not getattr(_peer, 'flying', False):
                                    continue
                                try:
                                    send_rel(_peer, build_delete_object_3(onumber=_pn2),
                                             f'<- Server require delete PARACHUTER 0x{_pn2:04x} '
                                             f'({_s.current_pilot} landed)', to=3.0)
                                except Exception:
                                    pass
                            _s.para_obj_number = None
                            log('PARA', f'parachuter 0x{_pn2:04x} ({_s.current_pilot}) landed after '
                                        f'{PARA_DESCENT_SECONDS}s -> server delete sent')
                        threading.Thread(target=_para_land, daemon=True).start()
            else:
                log('POST-AUTH', 'parachute msg-4 consumed, not confirmed (SEND_PARACHUTER off or '
                                 'no plane) - counters resynced only')
            # *** v247: the bail does not CREATE the attribution - the damage report already did.
            # It just tells us the pilot is out, so the plane's eventual crash is a kill, however
            # long it takes to fall. Mark the latch so the log explains itself.
            _pk = PENDING_KILL.get(getattr(s, 'my_obj_number', None))
            if _pk:
                _pk['why'] = 'bail'
                log('BAIL', f'{s.current_pilot} BAILED OUT of obj 0x{s.my_obj_number:04x} - the kill '
                            f'is already held for obj 0x{_pk["killer"]:04x} and will be credited when '
                            f'the empty plane comes down, however long that takes')
            else:
                log('BAIL', f'{s.current_pilot} bailed out with no damage on record - no kill to '
                            f'credit')
            return
        # Generic fall-through echo. HARD GUARD: never echo a type=0x00 reliable message. The
        # client's Conductor cannot parse a reliable msg with type byte 0 ("Server sent client
        # something it doesn't understand (-102)") and stops ACKing the moment it receives one,
        # killing the whole reliable channel (observed: a wrapped msg-77 `00 00 00 00 00 12 00 00
        # 4d` parsed here as tb=0x00 sub=0x00, got echoed as reliable type=0x00 seq=44, and every
        # server send from that point timed out -> "waiting for server response" -> empty plane
        # list). Wrapped forms whose real inner type sits at pl[8] must not be echoed verbatim;
        # if we didn't recognise it above, swallowing is strictly safer than emitting a type-0
        # reliable packet. (0x4d=msg77 plane-preload is already a NO_ECHO sub in its direct form.)
        if tb == 0x00:
            _inner = pl[8] if len(pl) > 8 else 0
            log('POST-AUTH', f'cmd=0 type=0x00 (wrapped, inner=0x{_inner:02x}) -> swallow '
                             f'(never echo a type-0 reliable msg; would -102 the client)')
            return
        # v222: NO-ECHO BY *TYPE* BYTE. NO_ECHO_SUBS above tests pl[4] (the sub byte), but some
        # client->server reports carry their message id in the TYPE byte instead, with sub=0x00 -
        # so they slipped past that guard and got blind-echoed. Observed (run 104546):
        #   'cmd=0 type=0x21 sub=0x00 -> echo'  = msg 33 (0x21) SCORE-EVENT, the client's own
        #   kill/death score report ([00210000|00420000]+18000200). It is a fire-and-forget REPORT
        #   to be CONSUMED, never reflected: echoing it feeds the client back its own event (the
        #   same class of bug as msg 25 in v220, and 0x21 was already in NO_ECHO_SUBS for exactly
        #   this reason - the sub-byte check just never matched it).
        # The server does its own authoritative scoring from the msg-3 delete-notify
        # (score_on_death) and states the result with msg 88 / msg 33, so nothing is lost.
        # v226: msg 33 (0x21) is the EXIT-EVENT, and it must be RELAYED to the other players.
        # The client's own sender is Msn_Exit.cpp FUN_0045d930: it emits DAT_00c82350 = 0x21 with
        #   [0x21][AddData][Number u16][(MissExitCode << 4) | ScoreEvent][... nHits + 8B hit records]
        # i.e. the dying plane reports WHO HIT IT AND BY HOW MUCH (each record carries a damage
        # share). That hits list IS the game's kill-attribution mechanism, and the receiving
        # handler (0x004f9ae0) resolves the score object, ticks the stats and prints the events.
        #
        # v222 added 0x21 to NO_ECHO_TYPES to stop it being blind-ECHOED back to the SENDER (that
        # echo fed the client its own 0xFFFF object index -> ARR<NET::OBJECT*,2048>[65535]
        # bounds-error CTD). That was right, but "don't echo to the sender" is NOT "don't relay to
        # the peers" - and we were dropping it entirely. So NOBODY ever ran their stat pipeline,
        # which is exactly why kills, deaths AND planes-lost all stayed 0 in the HUD / session
        # statistics. Relay it verbatim to everyone else in the room (never back to the sender).
        if tb == MSG_SCORE_EVENT_33:
            if RELAY_EXIT_EVENT_33 and getattr(s, 'current_room', None) is not None:
                peers = [p for p in get_sessions_in_room(s.current_room) if p is not s]
                log('EXIT33', f'ExitEvent from {s.current_pilot} ({len(stored)}B: '
                              f'{stored.hex()}) -> relay to {len(peers)} peer(s)')
                for _p in peers:
                    threading.Thread(
                        target=lambda _t=_p: send_rel(_t, stored,
                                f'<- ExitEvent 33 relay (from {s.current_pilot})', to=3.0),
                        daemon=True).start()
            else:
                log('EXIT33', f'ExitEvent from {s.current_pilot} ({len(stored)}B: '
                              f'{stored.hex()}) -> not relayed')
            return   # never echo back to the sender (0xFFFF object index -> CTD)
        if tb in NO_ECHO_TYPES:
            log('POST-AUTH', f'cmd=0 type=0x{tb:02x} (client report, must not echo) -> swallow')
            return
        log('POST-AUTH',f'cmd=0 type=0x{tb:02x} sub=0x{sub:02x} -> echo')
        threading.Thread(target=lambda:send_reply(s,stored,f'echo type=0x{tb:02x}',to=5.0),daemon=True).start()
        return

    if cmd == 0x0222:
        if len(pl) >= 15:
            inner_sub = pl[8] if len(pl)>8 else 0
            if inner_sub == 0xe4:
                sb14 = pl[14] if len(pl)>14 else 0
                if sb14 < 0x20: pname = pl[15:].split(b'\x00')[0].decode('ascii','replace')
                else:             pname = pl[14:].split(b'\x00')[0].decode('ascii','replace')
                slot = db_get_pilot_slot(s.account, pname) or 0
                s.current_pilot=pname; s.current_slot=slot
        threading.Thread(target=lambda:send_rel(s,stored,'<- echo cmd=546',to=5.0),daemon=True).start(); return

    if cmd==3:
        time.sleep(0.05)
        rec=bytearray(15); rec[0]=2; rec[2]=0x20; rec[11]=0xD3; rec[14]=s.nsq()
        sock.sendto(bytes(rec),s.addr)
        time.sleep(0.05); sock.sendto(build_data(106,s.nsq()),s.addr)
    elif cmd==2:
        pl2=bytearray(80); pl2[0]=4; pl2[3]=0x64; send_rel(s,bytes(pl2),'disconnect reply')
    elif cmd==5:
        log('POST-AUTH','vcncExitAppSpace (cmd=5)')
        pl2=bytearray(80); pl2[0]=4; pl2[3]=0x64
        if not send_rel(s,bytes(pl2),'exit appspace reply'):
            s.closing=True   # reply timed out -> client gone, stop heartbeat
            with sl: sadrs.pop(s.addr,None); sids.pop(s.sid,None)
    elif cmd==512:
        pilots=db_get_pilots(s.account) if s.account else []
        resp=build_e1_pilot_list(pilots)
        threading.Thread(target=lambda:send_rel(s,resp,'<- pilot list 512',to=5.0),daemon=True).start()
    elif cmd==530: pass
    else:
        if len(pl) >= 9: handle_compound(s, cmd, pl)

# --- Packet receiver ----------------------------------------------------------

def _match_session_by_ip(addr):
    """v214: find a session whose IP matches addr[0] even if the PORT differs. The client can
    move its source port mid-session - e.g. IOCInitializeTimeSynchronization's failure path rebinds
    to a 'unique port' (FUN_100032b2) and retries, and NAT/rebind can also shift it. When that
    happens the time-sync pings arrive from a new (ip, port) that isn't in sadrs, so the old code
    silently dropped them (get_s -> None -> return) and the client got no reply -> sync FAIL (d660=5)
    -> vcncGetTimeState -2 -> freeze. Matching by IP lets us still answer."""
    with sl:
        for a, sess in sadrs.items():
            if a[0] == addr[0]:
                return sess
    return None

def on_pkt(data, addr):
    sz=len(data)
    # v214 DIAGNOSTIC: log EVERY raw inbound packet's addr + head, so we can SEE time-sync pings
    # that arrive from an unexpected port (the old code dropped unknown-addr packets silently).
    if RAW_RX_LOG:
        _known = get_s(addr) is not None
        log('RX/RAW', f'{addr[0]}:{addr[1]} sz={sz} head={data[:16].hex()} '
                      f'{"known" if _known else "UNKNOWN-ADDR"}')
    s=get_s(addr)
    # v214: time-sync ping from a moved port -> match by IP and ADOPT the new addr into the session,
    # so subsequent packets (and our replies) stay aligned. Only for the 12-byte TIME ping, which is
    # safe to answer regardless of the reliable-channel state.
    if s is None and sz==12 and (data[2]&0x80):
        s = _match_session_by_ip(addr)
        if s is not None:
            _old = s.addr
            with sl:
                sadrs.pop(_old, None); sadrs[addr] = s; s.addr = addr
            log('RX/PORTMOVE', f'time-ping from {addr[0]}:{addr[1]} adopted into session '
                               f'(was {_old[1]}) ({getattr(s,"current_pilot","?")})')
    if not s: return
    # v215: capture the connection id the client stamps in its own packets (wire bytes 0-1) so our
    # STATUS request can carry the value the client expects. The 12-byte TIME pings carry it (e.g.
    # 001e...); grab it once. Falls back to a beacon-style default in build_status_request if unseen.
    if s._status_connid is None and sz >= 2 and (data[2] & 0x80) and sz == 12:
        s._status_connid = struct.unpack_from('>H', data, 0)[0]
        log('STATUS/CONNID', f'captured connid=0x{s._status_connid:04x} for STATUS packets '
                             f'({getattr(s,"current_pilot","?")})')
    if sz==12 and (data[2]&0x80):
        # 12-byte two-way TIME ping (client FUN_100090e4: flag 0x40 -> wire byte[2]=0x80). In the
        # LOBBY this is the initial clock sync; IN-GAME (v213) it's the client's periodic RESYNC
        # (FUN_100091b7 drops to sync state 2 when its last time sample goes stale). We reply with a
        # fresh timestamp + echoed time-index so it re-baselines cleanly and measures round-trip
        # latency (HUD 'L:'). Logged per session-phase so we can confirm the resync loop is running.
        ti = struct.unpack_from('>H', data, 8)[0] if sz >= 10 else 0
        s._tping_n = getattr(s, '_tping_n', 0) + 1
        if getattr(s, 'entered_game', False):
            if (s._tping_n % 4) == 1:
                log('RX/TIMEPING', f'in-game RESYNC ping #{s._tping_n} ti={ti} '
                                   f'-> reply A_ms={tsync_ms(s)} ({getattr(s,"current_pilot","?")})')
        sock.sendto(build_time_reply(data,sess=s),addr); return
    if sz>=8:
        dw=struct.unpack_from('>I',data,4)[0]; pt=(dw>>29)&7
        if pt==1:
            s.rx+=1; cs=data[3] if sz>3 else 0
            pl=data[8:] if sz>8 else b''
            # Reconstruct the client's FULL 9-bit (mod-512) reliable seq. vcncNet's reliable
            # logic runs mod 512 (the 0x200 modulus in the ACK processor FUN_10006b0e) and its
            # send-queue base does NOT wrap at 256 - but the wire seq byte (data[3]) is only 8-bit
            # and wraps 255->0. Below 256 the two agree, so ACKing the 8-bit value worked; but on
            # the 256th reliable msg of a session the client's base is 256 while data[3]=0, so an
            # ACK built from the 8-bit value carries the wrong next_exp, the client's cumulative
            # removal never clears that packet, and it retransmits it forever -> freeze (observed
            # exactly: cs wraps 255->0, then cs=0 DUP#1..n every 5s). We track the 255->0 wraps
            # to rebuild cs9 in 0..511 and ACK in that space so the wrap stays aligned.
            _prev_cs = getattr(s, '_rel_rx_last_cs', None)
            if _prev_cs is not None and _prev_cs >= 0xC0 and cs < 0x40:      # 255->0 style wrap
                s._rel_rx_hi = (getattr(s, '_rel_rx_hi', 0) ^ 1)
            elif _prev_cs is not None and _prev_cs < 0x40 and cs >= 0xC0:    # rare backward wrap
                s._rel_rx_hi = (getattr(s, '_rel_rx_hi', 0) ^ 1)
            cs9 = ((getattr(s, '_rel_rx_hi', 0) & 1) << 8) | cs
            # - reliable-RX diagnostics -
            _now=time.time()
            s._rel_rx_count=getattr(s,'_rel_rx_count',0)+1
            _dup=(cs==getattr(s,'_rel_rx_last_cs',None))
            if _dup: s._rel_rx_dups=getattr(s,'_rel_rx_dups',0)+1
            s._rel_rx_last_cs=cs; s._rel_rx_time=_now
            if getattr(s,'_stall_warned',False):
                s._stall_warned=False
                s._rec_dumped=False
                log('STALL-WATCH', f'{s.current_pilot}: reliable RX RESUMED (cs={cs})')
            time.sleep(0.01); sock.sendto(build_rel_ack(30,cs9),s.addr)
            cv=struct.unpack_from('>H',pl,2)[0] if len(pl)>=4 else 0
            if getattr(s,'entered_game',False):
                _dtag=f' DUP#{s._rel_rx_dups}(retransmit)' if _dup else ''
                log('RELRX', f'{s.current_pilot} cs={cs} d0=0x{data[0]:02x} cmd={cv} sz={sz}{_dtag}')
                _rec(s, 'C->S', 'RELRX',
                     f'cs={cs} cmd={cv} sz={sz}{_dtag} pl={binascii.hexlify(pl[:24]).decode()}')
            if cv==4:
                s.session_id=pl[4:6] if len(pl)>=6 else b'\x00\x01'
                if not getattr(s,'_login_started',False):
                    s._login_started=True
                    threading.Thread(target=login,args=(s,),daemon=True).start()
            elif s.auth_done:
                with s._lock: s.post_auth_cmds.append((cv,pl))
            return
        if pt==0 and sz==8:
            aseq=(dw>>20)&0x1FF
            with s._lock: is_ack=aseq in s._evts
            if is_ack:
                s._ack_in_count=getattr(s,'_ack_in_count',0)+1
                s.sig(aseq); return
            s.closing=True
            if s.current_pilot:
                broadcast_player_leave(s.current_pilot, exclude_sess=s)
                broadcast_system(f'[{s.current_pilot}] has left')
                db_room_leave(s.current_pilot)
            _free_start_place(s)   # release start-place slot on disconnect
            with sl: sadrs.pop(addr,None); sids.pop(s.sid,None); return
        # CAPTURE (diagnostic): in-game packets that are neither reliable-data (pt=1)
        # nor ack/disconnect (pt=0) - the UNRELIABLE flight-telemetry stream a flying
        # client streams (currently dropped). Rate-limited hex sample of the payload
        # after the 8-byte VCNC header, so the entity/position format can be decoded
        # and relayed to other players in the room.
        if getattr(s,'entered_game',False):
            s._unrel_rx_time=time.time()
            # Flight recorder: keep the trailing telemetry so a stall dump shows the last
            # known aircraft state. Decode tick+Number (the trend fields) so a freeze dump
            # reveals whether the sim was degrading (tick stalling / Number changing) or the
            # client froze instantly from a clean stream.
            _td = _rec_decode_telem(data)
            _rec(s, 'C->S', 'UNREL',
                 f'sz={sz} {_td} hdr={hx(data[:8])} pl={hx(data[8:32])}')
        if CAPTURE_UNREL and s.entered_game:
            _now=time.time()
            if _now - getattr(s,'_unrel_ts',0.0) >= 0.5:
                s._unrel_ts=_now
                log('RX/UNREL', f'{getattr(s,"current_pilot",None)} sz={sz} hdr={hx(data[:8])} pl={hx(data[8:])}')
        # RELAY the flying client's telemetry to other flying players in the same room.
        if RELAY_TELEMETRY and getattr(s,'flying',False) and s.current_room is not None:
            relay_telemetry(s, data)

# --- Web Server Bridge --------------------------------------------------------

def get_existing_ticket(account_name: str) -> tuple:
    """Rebuilds the binary .vr1 ticket from database hex values."""
    if TICKET_TEMPLATE is None: raise RuntimeError("No ticket template loaded")
        
    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute(
        "SELECT player_id, field_45, auth_block FROM accounts WHERE account_name=?", 
        (account_name,)
    ).fetchone()
    conn.close()
    
    if existing:
        pid_hex, f45_hex, ab_hex = existing
        ticket = bytearray(TICKET_TEMPLATE)
        ticket[TICKET_PID_OFF:TICKET_PID_OFF+4] = bytes.fromhex(pid_hex)
        ticket[TICKET_F45_OFF:TICKET_F45_OFF+4] = bytes.fromhex(f45_hex)
        ticket[TICKET_AB_OFF:TICKET_AB_OFF+16] = bytes.fromhex(ab_hex)
        
        acct_field = account_name.encode('ascii') + b'\x00' * (TICKET_ACCT_LEN - len(account_name))
        ticket[TICKET_ACCT_OFF:TICKET_ACCT_OFF+TICKET_ACCT_LEN] = acct_field
        
        return bytes(ticket), pid_hex
    raise ValueError(f"Account {account_name} not found in database.")

from web_server import start_web_server

def _stall_watch():
    """Background monitor for the reliable-channel stall. The failure signature seen in
    the field: a client keeps streaming UNRELIABLE telemetry while its RELIABLE channel
    goes silent (death-notify/respawn never arrive). Flag that transition once, with the
    channel state, so the next occurrence is captured instead of inferred."""
    while running:
        time.sleep(3.0)
        now=time.time()
        for s in get_all_sessions():
            if not getattr(s,'entered_game',False): continue
            r0=getattr(s,'_rel_rx_time',0.0)
            if r0<=0: continue
            rel_idle=now-r0; unrel_idle=now-getattr(s,'_unrel_rx_time',0.0)
            if rel_idle>=10.0 and unrel_idle<3.0 and not getattr(s,'_stall_warned',False):
                s._stall_warned=True
                with s._lock: pend=len(s._evts)
                log('STALL-WATCH', f'[warn] {s.current_pilot}: reliable RX idle {rel_idle:.1f}s but '
                                   f'unreliable active ({unrel_idle:.1f}s ago) - possible reliable '
                                   f'stall | last_cs={getattr(s,"_rel_rx_last_cs",None)} '
                                   f'rel_rx={getattr(s,"_rel_rx_count",0)} dups={getattr(s,"_rel_rx_dups",0)} '
                                   f'pending_tx={pend} acks_in={getattr(s,"_ack_in_count",0)}')
                if not getattr(s,'_rec_dumped',False):
                    s._rec_dumped=True
                    _p=_rec_dump(s, f'reliable stall (idle {rel_idle:.1f}s, last_cs='
                                    f'{getattr(s,"_rel_rx_last_cs",None)})')
                    if _p:
                        log('REC', f'flight recorder dumped -> {_p}')

# --- Main loop ----------------------------------------------------------------

log('SERVER',f'Fighter Ace LAN Server v279 on {HOST}:{PORT}')
_unpriced = [n for n in PLANE_ROSTER if n not in PLANE_VALUE_NAMES]
if _unpriced:
    log('PLANES', f'[warn] no point value for {len(_unpriced)} plane(s), falling back to the '
                  f'class default: {sorted(_unpriced)}')
log('PLANES', f'scoring: {len(PLANE_VALUE_NAMES)} plane values loaded; ranks '
              f'{RANK_NAMES[0]}..{RANK_NAMES[-1]} at {RANK_THRESHOLDS}')
if _unmatched:
    log('PLANES', f'[warn] BOMBER_PLANE_NAMES not found in PLANE_ROSTER (typo?): {sorted(_unmatched)}')
log('PLANES', f'aircraft class: {len(BOMBER_PLANE_IDS)} bombers / '
              f'{len(PLANE_ROSTER) - len(BOMBER_PLANE_IDS)} fighters of {len(PLANE_ROSTER)}')
# -- ONE-TIME DEBUG (remove later): decompress the stock arena templates FFA.gdf / TC.gdf
#    so their camps/side block can be diffed against what a created room stores. The
#    decompressor anchors on the 0x8a version byte, so each .gdf's "Custom Arena" label
#    prefix is skipped automatically. Read-only.
for _gdf in ('FFA', 'TC'):
    try:
        _p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'FA', 'NewArenas', f'{_gdf}.gdf')
        with open(_p, 'rb') as _f:
            _raw = _f.read()
        log('GDFDUMP', f'{_gdf}.gdf raw={len(_raw)}B (verbatim, NOT decompressed): {bytes(_raw).hex()}')
    except Exception as _e:
        log('GDFDUMP', f'{_gdf}.gdf dump failed: {_e}')
threading.Thread(target=console_handler, daemon=True).start()

# Start the separate web server and inject our local server variables into it
threading.Thread(
    target=start_web_server, 
    args=(DB_PATH, get_existing_ticket, generate_ticket, log, arena_settings_read,
          ARENA_TAIL_FIELDS, _falog.get_recent_logs),
    daemon=True
).start()

threading.Thread(target=_stall_watch, daemon=True).start()
threading.Thread(target=_resupply_poll_loop, daemon=True).start()  # v272: ground-speed-0 auto-resupply

_drop_ts=0.0

def _guarded(fn, data, addr):
    try:
        fn(data, addr)
    except Exception:
        logx('DISPATCH', f'{fn.__name__} failed addr={addr} sz={len(data)} '
                         f'hdr={hx(data[:16])}')

while running:
    try: data,addr=sock.recvfrom(65536)
    except socket.timeout: continue
    except KeyboardInterrupt: running=False; break
    except OSError as e:
        # WinError 10054 (WSAECONNRESET): a prior sendto() to a client that has quit made
        # Windows post a stale ICMP port-unreachable, surfaced here on the NEXT recvfrom and
        # DISCARDING no real datagram of ours. SIO_UDP_CONNRESET(False) above normally
        # suppresses it; if one still slips through it is benign. Do NOT spam it as ERROR
        # every heartbeat - rate-limit to one WARNING per 30s so a real error is still visible.
        _wr = getattr(e, 'winerror', None)
        if _wr == 10054 or getattr(e, 'errno', None) in (10054,):
            _now = time.time()
            if _now - globals().get('_connreset_ts', 0.0) > 30.0:
                globals()['_connreset_ts'] = _now
                log('RX/DROP', 'WSAECONNRESET (10054) from a departed client - benign, suppressed for 30s')
            continue
        log('ERROR', str(e)); continue
    except Exception as e: log('ERROR',str(e)); continue
    if not data: continue
    pt=data[0]; sz=len(data)
    if sz==912 and pt==0:
        threading.Thread(target=_guarded, args=(handle_syn, data, addr), daemon=True).start()
    elif sz==8 and data[2]==2: _guarded(on_pkt, data, addr)
    elif sz==8: _guarded(on_pkt, data, addr)
    elif pt==2: _guarded(on_pkt, data, addr)
    elif pt==0: _guarded(on_pkt, data, addr)
    else:
        # If a RELIABLE packet (control-dword pt==1) ever lands here it is being dropped
        # WITHOUT an ACK -> the client's reliable window wedges -> stall. Always log these,
        # un-rate-limited, so the next stall is caught at the routing layer.
        _cpt = ((struct.unpack_from('>I',data,4)[0])>>29)&7 if sz>=8 else -1
        if _cpt==1:
            log('RELDROP', f'[warn] reliable pkt NOT routed -> dropped/un-ACKed '
                           f'data0=0x{pt:02x} sz={sz} cs={data[3] if sz>3 else 0} {hx(data[:16])}')
        # CAPTURE: packet matched by no route above - a candidate UNRELIABLE in-game
        # telemetry datagram with an unexpected first byte. Rate-limited raw log only
        # (do NOT route to on_pkt: avoids misparsing telemetry as a reliable packet).
        elif CAPTURE_UNREL:
            _t=time.time()
            if _t-_drop_ts>=0.5:
                _drop_ts=_t
                log('RX/DROP', f'data0=0x{pt:02x} sz={sz} {hx(data[:96])}')