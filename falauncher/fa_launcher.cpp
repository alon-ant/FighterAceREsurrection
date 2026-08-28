// ============================================================================
//  FA Secure Launcher  (C++ / embedded WebBrowser control)
// ----------------------------------------------------------------------------
//  A single Win32 window hosting the built-in IE/MSHTML WebBrowser ActiveX
//  control (shdocvw / IWebBrowser2). Faithful port of fa_launcher.py:
//
//    1. Read settings from launcher.ini (server login URL, game dir, ...).
//    2. Show the server login page inside an embedded browser form.
//    3. When the page navigates to the ticket download (/download, which the
//       server serves as ticket_<pid>.vr1), cancel the browser's own download
//       and instead fetch the bytes with the control's session cookies,
//       writing DIRECTLY to <GameDir>\ticket.vr1. Extract <pid>.
//    4. Launch FA.exe /NET /Name:<pid> <LaunchArgs> and close.
//
//  Uses only Windows built-ins (ole32, oleaut32, shdocvw via COM, urlmon,
//  wininet, shell32). No SDK download, no WebView2 runtime.
//
// CHANGELOG
// 2026-08-05: launcher v2 - three independent fixes, individually revertible:
//   L-FIX-1 (TAB dead between username/password): the message loop dispatched
//     keystrokes straight to the main window, so the hosted control never saw
//     keyboard NAVIGATION keys (TAB/Shift+TAB, arrows in dropdowns, Ctrl+A...).
//     Standard MSHTML-hosting fix: hold the control's IOleInPlaceActiveObject
//     and offer every message to its TranslateAccelerator first; only messages
//     it returns S_FALSE for go through TranslateMessage/DispatchMessage.
//     Falsify by: TAB still not moving focus between the two login fields.
//     Revert by: delete g_ipao and the two lines in the message loop.
//   L-FIX-2 (remember last username): on any form submit from a page that has
//     a password field, the first text input's value is saved to lastuser.txt
//     next to the exe; on DocumentComplete of such a page, an EMPTY first text
//     input is prefilled with it and focus moves to the password field. Purely
//     DOM-side (mshtml.h), no server change, works with any login page markup
//     that has one text + one password input. The password is never stored.
//     Falsify by: second run of the launcher shows an empty username field.
//     Revert by: delete the L-FIX-2 blocks (helpers + 2 call sites).
//   L-FIX-3 (spaces in the game path): CreateProcess itself was fine with the
//     quoted path, but FA.exe (2002-era) parses its own command line with a
//     naive whitespace split, so "C:\Program Files (x86)\...\FA.exe" shifted
//     /NET and /Name: out of position and the game refused to start. Fix:
//     build the command line from the 8.3 short path (GetShortPathNameW) so it
//     contains NO spaces and NO quotes; pass lpApplicationName explicitly so
//     process resolution never depends on command-line parsing. Falls back to
//     the old quoted long path when the volume has 8.3 names disabled.
//     Falsify by: launch still failing from a path with spaces while the same
//     build launches fine from C:\games\FA.
//     Revert by: delete the exeForCmd block in LaunchGame.
// 2026-08-05: launcher v3 - L-FIX-4: game download + sharing via BitTorrent.
//     The launcher can now download FA42DeluxeEdition.iso with the bundled
//     aria2c.exe as the transfer engine: BitTorrent (the shipped .torrent,
//     ~100 public trackers + DHT) plus an optional plain-HTTP mirror passed as
//     an extra source (aria2 -T <torrent> <url>), with piece-hash verification
//     and automatic seeding back to other pilots (--seed-ratio=0.0).
//     Entry points: the /getgame command-line flag, or a yes/no prompt when the
//     configured fallback client exe is missing at startup. Progress renders as
//     an HTML page inside the existing browser control, updated from aria2's
//     JSON-RPC (127.0.0.1:<RpcPort>, random per-run secret) on a 2 s timer.
//     Login remains fully usable during a download (the progress page links to
//     it, and the poll only repaints while the browser sits on about:blank).
//     If a previous download (complete or partial) is present, the launcher
//     quietly resumes seeding/downloading in the background on every start
//     (SeedOnStart=1, --bt-seed-unverified for instant seeding). aria2's
//     lifetime is tied to the launcher: it is shut down via RPC when the game
//     launches or the window closes, unless SeedWhilePlaying=1.
//     New ini keys (all optional): TorrentFile, DownloadUrl, DownloadDir,
//     Aria2Exe, IsoName, RpcPort, SeedOnStart, SeedWhilePlaying.
//     Falsify by: /getgame not producing a growing <DownloadDir>\<IsoName>
//     with visible progress, or a completed ISO not uploading to a second peer.
//     Revert by: delete the L-FIX-4 sections (config keys + the aria2 block +
//     the 3 call sites in DownloadTicketAndLaunch / WndProc / wWinMain).
// 2026-08-05: launcher v3.1 - L-FIX-4b: make peers actually findable/connectable.
//     Field test showed 0 seeders seen with 2 expected. Causes and fixes:
//     * Random BT listen port made router port-forwarding impossible. Now a
//       FIXED, forwardable port range: --listen-port / --dht-listen-port =
//       BtPort..BtPort+9 (ini BtPort, default 6888; aria2 takes the first
//       free one in the range, so two instances on one PC also coexist).
//     * DHT bootstrap + LAN discovery were not configured: added an explicit
//       --dht-entry-point (dht.transmissionbt.com) and --bt-enable-lpd=true,
//       so same-LAN peers find each other even when the tracker hands both of
//       them the same public IP (hairpin NAT).
//     * Two launcher instances fought over RPC port 6811 (seen in the stage
//       log as interleaved runs + double T2): StartAria2 now probes
//       RpcPort..RpcPort+9 with a loopback bind test and takes the first free
//       port. Needs ws2_32 (added to the link line).
//     Also shipped seed.bat: a dedicated always-on seeder for the server
//     machine, run OUTSIDE the launcher lifecycle with a visible console (so
//     Windows Firewall shows its allow prompt). One port-forwarded seed makes
//     the whole swarm work for NATed pilots.
//     Falsify by: a downloader still showing 0 seeders while seed.bat runs on
//     a machine with TCP+UDP 6888 forwarded and firewall-allowed.
//     Revert by: delete the PortFree probe + the five new aria2 switches.
// 2026-08-05: launcher v3.2/v3.3 - L-FIX-5: install from the ISO + writable
//     game folder + persisted path. Revised per plan change: the disc's
//     installer (FA42DELUXE.exe) is NOT executed. Instead:
//     * The completed-download page's 'Install the game now' link mounts the
//       ISO (PowerShell Mount-DiskImage, no admin), asks the user for a target
//       folder with the modern common file dialog (IFileOpenDialog with
//       FOS_PICKFOLDERS; SHBrowseForFolder fallback), and copies the CONTENTS
//       of the disc's FIGHTER_ACE_4_2_DELUXE_EDITION folder there using
//       SHFileOperation - the native Explorer copy dialog provides progress
//       and pumps messages, so the launcher stays responsive.
//     * The copy inherits read-only attributes from the disc image, so the
//       whole target tree is then cleared of FILE_ATTRIBUTE_READONLY
//       in-process (no UAC - the user picked a folder they can write to).
//     * The chosen path is persisted as GameDir= in launcher.ini (first
//       active key replaced, else appended; BOM/comments/order preserved),
//       and applied to the running config, so the launcher launches the game
//       from it (still overridable by the server's X-Game-Client-Path).
//     * 'Fix folder permissions' re-runs just the read-only sweep on GameDir
//       (or a picked folder) - useful for hand-copied installs.
//     * Startup offers when the client exe is missing: no data -> download;
//       partial -> visible resume; complete ISO -> copy-install.
//     Ini: IsoGameFolder overrides the disc folder name if it ever changes.
//     v3.4 - L-FIX-5c: the picker selection is never used directly if it
//     already contains other files. Rules: selection named like the game
//     subfolder -> use as-is; selection empty (freshly created via 'Make New
//     Folder') -> use as-is; otherwise create <selection>\<InstallSubdir>
//     (ini InstallSubdir, default FA42) and install there. If the computed
//     target already exists WITH files, a reinstall/repair is confirmed
//     first. The target is created (and thereby write-tested) before the
//     ISO is even mounted.
//     Falsify by: picking C:\games (non-empty) and finding game files
//     directly in C:\games instead of C:\games\FA42.
//     v3.5 - L-FIX-5d: fully automated first-run journey. When a download the
//     launcher WATCHED finishing completes, the destination picker opens by
//     itself (one-shot; a pre-completed ISO at startup keeps using the
//     yes/no offer instead, so reseed-only runs get no surprise dialog).
//     After a successful copy: a desktop shortcut 'Fighter Ace 4.2.lnk' is
//     created pointing at the launcher (wearing FA.exe's icon when
//     available), one confirmation box summarizes what happened, and the
//     browser advances to the login page automatically. Seeding continues
//     in the background throughout.
//     Falsify by: a fresh /getgame run ending anywhere other than the login
//     page with a working desktop shortcut and GameDir= saved.
// 2026-08-05: launcher v3.6 - L-FIX-4c: seed while playing, ON by default.
//     Rather than orphaning a headless aria2c past the launcher's exit (which
//     would also stack duplicate instances across sessions via the port
//     probing), the launcher now HIDES after launching the game and stays
//     alive as the seeding supervisor: aria2 keeps seeding, upload is capped
//     live over RPC (aria2.changeGlobalOption max-overall-upload-limit, ini
//     PlayUploadLimit, default 512K, "0"=unlimited) so the pilot's ping is
//     protected, and a 3 s timer watches the FA.exe process handle. When the
//     game exits, the launcher stops aria2 cleanly and exits too - launcher
//     lifetime == session lifetime, zero orphan processes. SeedWhilePlaying=0
//     restores the old stop-at-launch behavior. WM_DESTROY now always stops
//     aria2 (the survive-launch exception is gone since we no longer exit).
//     Falsify by: aria2c.exe alive in Task Manager after the game closes, or
//     upload exceeding PlayUploadLimit while the game is running.
//     Revert by: set SeedWhilePlaying=0 in the ini (no rebuild needed), or
//     delete the L-FIX-4c blocks.
// 2026-08-05: launcher v3.7 - L-FIX-5e: GameInstalled gate + real client exe.
//     Field snag: after a successful install the startup still offered the
//     copy. Root cause found by inspecting a real Deluxe install: the ISO
//     ships FA42R.EXE / FA42B.EXE / FA42D.EXE and NO FA.exe, so the
//     GameDir\FA.exe existence check could never turn true. Two fixes:
//     * Explicit gate: GameInstalled=true|false in launcher.ini. Written
//       automatically (true) after a successful install; while true, startup
//       NEVER offers download/resume/copy again regardless of exe detection.
//     * After the copy, the actual client exe is detected (FA42R.EXE
//       preferred, then FA.exe, then FA42B.EXE) and persisted as ClientExe=
//       alongside GameDir= and GameInstalled= (ini writer generalized to
//       update all three keys in one preserving pass), so the launch
//       fallback and the shortcut icon use the right binary.
//     Falsify by: a post-install launcher start showing any install offer,
//     or ClientExe= absent/wrong in launcher.ini after installing.
//     Revert by: delete GameInstalled from the ini and the L-FIX-5e blocks.
//     v3.8 - L-FIX-5f: the exe-presence gate now accepts ANY known client
//     binary (FA.EXE, FA42R.EXE, FA42D.EXE, FA42B.EXE, or the ini's custom
//     ClientExe) so both classic 4.20 and Deluxe installs count as present.
//     Post-copy detection also falls back to FA42D.EXE as a last resort.
// 2026-08-05: launcher v3.9 - L-FIX-6: single-file distribution. aria2c.exe,
//     the torrent, aria2's GPL license and a default launcher.ini (pointing
//     at the public server) are embedded as RCDATA and the launcher is now
//     self-provisioning: run without a launcher.ini beside it (the one exe a
//     pilot downloads), it installs itself to %LOCALAPPDATA%\FighterAce,
//     extracts the payload, copies itself there and relaunches from that
//     home, passing the original command line through. Re-running a newer
//     distributed exe refreshes the tools and upgrades the home copy but
//     NEVER overwrites an existing launcher.ini (GameInstalled, GameDir,
//     the saved username all survive upgrades). With a launcher.ini beside
//     it (the home itself, or a dev folder), it runs in place and only
//     fills in missing payload files. Build now links fa_launcher_res.o
//     (windres fa_launcher.rc with payload/ files).
//     Falsify by: double-clicking the bare exe in Downloads not ending at
//     the login page with everything under %LOCALAPPDATA%\FighterAce, or an
//     upgrade run wiping a pilot's saved settings.
// 2026-08-05: launcher v4.0 - L-FIX-6b: game-folder-first setup flow.
//     Restructured per plan: the bare distributed exe asks for the GAME
//     folder FIRST (same L-FIX-5c subfolder rules), creates it, provisions
//     the launcher into <target>\launcher (no %LOCALAPPDATA% home any more),
//     records InstallTarget= in the generated ini, and relaunches with
//     /getgame so the download starts with no further prompts. The install
//     step copies the ISO contents into the recorded target WITHOUT a second
//     picker (and without the not-empty confirm - the target legitimately
//     contains our launcher\ subfolder). Everything - game, launcher, tools,
//     downloaded ISO - lives self-contained under the chosen game folder.
//     The desktop shortcut now prefers FA42D.exe's icon, then the detected
//     client exe, then the launcher's own.
//     Falsify by: the bare exe asking anything after the single folder pick
//     (besides Windows' own copy/UAC dialogs), files landing outside the
//     chosen folder, or the shortcut icon not being FA42D's when present.
//     v4.0b - L-FIX-6b2: field bug - the picker reappeared after the
//     download. Root cause: the payload ini's doc COMMENT contained the
//     literal text 'InstallTarget=', which satisfied provisioning's
//     substring guard, so the real key was never appended and the install
//     step fell back to the picker. Fixed threefold: the guard now matches
//     an actual key line (leading newline), the payload comment no longer
//     contains the literal, and StartInstall gains a fallback - running
//     from a folder named 'launcher' implies the parent IS the target,
//     which also heals installs provisioned by the buggy v4.0.
//     Falsify by: a v4.0-provisioned machine still showing the picker after
//     the download with this build dropped into its launcher folder.
// 2026-08-05: launcher v4.1 - L-FIX-7: ini client path overrides the server's.
//     The launcher installs the game itself now, so GameDir/ClientExe from
//     launcher.ini (written by the install step) is authoritative at launch;
//     the account's X-Game-Client-Path from the website is demoted to a
//     fallback used only when the ini path holds no existing client exe
//     (legacy pilots with website-configured paths keep working). The stage
//     log shows which source won ('L2: using ini/server client path').
//     Falsify by: a self-installed pilot's launch running an exe outside
//     their ini GameDir while that dir contains a valid client.
//     v4.1b - L-FIX-7b: field bug - the TICKET download still targeted the
//     server-path folder (a second consumer of X-Game-Client-Path missed in
//     v4.1), so the launched client found no fresh ticket. The ticket
//     destination now follows the same ini-first precedence, with a 'D0:'
//     stage line recording which dir won.
//     Falsify by: ticket.vr1's timestamp not updating in the ini GameDir on
//     a self-installed machine at login.
// 2026-08-05: launcher v4.2 - L-FIX-8b: AV false positives. The custom
//     self-extractor (embedded aria2c PE + self-copy + relaunch) fed every
//     dropper heuristic. The outer layer is now a standard NSIS installer
//     (installer.nsi): welcome -> directory (default C:\Games\FA42, NSIS
//     auto-appends FA42 on browse) -> extract to $INSTDIR\launcher ->
//     WriteINIStr InstallTarget -> finish page runs the launcher /getgame.
//     Reinstalls preserve an existing launcher.ini; an uninstaller and
//     HKCU Add/Remove entry are written. The launcher itself drops the
//     payload resources except the default ini (self-heal only), and its
//     provisioning reduces to 'extract default ini if missing' - no picker,
//     no self-copy, no relaunch. The L-FIX-6b2 launcher-parent rule remains
//     the InstallTarget safety net.
//     Falsify by: VirusTotal detections not dropping materially vs v4.1.2,
//     or a reinstall wiping a pilot's launcher.ini.
// 2026-08-06: launcher v4.3 - L-FIX-8c: the launcher extracts NOTHING now.
//     With the NSIS installer owning all extraction, the residual ini
//     self-heal (last embedded resource + bootstrap function) is removed
//     entirely: no RCDATA resources, no extraction code, no relaunch
//     capability anywhere in the binary. A missing launcher.ini produces a
//     clear 'run FighterAce42_Setup.exe' message. The launcher is purely:
//     download -> install -> login.
//     Falsify by: strings/resource dump of fa_launcher.exe showing any
//     RCDATA payload, or any code path that writes an exe or relaunches.
// 2026-08-08: launcher v4.4 - L-FIX-9: HTTP mirror fallback for the young
//     swarm. If MirrorFallbackSecs (default 60) after the torrent starts
//     there are ZERO bytes and ZERO seeders, the launcher fetches
//     mirrors.txt from the project repo (MirrorListUrl, default
//     raw.githubusercontent.com/alon-ant/FighterAceREsurrection/main/
//     falauncher/mirrors.txt; one URL per line, #/; comments allowed),
//     resolves each entry - Google Drive share links get the large-file
//     confirm interstitial resolved to a direct drive.usercontent URL with
//     the uuid token - and hands the URL to the RUNNING aria2 via addUri
//     (forceRemove of the torrent gid first; the BT control file and the
//     0-byte stub are deleted since HTTP cannot reuse them). A dead mirror
//     (stopped status 'error') advances to the next entry; an exhausted
//     list returns to the torrent permanently for the session. The progress
//     page shows 'Source: mirror (<host>)' in mirror mode. Stage lines:
//     M0 (list size), M1 (mirror chosen), M! (exhausted).
//     Falsify by: a machine with no reachable seeds not switching to a
//     mirror within ~70 s, or a first-mirror 404 not advancing to the next.
// 2026-08-23: launcher v5.0 - L-FIX-10: torrent era removed. Field result:
//     the swarm never reached critical mass, so BitTorrent, seeding and all
//     related machinery are gone: no torrent file, no BT/DHT/LPD ports, no
//     seed-on-start, no seed-while-playing supervisor (the launcher closes
//     at game launch again), no PlayUploadLimit, no seed.bat. aria2c remains
//     purely as the HTTP engine (resume, 8-way split, RPC progress); the
//     maintained mirrors.txt on the project repo is the ONE download source,
//     started immediately (no fallback delay). Dead mirrors advance down the
//     list; an exhausted list is a clear hard stop ('try again later').
//     After a successful install the downloaded ISO is deleted to free
//     4.4 GB on the pilot's disk. Old inis with torrent-era keys still load
//     (unknown keys are ignored).
//     Falsify by: any BT traffic or listen port from a v5.0 machine, a
//     download not starting from mirror #0 within seconds, or the ISO still
//     present after a completed install.
//     Falsify by: post-install, a file under the target still carrying the R
//     attribute, GameDir absent from launcher.ini, or the game failing to
//     launch from the saved path.
//     Revert by: delete the L-FIX-5 block + the BeforeNavigate2 catch + the
//     two WndProc messages + the wWinMain offer changes.
// 2026-08-25: launcher v5.2 - L-FIX-10b: torrent leftovers scrubbed. L-FIX-10
//     removed the machinery but four references survived; one was live UI:
//     the fresh-install offer still promised 'via BitTorrent + mirror,
//     shared with other pilots'. That dialog now says 'direct download from
//     the project mirror list'. The other three were stale comments only
//     (g_mirrorIndex '-1 = torrent mode', the SwitchToNextMirror header, the
//     L-FIX-4 section banner) - zero behavior change; the aria2c command
//     line was audited and carries no BT/DHT/seed flags.
//     Falsify by: the word 'BitTorrent' appearing anywhere in the built
//     binary's strings, or any dialog mentioning seeding/sharing.
// 2026-08-25: launcher v5.3 - L-FIX-11: mirror content validation. Field
//     failure: Google Drive over daily quota answers HTTP 200 with an HTML
//     'Quota exceeded' page (~2 KB); ResolveMirror found no confirm uuid in
//     it and fed the URL to aria2 anyway, which saved the page as the ISO
//     with no .aria2 control file - so PollDownload reported 'complete',
//     auto-install fired on a web page, and startup forever saw a finished
//     disc. Three layers now:
//     * ProbeMirrorUrl: before addUri, GET the first 512 bytes + headers of
//       the resolved URL; text/html content-type, an HTML-looking body, or
//       a Content-Length under MIN_ISO_BYTES (3 GiB floor; queried as a
//       string - the DWORD query overflows past 4 GB) rejects the mirror
//       and the pick loop moves down the list ('M!: mirror #N rejected').
//     * PollDownload: a 'complete' file failing IsIsoFileValid (size floor
//       + HTML sniff) is deleted and the download rotates to the next
//       mirror instead of offering install. StartInstall has the same
//       guard with a clear message.
//     * Startup: an existing 'complete' ISO failing IsIsoFileValid is
//       deleted, so machines that already saved the quota page self-heal
//       into a normal download offer.
//     Falsify by: a quota'd first mirror not being skipped within seconds,
//     an install ever starting from a <3 GiB file, or a machine with a
//     saved quota page not offering a fresh download on next start.
//     Revert by: delete the L-FIX-11 blocks (probe loop back to plain
//     ++g_mirrorIndex; drop the three IsIsoFileValid call sites).
// 2026-08-28: launcher v5.4 - L-FIX-12: Mega.nz mirror support. Mega files
//     are end-to-end encrypted (the '#' fragment of a share link is the
//     32-byte AES file key), so a Mega mirror needs its own pipeline:
//     ResolveMirror routes mega.nz/mega.co.nz entries to ResolveMegaLink,
//     which POSTs {"a":"g","g":1,"p":<handle>} to g.api.mega.co.nz and gets
//     a temporary direct ciphertext URL (plain HTTPS, range-resumable);
//     aria2 downloads that to <iso>.megaenc; on completion a worker thread
//     streams it through AES-128-CTR via CNG (key = raw[0..15]^raw[16..31],
//     nonce = raw[16..23], big-endian block counter; CNG has no CTR mode so
//     the counter blocks are ECB-encrypted and XORed) into <iso>.megadec,
//     verifies the ISO9660 'CD001' signature at 0x8000 (wrong-key catch;
//     Mega's chunked CBC-MAC is deliberately NOT verified - the signature
//     check + L-FIX-11 validation cover the corruption cases), then swaps
//     .megadec in as the ISO and removes the ciphertext. The .megadec size
//     doubles as the decrypt resume marker (ciphertext is never modified,
//     so truncate-to-chunk-and-continue is always safe); .megaenc resumes
//     over aria2 by size like any mirror; both temps count as a partial
//     download at startup. Progress page shows a 'Decrypting the disc
//     image... N%' phase. Decrypt failure = wipe temps + next mirror. An
//     unresolvable entry (bad link, over quota: the API answers a bare
//     error code, no 'g' URL) is skipped by the pick loop like any
//     rejected mirror. Old dead pre-escape addUri body build dropped while
//     touching that code. Links -lbcrypt now.
//     Falsify by: a Mega mirror yielding an .iso that fails IsIsoFileValid
//     or CD001, a decrypt resume after kill producing a corrupt image, or
//     an over-quota Mega link not being skipped.
//     Revert by: delete the L-FIX-12 block + the ResolveMirror route + the
//     PollDownload decrypt phase + outName; restore out=isoName.
// ============================================================================

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN

#include <windows.h>
#include <exdisp.h>       // IWebBrowser2, DWebBrowserEvents2
#include <exdispid.h>     // DISPID_* event ids
#include <mshtmhst.h>     // IDocHostUIHandler, DOCHOSTUIINFO
#include <mshtml.h>       // L-FIX-2: IHTMLDocument2 / IHTMLInputElement DOM access
#include <ocidl.h>
#include <oleidl.h>
#include <shlobj.h>
#include <shobjidl.h>   // L-FIX-5b: IFileOpenDialog folder picker
#include <shellapi.h>
#include <urlmon.h>       // URLDownloadToFile
#include <servprov.h>     // IServiceProvider
#include <initguid.h>     // so DEFINE_GUID emits the GUID data in this TU
#include <downloadmgr.h>  // IDownloadManager, IID_IDownloadManager
// SID_SDownloadManager isn't defined by the MinGW headers; it equals the IID.
#ifndef SID_SDownloadManager
#define SID_SDownloadManager IID_IDownloadManager
#endif
#include <wininet.h>
#include <winsock2.h>     // L-FIX-4b: loopback bind test for RPC port probing
#include <objbase.h>
#include <string>
#include <vector>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <bcrypt.h>       // L-FIX-12: AES-128-CTR for Mega downloads
#ifndef NT_SUCCESS
#define NT_SUCCESS(s) (((NTSTATUS)(s)) >= 0)
#endif

// ----------------------------------------------------------------------------
//  Config (launcher.ini)
// ----------------------------------------------------------------------------
struct Config {
    std::wstring loginUrl  = L"http://localhost/login";
    std::wstring gameDir   = L"C:\\games\\FA";
    std::wstring clientExe = L"FA.exe";
    std::wstring launchArgs =
        L"/MK:0 \"/MCD1:0 /MCD2:0 /MTD:0 /NoPreload /PPS:5 /FPS:50 /SDM:1000\"";
    int windowW = 460;
    int windowH = 640;
    // L-FIX-10: download settings (mirror-list HTTP only; the torrent/seeding
    // era is over). Empty strings get ExeDir-relative defaults at startup.
    std::wstring downloadDir;                          // <ExeDir>\\download
    std::wstring aria2Exe;                             // <ExeDir>\\aria2c.exe (HTTP engine)
    std::wstring isoName = L"FA42DeluxeEdition.iso";
    int  rpcPort = 6811;            // aria2 JSON-RPC port on 127.0.0.1
    // L-FIX-10: the ONLY download source - the maintained mirror list.
    std::wstring mirrorListUrl =
        L"https://raw.githubusercontent.com/alon-ant/FighterAceREsurrection/main/falauncher/mirrors.txt";
    // L-FIX-5b: the folder inside the ISO whose CONTENTS are copied to the
    // user-selected target (no installer is run).
    std::wstring isoGameFolder = L"FIGHTER_ACE_4_2_DELUXE_EDITION";
    // L-FIX-5c: subfolder created inside the user's selection to hold the game
    // (unless the selection is empty or already named like this).
    std::wstring installSubdir = L"FA42";
    // L-FIX-5e: explicit installed gate - once true, startup never offers
    // download/copy again (written automatically after a successful install).
    bool gameInstalled = false;
    // L-FIX-6b: game folder chosen at setup time (written into the generated
    // launcher.ini by provisioning); the install step copies the ISO contents
    // here WITHOUT asking again.
    std::wstring installTarget;
};
static std::wstring MakeAbsolute(const std::wstring& url);   // fwd (L-FIX-5 uses it early)

static std::wstring Trim(const std::wstring& s) {
    const wchar_t* ws = L" \t\r\n";
    size_t b = s.find_first_not_of(ws);
    if (b == std::wstring::npos) return L"";
    size_t e = s.find_last_not_of(ws);
    return s.substr(b, e - b + 1);
}
static std::wstring Utf8ToWide(const std::string& s) {
    if (s.empty()) return L"";
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), nullptr, 0);
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), &w[0], n);
    return w;
}
static std::string WideToUtf8(const std::wstring& w) {
    if (w.empty()) return "";
    int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    std::string s(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), &s[0], n, nullptr, nullptr);
    return s;
}
static void ShowError(const std::wstring& m) {
    MessageBoxW(nullptr, m.c_str(), L"FA Secure Launcher", MB_OK | MB_ICONERROR);
}
static void Stage(const wchar_t* s);   // fwd: defined later, used by download/host code
static std::wstring ExeDir() {
    std::vector<wchar_t> buf(MAX_PATH);
    for (;;) {
        DWORD n = GetModuleFileNameW(nullptr, buf.data(), (DWORD)buf.size());
        if (!n) return L".";
        if (n < buf.size() - 1) break;
        buf.resize(buf.size() * 2);
    }
    std::wstring p(buf.data());
    size_t s = p.find_last_of(L"\\/");
    return (s == std::wstring::npos) ? L"." : p.substr(0, s);
}
static bool FileExists(const std::wstring& p) {
    DWORD a = GetFileAttributesW(p.c_str());
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

static bool LoadConfig(const std::wstring& ini, Config& cfg, std::wstring& err) {
    std::ifstream f(ini.c_str(), std::ios::binary);
    if (!f) { err = L"Could not open launcher.ini at:\n" + ini; return false; }
    std::stringstream ss; ss << f.rdbuf();
    std::string bytes = ss.str();
    if (bytes.size() >= 3 && (unsigned char)bytes[0] == 0xEF &&
        (unsigned char)bytes[1] == 0xBB && (unsigned char)bytes[2] == 0xBF)
        bytes.erase(0, 3);
    std::wstring text = Utf8ToWide(bytes);
    std::wstringstream lines(text); std::wstring line;
    while (std::getline(lines, line)) {
        std::wstring t = Trim(line);
        if (t.empty() || t[0] == L';' || t[0] == L'#' || t[0] == L'[') continue;
        size_t eq = t.find(L'='); if (eq == std::wstring::npos) continue;
        std::wstring k = Trim(t.substr(0, eq)), v = Trim(t.substr(eq + 1));
        if (v.size() >= 2 && v.front() == L'"' && v.back() == L'"') v = v.substr(1, v.size() - 2);
        std::wstring lk = k; std::transform(lk.begin(), lk.end(), lk.begin(), ::towlower);
        if      (lk == L"loginurl" || lk == L"serverurl" || lk == L"server") cfg.loginUrl = v;
        else if (lk == L"gamedir")    cfg.gameDir = v;
        else if (lk == L"clientexe")  cfg.clientExe = v;
        else if (lk == L"launchargs") cfg.launchArgs = v;
        else if (lk == L"windowwidth")  { try { cfg.windowW = std::stoi(v); } catch (...) {} }
        else if (lk == L"windowheight") { try { cfg.windowH = std::stoi(v); } catch (...) {} }
        // L-FIX-10 (torrent-era keys in old inis are ignored like any unknown key)
        else if (lk == L"downloaddir")  cfg.downloadDir = v;
        else if (lk == L"aria2exe")     cfg.aria2Exe = v;
        else if (lk == L"isoname")      cfg.isoName = v;
        else if (lk == L"rpcport")      { try { cfg.rpcPort = std::stoi(v); } catch (...) {} }
        else if (lk == L"mirrorlisturl") cfg.mirrorListUrl = v;
        else if (lk == L"isogamefolder") cfg.isoGameFolder = v;
        else if (lk == L"installsubdir") cfg.installSubdir = v;
        else if (lk == L"installtarget") cfg.installTarget = v;
        else if (lk == L"gameinstalled") {
            std::wstring lv = v;
            std::transform(lv.begin(), lv.end(), lv.begin(), ::towlower);
            cfg.gameInstalled = (lv == L"true" || lv == L"1" || lv == L"yes");
        }
    }
    return true;
}

// ----------------------------------------------------------------------------
//  Globals
// ----------------------------------------------------------------------------
static Config        g_cfg;
static IWebBrowser2* g_web = nullptr;
static HWND          g_mainWnd = nullptr;
static bool          g_launched = false;
static bool          g_handling = false;   // set as soon as a download is being handled
static bool          g_docLoaded = false;  // set on DocumentComplete for the login page
static int           g_navAttempts = 0;
static std::wstring  g_pendingUrl;         // url to fetch, handed to the main thread
// L-FIX-1: the control's active object; every message is offered to its
// TranslateAccelerator so TAB/arrows/Ctrl+A work inside the hosted page.
static IOleInPlaceActiveObject* g_ipao = nullptr;
#define WM_DO_DOWNLOAD (WM_APP + 1)
#define WM_DO_NAVIGATE (WM_APP + 2)
#define NAV_RETRY_TIMER 1001

// ----------------------------------------------------------------------------
//  L-FIX-2: remember the last logged-in username (lastuser.txt next to the exe)
// ----------------------------------------------------------------------------
static std::wstring LastUserPath() { return ExeDir() + L"\\lastuser.txt"; }

static std::wstring LoadLastUser() {
    std::ifstream f(LastUserPath().c_str(), std::ios::binary);
    if (!f) return L"";
    std::stringstream ss; ss << f.rdbuf();
    std::string bytes = ss.str();
    if (bytes.size() >= 3 && (unsigned char)bytes[0] == 0xEF &&
        (unsigned char)bytes[1] == 0xBB && (unsigned char)bytes[2] == 0xBF)
        bytes.erase(0, 3);
    return Trim(Utf8ToWide(bytes));
}

static void SaveLastUser(const std::wstring& user) {
    if (user.empty()) return;
    std::ofstream f(LastUserPath().c_str(), std::ios::binary | std::ios::trunc);
    if (!f) return;
    std::string u8 = WideToUtf8(user);
    f.write(u8.data(), (std::streamsize)u8.size());
}

// Walk the current document's <input> elements. Returns (AddRef'd) the FIRST
// text-type input, and reports whether the page also has a password input --
// the "has a password field" test is what makes this the LOGIN page and not
// some other page with a random text box. Any of the outputs may be null.
static void FindLoginFields(IHTMLInputElement** userField,
                            IHTMLElement** passElem, bool* hasPassword) {
    if (userField) *userField = nullptr;
    if (passElem)  *passElem  = nullptr;
    if (hasPassword) *hasPassword = false;
    if (!g_web) return;

    IDispatch* docDisp = nullptr;
    if (FAILED(g_web->get_Document(&docDisp)) || !docDisp) return;
    IHTMLDocument2* doc = nullptr;
    docDisp->QueryInterface(IID_IHTMLDocument2, (void**)&doc);
    docDisp->Release();
    if (!doc) return;

    IHTMLElementCollection* all = nullptr;
    if (SUCCEEDED(doc->get_all(&all)) && all) {
        long len = 0; all->get_length(&len);
        for (long i = 0; i < len; ++i) {
            VARIANT idx; VariantInit(&idx); idx.vt = VT_I4; idx.lVal = i;
            VARIANT dummy; VariantInit(&dummy); dummy.vt = VT_I4; dummy.lVal = 0;
            IDispatch* elDisp = nullptr;
            if (FAILED(all->item(idx, dummy, &elDisp)) || !elDisp) continue;
            IHTMLInputElement* inp = nullptr;
            elDisp->QueryInterface(IID_IHTMLInputElement, (void**)&inp);
            if (inp) {
                BSTR type = nullptr;
                if (SUCCEEDED(inp->get_type(&type)) && type) {
                    std::wstring t = type; SysFreeString(type);
                    std::transform(t.begin(), t.end(), t.begin(), ::towlower);
                    if (t == L"password") {
                        if (hasPassword) *hasPassword = true;
                        if (passElem && !*passElem)
                            elDisp->QueryInterface(IID_IHTMLElement, (void**)passElem);
                    } else if (t == L"text" || t.empty()) {
                        if (userField && !*userField) { *userField = inp; inp = nullptr; }
                    }
                } else if (type) SysFreeString(type);
                if (inp) inp->Release();
            }
            elDisp->Release();
        }
        all->Release();
    }
    doc->Release();
}

// DocumentComplete: if this looks like the login page and the username box is
// empty, drop in the remembered name and put the caret in the password box.
static void PrefillLastUser() {
    std::wstring saved = LoadLastUser();
    if (saved.empty()) return;
    IHTMLInputElement* user = nullptr; IHTMLElement* pass = nullptr; bool hasPw = false;
    FindLoginFields(&user, &pass, &hasPw);
    if (user && hasPw) {
        BSTR cur = nullptr;
        bool empty = true;
        if (SUCCEEDED(user->get_value(&cur)) && cur) {
            empty = (SysStringLen(cur) == 0);
            SysFreeString(cur);
        }
        if (empty) {
            BSTR v = SysAllocString(saved.c_str());
            user->put_value(v);
            SysFreeString(v);
            Stage(L"U1: prefilled last user");
            if (pass) {
                IHTMLElement2* p2 = nullptr;
                if (SUCCEEDED(pass->QueryInterface(IID_IHTMLElement2, (void**)&p2)) && p2) {
                    p2->focus(); p2->Release();
                }
            }
        }
    }
    if (user) user->Release();
    if (pass) pass->Release();
}

// BeforeNavigate2 (i.e. the form is being submitted / any navigation away):
// if the outgoing page has a password field, persist the username box's value.
// The password itself is never read or stored.
static void CaptureLastUser() {
    IHTMLInputElement* user = nullptr; bool hasPw = false;
    FindLoginFields(&user, nullptr, &hasPw);
    if (user) {
        if (hasPw) {
            BSTR v = nullptr;
            if (SUCCEEDED(user->get_value(&v)) && v) {
                std::wstring u = Trim(std::wstring(v));
                if (!u.empty()) { SaveLastUser(u); Stage(L"U2: saved last user"); }
                SysFreeString(v);
            }
        }
        user->Release();
    }
}

// ----------------------------------------------------------------------------
//  L-FIX-4 -> L-FIX-10: game download (bundled aria2c.exe, now a pure
//  mirror-list HTTP download engine - no BitTorrent)
// ----------------------------------------------------------------------------
static bool   g_downloadMode = false;  // the browser is showing the progress page
static bool   g_startInstall = false;  // L-FIX-5: auto-trigger install after startup
static HANDLE g_ariaProc = nullptr;    // aria2c process handle (nullptr = not running)
#define DL_POLL_TIMER 1002

static std::wstring RandToken() {
    wchar_t b[48];
    swprintf(b, 48, L"fa%08lx%08lx",
             (unsigned long)GetTickCount64(),
             (unsigned long)(GetCurrentProcessId() * 2654435761u));
    return b;
}
static std::wstring g_rpcSecret;

// Minimal JSON field extractor for aria2's responses. Handles "key":"value"
// (aria2 sends all numbers as strings) and bare numbers. Good enough here;
// we never parse nested objects by key.
static std::string JStr(const std::string& js, const std::string& key, size_t from = 0) {
    std::string pat = "\"" + key + "\":";
    size_t p = js.find(pat, from);
    if (p == std::string::npos) return "";
    p += pat.size();
    if (p < js.size() && js[p] == '"') {
        size_t e = js.find('"', p + 1);
        if (e == std::string::npos) return "";
        return js.substr(p + 1, e - p - 1);
    }
    size_t e = js.find_first_of(",}]", p);
    return js.substr(p, e == std::string::npos ? std::string::npos : e - p);
}

// POST a JSON-RPC body to the local aria2 and return the response body
// (empty on any failure). Short timeouts: this runs on the UI thread.
static std::string RpcCall(const std::string& body) {
    std::string out;
    HINTERNET hNet = InternetOpenW(L"FALauncherRPC", INTERNET_OPEN_TYPE_DIRECT,
                                   nullptr, nullptr, 0);
    if (!hNet) return out;
    DWORD to = 1500;
    InternetSetOptionW(hNet, INTERNET_OPTION_CONNECT_TIMEOUT, &to, sizeof to);
    InternetSetOptionW(hNet, INTERNET_OPTION_SEND_TIMEOUT,    &to, sizeof to);
    InternetSetOptionW(hNet, INTERNET_OPTION_RECEIVE_TIMEOUT, &to, sizeof to);
    HINTERNET hCon = InternetConnectW(hNet, L"127.0.0.1", (INTERNET_PORT)g_cfg.rpcPort,
                                      nullptr, nullptr, INTERNET_SERVICE_HTTP, 0, 0);
    if (hCon) {
        HINTERNET hReq = HttpOpenRequestW(hCon, L"POST", L"/jsonrpc", nullptr, nullptr, nullptr,
                                          INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE, 0);
        if (hReq) {
            const wchar_t* hdr = L"Content-Type: application/json\r\n";
            if (HttpSendRequestW(hReq, hdr, (DWORD)-1, (LPVOID)body.data(), (DWORD)body.size())) {
                char buf[8192]; DWORD got = 0;
                while (InternetReadFile(hReq, buf, sizeof buf, &got) && got > 0)
                    out.append(buf, got);
            }
            InternetCloseHandle(hReq);
        }
        InternetCloseHandle(hCon);
    }
    InternetCloseHandle(hNet);
    return out;
}
static std::string RpcMethod(const char* method) {
    return std::string("{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"") + method +
           "\",\"params\":[\"token:" + WideToUtf8(g_rpcSecret) + "\"]}";
}

// L-FIX-4b: is this loopback TCP port free? (bind test - aria2's RPC listens
// on loopback only, so this exactly mirrors what aria2 will try to do.)
static bool PortFree(int port) {
    WSADATA w; WSAStartup(MAKEWORD(2, 2), &w);
    SOCKET s = socket(AF_INET, SOCK_STREAM, 0);
    if (s == INVALID_SOCKET) return true;   // can't tell; assume free
    sockaddr_in a; ZeroMemory(&a, sizeof a);
    a.sin_family = AF_INET;
    a.sin_port = htons((u_short)port);
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    bool ok = (bind(s, (sockaddr*)&a, sizeof a) == 0);
    closesocket(s);
    return ok;
}

// L-FIX-10: start aria2c as a bare HTTP download engine (RPC only, nothing
// queued). Mirrors are added over RPC by SwitchToNextMirror.
static bool StartAria2(std::wstring& err) {
    if (g_ariaProc) return true;
    if (!FileExists(g_cfg.aria2Exe)) { err = L"aria2c.exe was not found next to the launcher:\n" + g_cfg.aria2Exe; return false; }
    CreateDirectoryW(g_cfg.downloadDir.c_str(), nullptr);
    g_rpcSecret = RandToken();

    // L-FIX-4b: take the first free RPC port in RpcPort..RpcPort+9 so a second
    // launcher instance (or a stale aria2) can never hijack our polling.
    for (int i = 0; i < 10; ++i) {
        if (PortFree(g_cfg.rpcPort + i)) { g_cfg.rpcPort += i; break; }
    }

    std::wstring cmd = L"\"" + g_cfg.aria2Exe + L"\""
        L" --enable-rpc --rpc-listen-all=false"
        L" --rpc-listen-port=" + std::to_wstring(g_cfg.rpcPort) +
        L" --rpc-secret=" + g_rpcSecret +
        L" --dir=\"" + g_cfg.downloadDir + L"\""
        L" --continue=true --file-allocation=none"
        L" --summary-interval=0 -q";

    STARTUPINFOW si; ZeroMemory(&si, sizeof si); si.cb = sizeof si;
    PROCESS_INFORMATION pi; ZeroMemory(&pi, sizeof pi);
    std::vector<wchar_t> buf(cmd.begin(), cmd.end()); buf.push_back(0);
    if (!CreateProcessW(g_cfg.aria2Exe.c_str(), buf.data(), nullptr, nullptr, FALSE,
                        CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi)) {
        wchar_t b[128]; swprintf(b, 128, L"Could not start aria2c (error %lu).", GetLastError());
        err = b; return false;
    }
    CloseHandle(pi.hThread);
    g_ariaProc = pi.hProcess;
    Stage(L"T1: aria2 started (download engine)");
    return true;
}

// Ask aria2 to shut down cleanly (flushes the .aria2 control file); terminate
// only if it ignores us. waitMs=0 is the fire-and-forget path.
static void StopAria2(DWORD waitMs) {
    if (!g_ariaProc) return;
    RpcCall(RpcMethod("aria2.shutdown"));
    if (WaitForSingleObject(g_ariaProc, waitMs) == WAIT_TIMEOUT)
        TerminateProcess(g_ariaProc, 0);
    CloseHandle(g_ariaProc);
    g_ariaProc = nullptr;
    Stage(L"T2: aria2 stopped");
}

// Replace the current document's <body> with the given HTML (progress page).
static void SetBrowserBody(const std::wstring& html) {
    if (!g_web) return;
    IDispatch* d = nullptr;
    if (FAILED(g_web->get_Document(&d)) || !d) return;
    IHTMLDocument2* doc = nullptr;
    d->QueryInterface(IID_IHTMLDocument2, (void**)&doc);
    d->Release();
    if (!doc) return;
    IHTMLElement* body = nullptr;
    if (SUCCEEDED(doc->get_body(&body)) && body) {
        BSTR b = SysAllocString(html.c_str());
        body->put_innerHTML(b);
        SysFreeString(b);
        body->Release();
    }
    doc->Release();
}

static std::wstring FmtGB(unsigned long long bytes) {
    wchar_t b[32]; swprintf(b, 32, L"%.2f GB", bytes / 1073741824.0); return b;
}
static std::wstring FmtSpeed(unsigned long long bps) {
    wchar_t b[32];
    if (bps >= 1048576) swprintf(b, 32, L"%.1f MB/s", bps / 1048576.0);
    else                swprintf(b, 32, L"%.0f KB/s", bps / 1024.0);
    return b;
}

// ----------------------------------------------------------------------------
//  L-FIX-5: install the game from the downloaded ISO + make its folder writable
// ----------------------------------------------------------------------------
enum InstallState { INST_NONE, INST_RUNNING, INST_DONE, INST_FAIL };
static bool g_sawUnfinished = false;  // L-FIX-5d: we watched this download run
static bool g_autoInstall   = false;  // L-FIX-5d: auto-picker fired already
static InstallState g_instState = INST_NONE;
static std::wstring g_instMsg;        // shown on the progress page
static std::wstring g_mountedIso;     // non-empty while our ISO is mounted
#define WM_DO_INSTALL  (WM_APP + 3)
#define WM_DO_FIXPERMS (WM_APP + 4)

// Run a hidden command, capture its stdout, wait for exit (bounded).
static std::wstring RunCaptureW(const std::wstring& cmdline, DWORD timeoutMs) {
    std::string out;
    SECURITY_ATTRIBUTES sa; ZeroMemory(&sa, sizeof sa);
    sa.nLength = sizeof sa; sa.bInheritHandle = TRUE;
    HANDLE rd = nullptr, wr = nullptr;
    if (!CreatePipe(&rd, &wr, &sa, 0)) return L"";
    SetHandleInformation(rd, HANDLE_FLAG_INHERIT, 0);
    STARTUPINFOW si; ZeroMemory(&si, sizeof si); si.cb = sizeof si;
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    si.hStdOutput = wr; si.hStdError = wr; si.hStdInput = nullptr;
    PROCESS_INFORMATION pi; ZeroMemory(&pi, sizeof pi);
    std::vector<wchar_t> buf(cmdline.begin(), cmdline.end()); buf.push_back(0);
    if (CreateProcessW(nullptr, buf.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW,
                       nullptr, nullptr, &si, &pi)) {
        CloseHandle(wr); wr = nullptr;
        char b[512]; DWORD got = 0;
        while (ReadFile(rd, b, sizeof b, &got, nullptr) && got > 0) out.append(b, got);
        WaitForSingleObject(pi.hProcess, timeoutMs);
        CloseHandle(pi.hProcess); CloseHandle(pi.hThread);
    }
    if (wr) CloseHandle(wr);
    CloseHandle(rd);
    return Utf8ToWide(out);   // we only ever need ASCII (a drive letter) from this
}

// Mount the ISO and return its drive letter (0 on failure). No admin needed.
static wchar_t MountIso(const std::wstring& iso) {
    std::wstring cmd = L"powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "
        L"\"(Mount-DiskImage -ImagePath '" + iso + L"' -PassThru | Get-Volume).DriveLetter\"";
    std::wstring out = RunCaptureW(cmd, 45000);
    for (wchar_t c : out)
        if ((c >= L'A' && c <= L'Z') || (c >= L'a' && c <= L'z')) return towupper(c);
    // Occasionally the volume isn't ready in the same pipeline; ask again.
    Sleep(1500);
    cmd = L"powershell.exe -NoProfile -Command "
        L"\"(Get-DiskImage -ImagePath '" + iso + L"' | Get-Volume).DriveLetter\"";
    out = RunCaptureW(cmd, 20000);
    for (wchar_t c : out)
        if ((c >= L'A' && c <= L'Z') || (c >= L'a' && c <= L'z')) return towupper(c);
    return 0;
}

static void DismountIso() {
    if (g_mountedIso.empty()) return;
    RunCaptureW(L"powershell.exe -NoProfile -Command \"Dismount-DiskImage -ImagePath '" +
                g_mountedIso + L"'\"", 20000);
    g_mountedIso.clear();
    Stage(L"I: iso dismounted");
}

// Vista+ folder picker (the modern common dialog). GUIDs defined here because
// MinGW's uuid lib doesn't always carry them. Falls back to SHBrowseForFolder.
static const CLSID L5_CLSID_FileOpenDialog =
    {0xDC1C5A9C, 0xE88A, 0x4DDE, {0xA5, 0xA1, 0x60, 0xF8, 0x2A, 0x20, 0xAE, 0xF7}};
static const IID L5_IID_IFileOpenDialog =
    {0xD57C7288, 0xD4AD, 0x4768, {0xBE, 0x02, 0x9D, 0x96, 0x95, 0x32, 0xD9, 0x60}};

static std::wstring PickFolder(const wchar_t* title) {
    std::wstring result;
    IFileOpenDialog* dlg = nullptr;
    if (SUCCEEDED(CoCreateInstance(L5_CLSID_FileOpenDialog, nullptr, CLSCTX_INPROC_SERVER,
                                   L5_IID_IFileOpenDialog, (void**)&dlg)) && dlg) {
        DWORD opts = 0;
        dlg->GetOptions(&opts);
        dlg->SetOptions(opts | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM);
        dlg->SetTitle(title);
        if (SUCCEEDED(dlg->Show(g_mainWnd))) {
            IShellItem* it = nullptr;
            if (SUCCEEDED(dlg->GetResult(&it)) && it) {
                PWSTR p = nullptr;
                if (SUCCEEDED(it->GetDisplayName(SIGDN_FILESYSPATH, &p)) && p) {
                    result = p;
                    CoTaskMemFree(p);
                }
                it->Release();
            }
        }
        dlg->Release();
        return result;
    }
    // Pre-Vista fallback
    BROWSEINFOW bi; ZeroMemory(&bi, sizeof bi);
    bi.hwndOwner = g_mainWnd;
    bi.lpszTitle = title;
    bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE;
    PIDLIST_ABSOLUTE pidl = SHBrowseForFolderW(&bi);
    if (pidl) {
        wchar_t path[MAX_PATH] = L"";
        if (SHGetPathFromIDListW(pidl, path) && path[0]) result = path;
        CoTaskMemFree(pidl);
    }
    return result;
}

// Recursively clear FILE_ATTRIBUTE_READONLY under dir (the copy inherits the
// R attribute from the UDF/ISO9660 disc image). In-process, no elevation -
// the user just copied here, so the folder is writable by them.
static void ClearReadOnlyTree(const std::wstring& dir, int& cleared, int& failed) {
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW((dir + L"\\*").c_str(), &fd);
    if (h == INVALID_HANDLE_VALUE) return;
    do {
        std::wstring name = fd.cFileName;
        if (name == L"." || name == L"..") continue;
        std::wstring full = dir + L"\\" + name;
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_READONLY) {
            if (SetFileAttributesW(full.c_str(),
                                   fd.dwFileAttributes & ~FILE_ATTRIBUTE_READONLY)) ++cleared;
            else ++failed;
        }
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)
            ClearReadOnlyTree(full, cleared, failed);
    } while (FindNextFileW(h, &fd));
    FindClose(h);
}

// Persist GameDir=, ClientExe= and GameInstalled=true into launcher.ini,
// preserving everything else (BOM, comments, key order). Each key's first
// ACTIVE line is replaced; missing keys are appended at the end.
static bool SaveInstallToIni(const std::wstring& dir, const std::wstring& exeName) {
    std::wstring ini = ExeDir() + L"\\launcher.ini";
    std::ifstream f(ini.c_str(), std::ios::binary);
    std::string bytes;
    bool hadBom = false;
    if (f) { std::stringstream ss; ss << f.rdbuf(); bytes = ss.str(); }
    if (bytes.size() >= 3 && (unsigned char)bytes[0] == 0xEF &&
        (unsigned char)bytes[1] == 0xBB && (unsigned char)bytes[2] == 0xBF) {
        hadBom = true; bytes.erase(0, 3);
    }
    std::wstring text = Utf8ToWide(bytes);
    bool endsWithNl = !text.empty() && text.back() == L'\n';

    std::vector<std::wstring> lines;
    { std::wstringstream ls(text); std::wstring line;
      while (std::getline(ls, line)) lines.push_back(line); }

    struct KV { const wchar_t* key; std::wstring value; bool done; };
    KV kvs[] = { { L"gamedir",       dir,      false },
                 { L"clientexe",     exeName,  false },
                 { L"gameinstalled", L"true",  false } };
    const wchar_t* names[] = { L"GameDir", L"ClientExe", L"GameInstalled" };
    for (auto& line : lines) {
        std::wstring t = Trim(line);
        if (t.empty() || t[0] == L';' || t[0] == L'#' || t[0] == L'[') continue;
        size_t eq = t.find(L'=');
        if (eq == std::wstring::npos) continue;
        std::wstring low = Trim(t.substr(0, eq));
        std::transform(low.begin(), low.end(), low.begin(), ::towlower);
        for (size_t k = 0; k < 3; ++k)
            if (!kvs[k].done && low == kvs[k].key) {
                line = std::wstring(names[k]) + L"=" + kvs[k].value;
                kvs[k].done = true;
            }
    }
    bool appendedHeader = false;
    for (size_t k = 0; k < 3; ++k) {
        if (kvs[k].done) continue;
        if (!appendedHeader) {
            lines.push_back(L"");
            lines.push_back(L"; Written by the launcher after installing from the ISO:");
            appendedHeader = true;
        }
        lines.push_back(std::wstring(names[k]) + L"=" + kvs[k].value);
        endsWithNl = true;
    }

    std::wstring outw;
    for (size_t i = 0; i < lines.size(); ++i) {
        outw += lines[i];
        if (i + 1 < lines.size() || endsWithNl) outw += L"\n";
    }
    std::ofstream o(ini.c_str(), std::ios::binary | std::ios::trunc);
    if (!o) return false;
    if (hadBom) o.write("\xEF\xBB\xBF", 3);
    std::string u8 = WideToUtf8(outw);
    o.write(u8.data(), (std::streamsize)u8.size());
    g_cfg.gameDir = dir;
    return true;
}

// True if the directory contains no entries besides . and .. .
static bool IsDirEmpty(const std::wstring& dir) {
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW((dir + L"\\*").c_str(), &fd);
    if (h == INVALID_HANDLE_VALUE) return true;   // unreadable: treat as empty
    bool empty = true;
    do {
        std::wstring n = fd.cFileName;
        if (n != L"." && n != L"..") { empty = false; break; }
    } while (FindNextFileW(h, &fd));
    FindClose(h);
    return empty;
}

// L-FIX-5d: desktop shortcut to THIS launcher, wearing the game's icon.
static bool CreateDesktopShortcut(const std::wstring& gameDir) {
    wchar_t exe[MAX_PATH] = L"";
    GetModuleFileNameW(nullptr, exe, MAX_PATH);
    wchar_t desk[MAX_PATH] = L"";
    if (FAILED(SHGetFolderPathW(nullptr, CSIDL_DESKTOPDIRECTORY, nullptr, 0, desk)))
        return false;
    std::wstring lnk = std::wstring(desk) + L"\\Fighter Ace 4.2.lnk";
    IShellLinkW* sl = nullptr;
    if (FAILED(CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER,
                                IID_IShellLinkW, (void**)&sl)) || !sl)
        return false;
    sl->SetPath(exe);
    sl->SetWorkingDirectory(ExeDir().c_str());
    sl->SetDescription(L"Fighter Ace 4.2 - Secure Launcher");
    // L-FIX-6b: the shortcut wears FA42D.exe's icon when available, then the
    // detected client exe, then the launcher's own.
    std::wstring icon;
    const wchar_t* iconCands[] = { L"FA42D.EXE", g_cfg.clientExe.c_str(),
                                   L"FA42R.EXE", L"FA.EXE" };
    for (auto c : iconCands) {
        std::wstring p = gameDir + L"\\" + c;
        if (FileExists(p)) { icon = p; break; }
    }
    sl->SetIconLocation(icon.empty() ? exe : icon.c_str(), 0);
    IPersistFile* pf = nullptr;
    bool ok = false;
    if (SUCCEEDED(sl->QueryInterface(IID_IPersistFile, (void**)&pf)) && pf) {
        ok = SUCCEEDED(pf->Save(lnk.c_str(), TRUE));
        pf->Release();
    }
    sl->Release();
    Stage(ok ? L"I: desktop shortcut created" : L"I: desktop shortcut FAILED");
    return ok;
}

// Make an existing game folder writable (the 'Fix folder permissions' link,
// also useful for pilots who copied the files by hand).
static void StartPermissionsFix() {
    std::wstring dir = g_cfg.gameDir;
    if (dir.empty() || GetFileAttributesW(dir.c_str()) == INVALID_FILE_ATTRIBUTES ||
        !(GetFileAttributesW(dir.c_str()) & FILE_ATTRIBUTE_DIRECTORY))
        dir = PickFolder(L"Select the game folder to make writable");
    if (dir.empty()) {
        g_instState = INST_FAIL;
        g_instMsg = L"No folder was selected - nothing was changed.";
        return;
    }
    DWORD ra = GetFileAttributesW(dir.c_str());
    if (ra != INVALID_FILE_ATTRIBUTES && (ra & FILE_ATTRIBUTE_READONLY))
        SetFileAttributesW(dir.c_str(), ra & ~FILE_ATTRIBUTE_READONLY);
    int cleared = 0, failed = 0;
    ClearReadOnlyTree(dir, cleared, failed);
    if (failed) {
        g_instState = INST_FAIL;
        g_instMsg = L"Cleared " + std::to_wstring(cleared) + L" read-only flags, but " +
                    std::to_wstring(failed) + L" could not be changed. If the game is in "
                    L"Program Files, run the launcher as administrator and retry, or move "
                    L"the game to a normal folder (e.g. C:\\Games).";
    } else {
        g_instState = INST_DONE;
        g_instMsg = L"<b>Done.</b> Cleared " + std::to_wstring(cleared) +
                    L" read-only flags in<br><code>" + dir + L"</code>";
    }
    Stage((L"I: perms fix cleared=" + std::to_wstring(cleared) +
           L" failed=" + std::to_wstring(failed)).c_str());
}

// 'Install the game now': mount the ISO, copy FIGHTER_ACE_4_2_DELUXE_EDITION's
// CONTENTS to a folder the user picks (Explorer copy with its native progress
// dialog), clear the read-only attributes, and save the path to launcher.ini
// so the launcher can launch from it. No installer is executed.
// Shared tail of the install: mount, copy, unlock, persist, shortcut, login.
// ----------------------------------------------------------------------------
//  L-FIX-11: mirror content validation. An over-quota / broken mirror answers
//  HTTP 200 with an HTML error page (e.g. Google Drive "Quota exceeded"),
//  which aria2 saves as a 2 KB "ISO" with no .aria2 control file - so every
//  later stage sees a "complete" disc. These helpers recognize that garbage.
// ----------------------------------------------------------------------------
static const unsigned long long MIN_ISO_BYTES =
    3ULL * 1024 * 1024 * 1024;   // sanity floor; the real disc is ~4.35 GB

static bool LooksLikeHtml(const std::string& head) {
    size_t i = 0;
    if (head.size() >= 3 && (unsigned char)head[0] == 0xEF &&
        (unsigned char)head[1] == 0xBB && (unsigned char)head[2] == 0xBF)
        i = 3;                                          // UTF-8 BOM
    while (i < head.size() && (unsigned char)head[i] <= ' ') ++i;
    std::string s = head.substr(i, 16);
    std::transform(s.begin(), s.end(), s.begin(), ::tolower);
    return s.rfind("<!doctype", 0) == 0 || s.rfind("<html", 0) == 0 ||
           s.rfind("<head", 0) == 0     || s.rfind("<?xml", 0) == 0;
}

// Is the file on disk plausibly the game ISO (and not a saved error page)?
static bool IsIsoFileValid(const std::wstring& path, std::wstring* why = nullptr) {
    HANDLE h = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
                           OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) {
        if (why) *why = L"the file could not be read";
        return false;
    }
    LARGE_INTEGER sz; sz.QuadPart = 0;
    GetFileSizeEx(h, &sz);
    char b[512]; DWORD got = 0;
    ReadFile(h, b, sizeof b, &got, nullptr);
    CloseHandle(h);
    if (LooksLikeHtml(std::string(b, got))) {
        if (why) *why = L"it is a web page, not a disc image";
        return false;
    }
    if ((unsigned long long)sz.QuadPart < MIN_ISO_BYTES) {
        if (why) *why = L"it is far too small (" +
                        std::to_wstring((unsigned long long)sz.QuadPart) + L" bytes)";
        return false;
    }
    if (why) why->clear();
    return true;
}

static void DoCopyInstall(const std::wstring& target) {
    std::wstring iso = g_cfg.downloadDir + L"\\" + g_cfg.isoName;
    g_instState = INST_RUNNING;
    g_instMsg = L"Mounting the ISO...";
    wchar_t drive = MountIso(iso);
    if (!drive) {
        g_instState = INST_FAIL;
        g_instMsg = L"Could not mount the ISO. You can mount it manually "
                    L"(double-click the file) and copy the game folder yourself.";
        Stage(L"I: mount failed");
        return;
    }
    g_mountedIso = iso;
    Stage((std::wstring(L"I: mounted at ") + drive).c_str());

    std::wstring src = std::wstring(1, drive) + L":\\" + g_cfg.isoGameFolder;
    DWORD sa = GetFileAttributesW(src.c_str());
    if (sa == INVALID_FILE_ATTRIBUTES || !(sa & FILE_ATTRIBUTE_DIRECTORY)) {
        DismountIso();
        g_instState = INST_FAIL;
        g_instMsg = L"The folder <code>" + g_cfg.isoGameFolder +
                    L"</code> was not found on the disc.";
        Stage(L"I: iso game folder missing");
        return;
    }

    g_instMsg = L"Copying game files to<br><code>" + target + L"</code>";
    Stage((L"I: copy " + src + L" -> " + target).c_str());

    // Explorer copy (native progress dialog). pFrom/pTo are double-NUL lists.
    std::wstring fromS = src + L"\\*";
    std::vector<wchar_t> from(fromS.begin(), fromS.end());
    from.push_back(0); from.push_back(0);
    std::vector<wchar_t> to(target.begin(), target.end());
    to.push_back(0); to.push_back(0);
    SHFILEOPSTRUCTW op; ZeroMemory(&op, sizeof op);
    op.hwnd = g_mainWnd;
    op.wFunc = FO_COPY;
    op.pFrom = from.data();
    op.pTo = to.data();
    op.fFlags = FOF_NOCONFIRMATION | FOF_NOCONFIRMMKDIR;
    int rc = SHFileOperationW(&op);
    DismountIso();
    if (rc != 0 || op.fAnyOperationsAborted) {
        g_instState = INST_FAIL;
        g_instMsg = op.fAnyOperationsAborted
            ? std::wstring(L"The copy was cancelled.")
            : L"The copy failed (code " + std::to_wstring(rc) +
              L"). Pick a folder you can write to (avoid Program Files).";
        Stage((L"I: copy failed rc=" + std::to_wstring(rc)).c_str());
        return;
    }

    // The disc image's files arrive read-only - make the tree writable.
    DWORD ra = GetFileAttributesW(target.c_str());
    if (ra != INVALID_FILE_ATTRIBUTES && (ra & FILE_ATTRIBUTE_READONLY))
        SetFileAttributesW(target.c_str(), ra & ~FILE_ATTRIBUTE_READONLY);
    int cleared = 0, failed = 0;
    ClearReadOnlyTree(target, cleared, failed);

    // L-FIX-5e: the Deluxe ISO ships FA42R.EXE (release) / FA42B / FA42D
    // rather than FA.exe - detect what actually landed and persist it as
    // ClientExe so the launch fallback and the shortcut icon are correct.
    {
        const wchar_t* exes[] = { L"FA42R.EXE", L"FA.exe", L"FA42B.EXE", L"FA42D.EXE" };
        for (auto e : exes)
            if (FileExists(target + L"\\" + e)) { g_cfg.clientExe = e; break; }
    }
    bool saved = SaveInstallToIni(target, g_cfg.clientExe);
    g_cfg.gameInstalled = true;
    // L-FIX-10: with sharing gone, the 4.4 GB download is pure disk waste
    // once installed - remove it (and any control file) to free space.
    DeleteFileW(iso.c_str());
    DeleteFileW((iso + L".aria2").c_str());
    Stage(L"I: download files removed after install");
    g_instState = INST_DONE;
    g_instMsg = L"<b>Installed.</b> Game files copied to<br><code>" + target +
                L"</code><br>Cleared " + std::to_wstring(cleared) + L" read-only flags" +
                (failed ? L" (" + std::to_wstring(failed) + L" could not be changed)"
                        : std::wstring()) +
                (saved ? L". Path saved to launcher settings."
                       : L". <span style='color:#a00'>Could not write launcher.ini - "
                         L"set GameDir, ClientExe and GameInstalled=true there "
                         L"manually.</span>");
    Stage((L"I: install done, cleared=" + std::to_wstring(cleared) +
           L" failed=" + std::to_wstring(failed)).c_str());

    // L-FIX-5d: finish the journey without further clicks - desktop shortcut,
    // a single confirmation, then straight to the login page.
    bool lnkOk = CreateDesktopShortcut(target);
    std::wstring info = L"Fighter Ace was installed to:\n" + target + L"\n\n" +
        (lnkOk ? L"A desktop shortcut for the launcher was created."
               : L"(The desktop shortcut could not be created.)") +
        L"\n\nContinuing to the login page.";
    MessageBoxW(g_mainWnd, info.c_str(), L"FA Secure Launcher",
                MB_OK | MB_ICONINFORMATION);
    if (g_web) {
        BSTR u = SysAllocString(g_cfg.loginUrl.c_str());
        g_web->Navigate(u, nullptr, nullptr, nullptr, nullptr);
        SysFreeString(u);
    }
}

static void StartInstall() {
    if (g_instState == INST_RUNNING) return;   // SHFileOperation pumps messages;
                                               // guard against re-entry
    std::wstring iso = g_cfg.downloadDir + L"\\" + g_cfg.isoName;
    if (!FileExists(iso)) {
        g_instState = INST_FAIL;
        g_instMsg = L"The ISO was not found:<br><code>" + iso + L"</code>";
        return;
    }
    // L-FIX-11: refuse to "install" a saved mirror error page.
    {
        std::wstring why;
        if (!IsIsoFileValid(iso, &why)) {
            DeleteFileW(iso.c_str());
            DeleteFileW((iso + L".aria2").c_str());
            g_instState = INST_FAIL;
            g_instMsg = L"The downloaded file is not the game disc - " + why +
                        L".<br>A mirror served an error page instead of the ISO. "
                        L"The bad file was removed; please run the download again.";
            Stage(L"I: install refused - iso invalid (removed)");
            return;
        }
    }
    // L-FIX-6b2: even without InstallTarget= (e.g. a broken v4.0 install),
    // running from a folder literally named 'launcher' means the game target
    // is our parent directory - use it rather than asking.
    if (g_cfg.installTarget.empty()) {
        std::wstring d = ExeDir();
        size_t slash = d.find_last_of(L"\\/");
        if (slash != std::wstring::npos) {
            std::wstring leaf = d.substr(slash + 1);
            std::transform(leaf.begin(), leaf.end(), leaf.begin(), ::towlower);
            if (leaf == L"launcher") g_cfg.installTarget = d.substr(0, slash);
        }
    }
    // L-FIX-6b: setup already chose the game folder - use it without asking.
    if (!g_cfg.installTarget.empty()) {
        std::wstring target = g_cfg.installTarget;
        if (!CreateDirectoryW(target.c_str(), nullptr) &&
            GetLastError() != ERROR_ALREADY_EXISTS) {
            g_instState = INST_FAIL;
            g_instMsg = L"Could not open the game folder chosen at setup:<br><code>" +
                        target + L"</code>";
            return;
        }
        DoCopyInstall(target);
        return;
    }
    std::wstring picked = PickFolder(
        L"Select where to install Fighter Ace (e.g. C:\\Games). A subfolder "
        L"for the game will be created there. Avoid Program Files.");
    if (picked.empty()) {
        g_instState = INST_FAIL;
        g_instMsg = L"No folder was selected - install cancelled.";
        return;
    }
    while (!picked.empty() && (picked.back() == L'\\' || picked.back() == L'/'))
        picked.pop_back();   // "C:\games\" -> "C:\games"

    // L-FIX-5c: never pour game files into a folder that already has other
    // content. Use the selection as-is only if it's already named like the
    // game subfolder, or if it's empty (a folder they just created for this);
    // otherwise create <selection>\<InstallSubdir>.
    std::wstring target;
    {
        std::wstring name = picked;
        size_t slash = name.find_last_of(L"\\/");
        if (slash != std::wstring::npos) name = name.substr(slash + 1);
        std::wstring lowName = name, lowSub = g_cfg.installSubdir;
        std::transform(lowName.begin(), lowName.end(), lowName.begin(), ::towlower);
        std::transform(lowSub.begin(),  lowSub.end(),  lowSub.begin(),  ::towlower);
        if (lowName == lowSub || IsDirEmpty(picked)) target = picked;
        else                                         target = picked + L"\\" + g_cfg.installSubdir;
    }
    DWORD ta = GetFileAttributesW(target.c_str());
    if (ta != INVALID_FILE_ATTRIBUTES && (ta & FILE_ATTRIBUTE_DIRECTORY) &&
        !IsDirEmpty(target)) {
        if (MessageBoxW(g_mainWnd,
                (L"The folder already exists and contains files:\n\n" + target +
                 L"\n\nCopy the game files into it anyway (reinstall/repair)?").c_str(),
                L"FA Secure Launcher", MB_YESNO | MB_ICONQUESTION) != IDYES) {
            g_instState = INST_FAIL;
            g_instMsg = L"Install cancelled - the target folder was not empty.";
            return;
        }
    }
    if (!CreateDirectoryW(target.c_str(), nullptr) &&
        GetLastError() != ERROR_ALREADY_EXISTS) {
        g_instState = INST_FAIL;
        g_instMsg = L"Could not create the game folder:<br><code>" + target +
                    L"</code><br>Pick a location you can write to.";
        return;
    }

    DoCopyInstall(target);
}

// ----------------------------------------------------------------------------
//  L-FIX-10: mirror-list HTTP download - the one and only source. mirrors.txt
//  is fetched from the project repo at download start; entries are resolved
//  (Google Drive links get the large-file confirm interstitial resolved to a
//  direct drive.usercontent URL) and fed to the running aria2 via addUri.
//  A dead mirror advances to the next entry; an exhausted list is a hard
//  stop with a clear message.
// ----------------------------------------------------------------------------
static int  g_mirrorIndex = -1;              // -1 = not started; first switch picks entry 0
static bool g_mirrorsExhausted = false;
static std::vector<std::string> g_mirrors;   // parsed mirrors.txt (utf-8)
static std::wstring g_mirrorHost;            // for the progress page

// Small HTTPS/HTTP GET via WinINet (redirects followed). Body capped.
// L-FIX-11: optionally reports Content-Length (queried as a string - the
// DWORD form would overflow on a 4.35 GB disc). 0 = unknown/absent.
static std::string WinInetGet(const std::wstring& url, DWORD maxBytes,
                              std::wstring* contentType,
                              unsigned long long* contentLen = nullptr) {
    std::string out;
    if (contentType) contentType->clear();
    if (contentLen)  *contentLen = 0;
    HINTERNET hNet = InternetOpenW(L"FALauncher", INTERNET_OPEN_TYPE_PRECONFIG,
                                   nullptr, nullptr, 0);
    if (!hNet) return out;
    DWORD to = 15000;
    InternetSetOptionW(hNet, INTERNET_OPTION_CONNECT_TIMEOUT, &to, sizeof to);
    InternetSetOptionW(hNet, INTERNET_OPTION_RECEIVE_TIMEOUT, &to, sizeof to);
    HINTERNET hUrl = InternetOpenUrlW(hNet, url.c_str(), nullptr, 0,
                                      INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE |
                                      INTERNET_FLAG_SECURE, 0);
    if (hUrl) {
        if (contentType) {
            wchar_t ct[128] = L""; DWORD cl = sizeof ct;
            if (HttpQueryInfoW(hUrl, HTTP_QUERY_CONTENT_TYPE, ct, &cl, nullptr))
                *contentType = ct;
        }
        if (contentLen) {
            wchar_t lb[64] = L""; DWORD ls = sizeof lb;
            if (HttpQueryInfoW(hUrl, HTTP_QUERY_CONTENT_LENGTH, lb, &ls, nullptr))
                *contentLen = wcstoull(lb, nullptr, 10);
        }
        char b[4096]; DWORD got = 0;
        while (out.size() < maxBytes && InternetReadFile(hUrl, b, sizeof b, &got) && got > 0)
            out.append(b, got);
        InternetCloseHandle(hUrl);
    }
    InternetCloseHandle(hNet);
    return out;
}

// ----------------------------------------------------------------------------
//  L-FIX-12: Mega.nz mirror support. Mega files are end-to-end encrypted:
//  the fragment after '#' in a share link is the 32-byte file key (base64url)
//  and the server only ever serves AES-128-CTR ciphertext. Pipeline:
//    1. ResolveMegaLink: POST {"a":"g","g":1,"p":<handle>} to the Mega API,
//       which answers a temporary direct URL to the ciphertext (plain HTTPS,
//       range-resumable - aria2 handles it like any mirror).
//    2. aria2 downloads to <iso>.megaenc (ciphertext == plaintext size).
//    3. MegaDecryptThread streams .megaenc -> <iso>.megadec with AES-CTR
//       (key = raw[0..15] XOR raw[16..31], nonce = raw[16..23], counter =
//       big-endian block index), verifies the ISO9660 'CD001' signature at
//       0x8000, then swaps .megadec into place as the ISO and deletes the
//       ciphertext. The .megadec size doubles as the resume marker: after a
//       crash, decryption truncates to a chunk boundary and continues -
//       the ciphertext is never modified, so resume is always safe.
// ----------------------------------------------------------------------------
static bool               g_megaActive = false;   // current mirror is a Mega link
static std::vector<BYTE>  g_megaKey;              // raw 32-byte decoded key
enum { DEC_NONE = 0, DEC_RUNNING, DEC_DONE, DEC_FAIL };
static volatile LONG      g_decState = DEC_NONE;
static volatile LONGLONG  g_decDone  = 0;
static volatile LONGLONG  g_decTotal = 0;
static std::wstring       g_decErr;               // set by thread before DEC_FAIL

static std::wstring MegaEncPath() { return g_cfg.downloadDir + L"\\" + g_cfg.isoName + L".megaenc"; }
static std::wstring MegaDecPath() { return g_cfg.downloadDir + L"\\" + g_cfg.isoName + L".megadec"; }

// POST a JSON body over HTTPS (Mega API). Empty string on any failure.
static std::string WinInetPostJson(const std::wstring& host, const std::wstring& path,
                                   const std::string& body, DWORD maxBytes) {
    std::string out;
    HINTERNET hNet = InternetOpenW(L"FALauncher", INTERNET_OPEN_TYPE_PRECONFIG,
                                   nullptr, nullptr, 0);
    if (!hNet) return out;
    DWORD to = 15000;
    InternetSetOptionW(hNet, INTERNET_OPTION_CONNECT_TIMEOUT, &to, sizeof to);
    InternetSetOptionW(hNet, INTERNET_OPTION_RECEIVE_TIMEOUT, &to, sizeof to);
    HINTERNET hCon = InternetConnectW(hNet, host.c_str(), INTERNET_DEFAULT_HTTPS_PORT,
                                      nullptr, nullptr, INTERNET_SERVICE_HTTP, 0, 0);
    if (hCon) {
        HINTERNET hReq = HttpOpenRequestW(hCon, L"POST", path.c_str(), nullptr, nullptr,
                                          nullptr, INTERNET_FLAG_SECURE |
                                          INTERNET_FLAG_RELOAD |
                                          INTERNET_FLAG_NO_CACHE_WRITE, 0);
        if (hReq) {
            const wchar_t* hdr = L"Content-Type: application/json\r\n";
            if (HttpSendRequestW(hReq, hdr, (DWORD)-1L,
                                 (LPVOID)body.data(), (DWORD)body.size())) {
                char b[4096]; DWORD got = 0;
                while (out.size() < maxBytes &&
                       InternetReadFile(hReq, b, sizeof b, &got) && got > 0)
                    out.append(b, got);
            }
            InternetCloseHandle(hReq);
        }
        InternetCloseHandle(hCon);
    }
    InternetCloseHandle(hNet);
    return out;
}

static std::vector<BYTE> B64UrlDecode(const std::string& in) {
    auto val = [](char c) -> int {
        if (c >= 'A' && c <= 'Z') return c - 'A';
        if (c >= 'a' && c <= 'z') return c - 'a' + 26;
        if (c >= '0' && c <= '9') return c - '0' + 52;
        if (c == '+' || c == '-') return 62;
        if (c == '/' || c == '_') return 63;
        return -1;                                   // padding / junk: skipped
    };
    std::vector<BYTE> out; int acc = 0, bits = 0;
    for (char c : in) {
        int v = val(c);
        if (v < 0) continue;
        acc = (acc << 6) | v; bits += 6;
        if (bits >= 8) { bits -= 8; out.push_back((BYTE)((acc >> bits) & 0xFF)); }
    }
    return out;
}

// AES-128 in CTR mode via CNG (CNG has no native CTR: ECB-encrypt the
// counter blocks, XOR the keystream into the data). offset must be
// 16-byte aligned (all our chunks are).
struct AesCtx {
    BCRYPT_ALG_HANDLE alg = nullptr;
    BCRYPT_KEY_HANDLE key = nullptr;
    bool Init(const BYTE k[16]) {
        if (!NT_SUCCESS(BCryptOpenAlgorithmProvider(&alg, BCRYPT_AES_ALGORITHM,
                                                    nullptr, 0))) return false;
        if (!NT_SUCCESS(BCryptSetProperty(alg, BCRYPT_CHAINING_MODE,
                                          (PUCHAR)BCRYPT_CHAIN_MODE_ECB,
                                          sizeof(BCRYPT_CHAIN_MODE_ECB), 0))) return false;
        return NT_SUCCESS(BCryptGenerateSymmetricKey(alg, &key, nullptr, 0,
                                                     (PUCHAR)k, 16, 0));
    }
    ~AesCtx() {
        if (key) BCryptDestroyKey(key);
        if (alg) BCryptCloseAlgorithmProvider(alg, 0);
    }
};

static bool CtrApply(AesCtx& ctx, const BYTE nonce[8],
                     unsigned long long offset, BYTE* data, size_t len,
                     std::vector<BYTE>& ks /* scratch, reused per chunk */) {
    size_t blocks = (len + 15) / 16;
    ks.resize(blocks * 16);
    unsigned long long ctr = offset / 16;
    for (size_t i = 0; i < blocks; ++i) {           // counter block: nonce || be64(ctr)
        BYTE* c = &ks[i * 16];
        memcpy(c, nonce, 8);
        unsigned long long n = ctr + i;
        for (int b = 0; b < 8; ++b) c[8 + b] = (BYTE)(n >> (56 - 8 * b));
    }
    ULONG res = 0;                                   // in-place ECB -> keystream
    if (!NT_SUCCESS(BCryptEncrypt(ctx.key, ks.data(), (ULONG)ks.size(), nullptr,
                                  nullptr, 0, ks.data(), (ULONG)ks.size(), &res, 0)))
        return false;
    for (size_t i = 0; i < len; ++i) data[i] ^= ks[i];
    return true;
}

// Turn a Mega share link into a temporary direct ciphertext URL and arm the
// decryption state. Supports mega.nz/file/<handle>#<key> and the legacy
// mega.nz/#!<handle>!<key>. Empty string = unusable (bad link, over quota,
// API error) - the mirror pick loop then just moves on.
static std::string ResolveMegaLink(const std::string& raw) {
    g_megaActive = false;
    std::string h, k;
    size_t p = raw.find("/file/");
    if (p != std::string::npos) {
        size_t s = p + 6, e = raw.find('#', s);
        if (e == std::string::npos) return "";
        h = raw.substr(s, e - s); k = raw.substr(e + 1);
    } else if ((p = raw.find("#!")) != std::string::npos) {
        size_t s = p + 2, e = raw.find('!', s);
        if (e == std::string::npos) return "";
        h = raw.substr(s, e - s); k = raw.substr(e + 1);
    } else return "";
    size_t stop = k.find_first_not_of(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_");
    if (stop != std::string::npos) k = k.substr(0, stop);
    std::vector<BYTE> key = B64UrlDecode(k);
    if (key.size() != 32) return "";                 // file keys are 32 bytes
    std::string body = "[{\"a\":\"g\",\"g\":1,\"p\":\"" + h + "\"}]";
    std::string rsp = WinInetPostJson(L"g.api.mega.co.nz",
        L"/cs?id=" + std::to_wstring(GetTickCount()) + L"&lang=en", body, 65536);
    std::string g = JStr(rsp, "g");
    {   // JSON may escape slashes
        std::string u; u.reserve(g.size());
        for (size_t i = 0; i < g.size(); ++i) {
            if (g[i] == '\\' && i + 1 < g.size() && g[i + 1] == '/') continue;
            u += g[i];
        }
        g = u;
    }
    if (g.rfind("http", 0) != 0) return "";          // over quota / error code
    g_megaKey    = key;
    g_megaActive = true;
    return g;
}

static DWORD WINAPI MegaDecryptThread(LPVOID) {
    const std::wstring enc = MegaEncPath(), dec = MegaDecPath();
    const std::wstring iso = g_cfg.downloadDir + L"\\" + g_cfg.isoName;
    const DWORD CHUNK = 4 * 1024 * 1024;
    std::wstring err;
    do {
        // Derive the AES key + CTR nonce from the raw 32-byte file key.
        if (g_megaKey.size() != 32) { err = L"no key"; break; }
        BYTE k[16], nonce[8];
        for (int i = 0; i < 16; ++i) k[i] = g_megaKey[i] ^ g_megaKey[i + 16];
        memcpy(nonce, &g_megaKey[16], 8);
        AesCtx ctx;
        if (!ctx.Init(k)) { err = L"crypto init failed"; break; }

        HANDLE hEnc = CreateFileW(enc.c_str(), GENERIC_READ, FILE_SHARE_READ,
                                  nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (hEnc == INVALID_HANDLE_VALUE) { err = L"cannot open ciphertext"; break; }
        LARGE_INTEGER total; total.QuadPart = 0;
        GetFileSizeEx(hEnc, &total);
        g_decTotal = total.QuadPart;

        HANDLE hDec = CreateFileW(dec.c_str(), GENERIC_READ | GENERIC_WRITE, 0,
                                  nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (hDec == INVALID_HANDLE_VALUE) {
            CloseHandle(hEnc); err = L"cannot create output"; break;
        }
        // Resume: the plaintext size IS the progress marker. Truncate any
        // partial trailing chunk and continue from the boundary.
        LARGE_INTEGER have; have.QuadPart = 0;
        GetFileSizeEx(hDec, &have);
        unsigned long long off = ((unsigned long long)have.QuadPart / CHUNK) * CHUNK;
        LARGE_INTEGER li; li.QuadPart = (LONGLONG)off;
        SetFilePointerEx(hDec, li, nullptr, FILE_BEGIN); SetEndOfFile(hDec);
        SetFilePointerEx(hEnc, li, nullptr, FILE_BEGIN);
        g_decDone = (LONGLONG)off;

        std::vector<BYTE> buf(CHUNK), ks;
        bool ok = true;
        while (off < (unsigned long long)total.QuadPart) {
            DWORD got = 0;
            if (!ReadFile(hEnc, buf.data(), CHUNK, &got, nullptr) || got == 0) {
                err = L"read failed"; ok = false; break;
            }
            if (!CtrApply(ctx, nonce, off, buf.data(), got, ks)) {
                err = L"decrypt failed"; ok = false; break;
            }
            DWORD wr = 0;
            if (!WriteFile(hDec, buf.data(), got, &wr, nullptr) || wr != got) {
                err = L"write failed (disk full?)"; ok = false; break;
            }
            off += got;
            g_decDone = (LONGLONG)off;
        }
        // ISO9660 sanity: sector 16 (0x8000) must open with 0x01 'CD001'.
        if (ok && total.QuadPart > 0x8008) {
            BYTE sig[6] = {0};
            li.QuadPart = 0x8000; DWORD got = 0;
            SetFilePointerEx(hDec, li, nullptr, FILE_BEGIN);
            ReadFile(hDec, sig, 6, &got, nullptr);
            if (got != 6 || sig[0] != 0x01 || memcmp(sig + 1, "CD001", 5) != 0) {
                err = L"decrypted data is not an ISO image (wrong key?)";
                ok = false;
            }
        }
        CloseHandle(hEnc); CloseHandle(hDec);
        if (!ok) break;
        // Swap into place; the ciphertext and any stale ISO artifacts go.
        DeleteFileW(iso.c_str());
        DeleteFileW((iso + L".aria2").c_str());
        if (!MoveFileW(dec.c_str(), iso.c_str())) { err = L"rename failed"; break; }
        DeleteFileW(enc.c_str());
        DeleteFileW((enc + L".aria2").c_str());
        InterlockedExchange(&g_decState, DEC_DONE);
        return 0;
    } while (false);
    g_decErr = err;
    InterlockedExchange(&g_decState, DEC_FAIL);
    return 0;
}

static void StartMegaDecrypt() {
    if (InterlockedCompareExchange(&g_decState, DEC_RUNNING, DEC_NONE) != DEC_NONE)
        return;                                      // already running/done
    g_decErr.clear();
    HANDLE t = CreateThread(nullptr, 0, MegaDecryptThread, nullptr, 0, nullptr);
    if (t) CloseHandle(t);
    else   InterlockedExchange(&g_decState, DEC_FAIL);
}

// Resolve a mirrors.txt entry to a URL aria2 can download directly.
// Google Drive links get the large-file confirm interstitial resolved.
static std::string ResolveMirror(const std::string& raw) {
    // L-FIX-12: Mega share links go through the API + decryption pipeline.
    if (raw.find("mega.nz") != std::string::npos ||
        raw.find("mega.co.nz") != std::string::npos)
        return ResolveMegaLink(raw);
    g_megaActive = false;                            // plain / Drive mirror
    if (raw.find("drive.google.com") == std::string::npos &&
        raw.find("drive.usercontent.google.com") == std::string::npos)
        return raw;
    // extract the file id: /d/<ID>/ or id=<ID>
    std::string id;
    size_t p = raw.find("/d/");
    if (p != std::string::npos) {
        size_t s2 = p + 3, e = raw.find_first_of("/?&", s2);
        id = raw.substr(s2, e == std::string::npos ? std::string::npos : e - s2);
    } else if ((p = raw.find("id=")) != std::string::npos) {
        size_t s2 = p + 3, e = raw.find_first_of("&", s2);
        id = raw.substr(s2, e == std::string::npos ? std::string::npos : e - s2);
    }
    if (id.empty()) return raw;
    std::string base = "https://drive.usercontent.google.com/download?id=" + id +
                       "&export=download&confirm=t";
    // Peek: large files answer with an HTML confirm page carrying a uuid field.
    std::wstring ct;
    std::string body = WinInetGet(Utf8ToWide(base), 131072, &ct);
    if (ct.find(L"text/html") != std::wstring::npos) {
        const std::string pat = "name=\"uuid\" value=\"";
        size_t u = body.find(pat);
        if (u != std::string::npos) {
            u += pat.size();
            size_t e = body.find('"', u);
            if (e != std::string::npos)
                return base + "&uuid=" + body.substr(u, e - u);
        }
    }
    return base;   // small file / already direct
}

// L-FIX-11: the pre-flight check. Read the headers + first bytes of the
// resolved URL and reject anything that is HTML (an over-quota / error page)
// or that announces a Content-Length far too small to be the game disc.
// A rejected mirror is skipped; the caller moves on to the next entry.
static bool ProbeMirrorUrl(const std::string& url, std::wstring& why) {
    std::wstring ct; unsigned long long clen = 0;
    std::string head = WinInetGet(Utf8ToWide(url), 512, &ct, &clen);
    if (head.empty()) { why = L"no response"; return false; }
    std::wstring lct = ct;
    std::transform(lct.begin(), lct.end(), lct.begin(), ::towlower);
    if (lct.find(L"text/html") != std::wstring::npos || LooksLikeHtml(head)) {
        why = L"serves a web page (over quota / error), not the ISO";
        return false;
    }
    if (clen > 0 && clen < MIN_ISO_BYTES) {
        why = L"file too small (" + std::to_wstring(clen) + L" bytes)";
        return false;
    }
    why.clear();
    return true;
}

static std::string CurrentActiveGid() {
    std::string rsp = RpcCall(RpcMethod("aria2.tellActive"));
    return JStr(rsp, "gid");
}

// Move to the next mirror (or start with the first one).
static void SwitchToNextMirror(bool firstStart) {
    if (g_mirrorsExhausted) return;
    if (g_mirrors.empty()) {
        std::string txt = WinInetGet(g_cfg.mirrorListUrl, 65536, nullptr);
        std::stringstream ls(txt); std::string line;
        while (std::getline(ls, line)) {
            while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
            size_t b = line.find_first_not_of(" \t");
            if (b == std::string::npos) continue;
            line = line.substr(b);
            if (line.empty() || line[0] == '#' || line[0] == ';') continue;
            if (line.rfind("http", 0) == 0) g_mirrors.push_back(line);
        }
        Stage((L"M0: mirrors.txt entries=" + std::to_wstring(g_mirrors.size())).c_str());
    }
    // L-FIX-11: pick the next mirror that actually serves the ISO. Probing
    // has no side effects on aria2, so it happens before the current
    // transfer is dropped; a rejected mirror is logged and skipped.
    std::string url;
    for (;;) {
        ++g_mirrorIndex;
        if (g_mirrorIndex >= (int)g_mirrors.size()) {
            // L-FIX-10: mirrors are the ONLY source now - out of mirrors means
            // the download cannot proceed. Say so on the page.
            g_mirrorsExhausted = true;
            g_mirrorHost.clear();
            Stage(L"M!: mirrors exhausted - no sources");
            return;
        }
        url = ResolveMirror(g_mirrors[g_mirrorIndex]);
        if (url.empty()) {
            Stage((L"M!: mirror #" + std::to_wstring(g_mirrorIndex) +
                   L" rejected - unresolvable (bad link / over quota)").c_str());
            continue;
        }
        std::wstring why;
        if (ProbeMirrorUrl(url, why)) break;
        Stage((L"M!: mirror #" + std::to_wstring(g_mirrorIndex) +
               L" rejected - " + why).c_str());
    }
    // L-FIX-12: fresh source, fresh decrypt state (never while a decrypt
    // thread owns the files - rotation can't happen then anyway).
    if (g_decState != DEC_RUNNING) {
        InterlockedExchange(&g_decState, DEC_NONE);
        g_decDone = g_decTotal = 0;
    }

    // Drop any current transfer and its control file (fresh source next).
    // its piece-based control file, which an HTTP download cannot reuse.
    std::string gid = CurrentActiveGid();
    if (!gid.empty())
        RpcCall("{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"aria2.forceRemove\","
                "\"params\":[\"token:" + WideToUtf8(g_rpcSecret) + "\",\"" + gid + "\"]}");
    std::wstring iso = g_cfg.downloadDir + L"\\" + g_cfg.isoName;
    DeleteFileW((iso + L".aria2").c_str());
    DeleteFileW((MegaEncPath() + L".aria2").c_str());   // L-FIX-12: same rule
    if (firstStart) {
        DeleteFileW(iso.c_str());   // clear any stale 0-byte stub
        DeleteFileW(MegaEncPath().c_str());             // L-FIX-12: stale temps
        DeleteFileW(MegaDecPath().c_str());
    }

    // host for the UI
    {
        size_t hs = url.find("://");
        std::string host = hs == std::string::npos ? url : url.substr(hs + 3);
        size_t he = host.find_first_of("/:");
        if (he != std::string::npos) host = host.substr(0, he);
        g_mirrorHost = Utf8ToWide(host);
    }
    // L-FIX-12: Mega serves ciphertext - it downloads under a temp name and
    // only becomes the ISO after decryption.
    std::wstring outName = g_cfg.isoName + (g_megaActive ? L".megaenc" : L"");
    // JSON: backslashes in dir must be escaped
    // (WideToUtf8 of a Windows path contains single backslashes).
    auto esc = [](std::string in) {
        std::string o; for (char c : in) { if (c == '\\') o += "\\\\"; else o += c; } return o; };
    std::string body =
        "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"aria2.addUri\",\"params\":[\"token:" +
        WideToUtf8(g_rpcSecret) + "\",[\"" + esc(url) + "\"],{" +
        "\"dir\":\"" + esc(WideToUtf8(g_cfg.downloadDir)) + "\"," +
        "\"out\":\"" + esc(WideToUtf8(outName)) + "\"," +
        "\"continue\":\"true\",\"split\":\"8\",\"max-connection-per-server\":\"8\"," +
        "\"max-tries\":\"3\"}]}";
    RpcCall(body);
    Stage((L"M1: mirror #" + std::to_wstring(g_mirrorIndex) + L" " + g_mirrorHost +
           (g_megaActive ? L" (mega, encrypted)" : L"")).c_str());
}

// 2 s timer tick while in download mode: read status over RPC, repaint the
// progress page. Repaints ONLY while the browser is still on about:blank, so
// the user can click through to the login page and log in mid-download.
static void PollDownload() {
    if (!g_web) return;
    {   // are we still on the progress page?
        BSTR loc = nullptr; bool onBlank = false;
        if (SUCCEEDED(g_web->get_LocationURL(&loc)) && loc) {
            std::wstring l = loc; SysFreeString(loc);
            onBlank = (l.find(L"about:blank") != std::wstring::npos);
        }
        if (!onBlank) return;
    }

    std::string rsp = RpcCall(RpcMethod("aria2.tellActive"));
    bool up = !rsp.empty();
    unsigned long long done = 0, total = 0, dspd = 0;
    std::string status;
    if (up && rsp.find("\"gid\"") != std::string::npos) {
        done     = strtoull(JStr(rsp, "completedLength").c_str(), nullptr, 10);
        total    = strtoull(JStr(rsp, "totalLength").c_str(), nullptr, 10);
        dspd     = strtoull(JStr(rsp, "downloadSpeed").c_str(), nullptr, 10);
        status   = JStr(rsp, "status");
    } else if (up) {
        // nothing active: a plain-HTTP download that finished lands in stopped
        std::string body = "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"aria2.tellStopped\","
                           "\"params\":[\"token:" + WideToUtf8(g_rpcSecret) + "\",0,8]}";
        std::string st = RpcCall(body);
        if (st.find("\"complete\"") != std::string::npos) {
            status = "complete";
            done = total = strtoull(JStr(st, "totalLength").c_str(), nullptr, 10);
        } else if (g_mirrorIndex >= 0 && st.find("\"error\"") != std::string::npos) {
            // L-FIX-9: the current mirror died - move to the next one.
            SwitchToNextMirror(false);
        }
    }

    double pct = total ? (100.0 * (double)done / (double)total) : 0.0;
    bool finished = (total > 0 && done >= total) || status == "complete";
    // L-FIX-12: a finished Mega transfer is the ENCRYPTED image. Decrypt it
    // before anything downstream may treat it as the disc.
    std::wstring decNote;
    if (finished && g_megaActive) {
        LONG ds = g_decState;
        if (ds == DEC_DONE) {
            g_megaActive = false;          // ISO swapped in - validate below
        } else if (ds == DEC_FAIL) {
            Stage((L"M!: mega decrypt failed - " + g_decErr + L"; next mirror").c_str());
            DeleteFileW(MegaEncPath().c_str());
            DeleteFileW(MegaDecPath().c_str());
            InterlockedExchange(&g_decState, DEC_NONE);
            SwitchToNextMirror(false);
            finished = false; done = total = 0; pct = 0.0; status.clear();
        } else {
            if (ds == DEC_NONE) StartMegaDecrypt();
            finished = false;              // not a disc yet
            LONGLONG dd = g_decDone, dt = g_decTotal;
            double dp = dt ? (100.0 * (double)dd / (double)dt) : 0.0;
            wchar_t dpb[16]; swprintf(dpb, 16, L"%.1f", dp);
            decNote = L"Decrypting the disc image... <b>" + std::wstring(dpb) +
                      L"%</b> (" + FmtGB((unsigned long long)dd) + L" / " +
                      FmtGB((unsigned long long)dt) + L")";
        }
    }
    // L-FIX-11: a "complete" download that is actually a saved HTML error
    // page (the mirror went over quota) is garbage - drop it and move to
    // the next mirror instead of offering to install it.
    if (finished) {
        std::wstring isoPath = g_cfg.downloadDir + L"\\" + g_cfg.isoName, why;
        if (!IsIsoFileValid(isoPath, &why)) {
            Stage((L"M!: finished file invalid - " + why + L"; next mirror").c_str());
            DeleteFileW(isoPath.c_str());
            SwitchToNextMirror(false);
            finished = false;
            done = total = 0; pct = 0.0; status.clear();
        }
    }
    // L-FIX-5d: the moment a download WE WATCHED finishes, open the install
    // dialog automatically (once). A pre-completed ISO doesn't trigger this -
    // the startup offer handles that case.
    if (!finished && up) g_sawUnfinished = true;
    if (finished && g_sawUnfinished && !g_autoInstall && g_instState == INST_NONE) {
        g_autoInstall = true;
        if (g_mainWnd) PostMessageW(g_mainWnd, WM_DO_INSTALL, 0, 0);
    }

    wchar_t pctb[16]; swprintf(pctb, 16, L"%.1f", pct);

    std::wstring h;
    h += L"<div style='font-family:Segoe UI,Arial,sans-serif;padding:20px;color:#222'>";
    h += L"<h2 style='margin-top:0'>Fighter Ace 4.2 Deluxe Edition</h2>";
    if (!up) {
        h += L"<p>Starting the transfer engine...</p>";
    } else {
        h += L"<div style='border:1px solid #999;background:#eee;width:100%;height:22px'>"
             L"<div style='background:#2e7d32;height:22px;width:" + std::wstring(pctb) + L"%'></div></div>";
        h += L"<p><b>" + std::wstring(pctb) + L"%</b> &nbsp; " + FmtGB(done) + L" / " + FmtGB(total) + L"</p>";
        if (finished) {
            h += L"<p><b>Download complete.</b></p>";
            // L-FIX-5: install controls
            h += L"<hr>";
            switch (g_instState) {
            case INST_NONE:
                h += L"<p><a href='" + MakeAbsolute(L"/falauncher-install") +
                     L"'><b>Install the game now &raquo;</b></a></p>";
                break;
            case INST_RUNNING:
                h += L"<p>" + g_instMsg + L"</p>";
                break;
            case INST_DONE:
                h += L"<p>" + g_instMsg + L"</p>";
                h += L"<p style='color:#666'>If your account's game path on the website "
                     L"points elsewhere, update it to this folder's FA.exe.</p>";
                break;
            case INST_FAIL:
                h += L"<p style='color:#a00'>" + g_instMsg + L"</p>";
                h += L"<p><a href='" + MakeAbsolute(L"/falauncher-install") +
                     L"'>Run the installer again</a> &nbsp;|&nbsp; <a href='" +
                     MakeAbsolute(L"/falauncher-fixperms") +
                     L"'>Fix folder permissions only</a></p>";
                break;
            }
        } else {
            if (!decNote.empty())          // L-FIX-12: decrypt phase
                h += L"<p>" + decNote + L"</p>";
            else
                h += L"<p>Source: <b>" + (g_mirrorHost.empty() ? std::wstring(L"...")
                                                                : g_mirrorHost) +
                     L"</b> &nbsp; Down: <b>" + FmtSpeed(dspd) + L"</b></p>";
            if (g_mirrorsExhausted)
                h += L"<p style='color:#a00'><b>No download sources are available "
                     L"right now.</b> Please try again later - the mirror list is "
                     L"updated regularly.</p>";
        }
    }
    h += L"</div>";
    SetBrowserBody(h);
}

static bool ExtractPidFromName(const std::wstring& name, std::wstring& pid) {
    size_t a = name.rfind(L"ticket_");
    if (a == std::wstring::npos) return false;
    size_t start = a + 7;
    size_t b = name.find(L".vr1", start);
    if (b == std::wstring::npos || b <= start) return false;
    pid = name.substr(start, b - start);
    return !pid.empty();
}

static bool LaunchGame(const std::wstring& pid, std::wstring& err,
                       const std::wstring& serverClientPath = L"") {
    // L-FIX-7: since the launcher now installs the game itself, the ini's
    // GameDir/ClientExe (written by the install step) is authoritative - it
    // OVERRIDES the account path stored on the website (X-Game-Client-Path),
    // which may be stale or point at a machine-specific old install. The
    // server header is only a fallback for legacy pilots whose ini has no
    // valid local install.
    std::wstring client, workDir;
    std::wstring iniClient = g_cfg.gameDir + L"\\" + g_cfg.clientExe;
    if (FileExists(iniClient)) {
        client = iniClient;
        workDir = g_cfg.gameDir;
        Stage(L"L2: using ini client path");
    } else if (!serverClientPath.empty()) {
        client = serverClientPath;
        size_t slash = client.find_last_of(L"\\/");
        workDir = (slash == std::wstring::npos) ? g_cfg.gameDir : client.substr(0, slash);
        Stage(L"L2: using server client path");
    } else {
        client = iniClient;   // will produce the clear 'not found' error below
        workDir = g_cfg.gameDir;
    }
    if (!FileExists(client)) { err = L"Game client not found:\n" + client; return false; }

    // L-FIX-3: FA.exe parses its own command line with a naive whitespace split,
    // so a QUOTED path containing spaces still breaks /NET /Name: parsing even
    // though CreateProcess accepts it. Build the command line from the 8.3 short
    // path (no spaces, no quotes needed). If the volume has 8.3 names disabled
    // (GetShortPathName fails or still contains a space), fall back to the old
    // quoted long path. lpApplicationName is now passed explicitly either way,
    // so WHICH exe runs never depends on command-line parsing.
    std::wstring exeForCmd = client;
    {
        wchar_t sp[MAX_PATH * 2];
        DWORD n = GetShortPathNameW(client.c_str(), sp, MAX_PATH * 2);
        if (n > 0 && n < MAX_PATH * 2) exeForCmd = sp;
    }
    std::wstring cmd;
    if (exeForCmd.find(L' ') == std::wstring::npos)
        cmd = exeForCmd + L" /NET /Name:" + pid + L" " + g_cfg.launchArgs;
    else
        cmd = L"\"" + client + L"\" /NET /Name:" + pid + L" " + g_cfg.launchArgs;
    Stage((L"L3: cmd = " + cmd).c_str());

    STARTUPINFOW si; ZeroMemory(&si, sizeof si); si.cb = sizeof si;
    PROCESS_INFORMATION pi; ZeroMemory(&pi, sizeof pi);
    std::vector<wchar_t> buf(cmd.begin(), cmd.end()); buf.push_back(0);
    if (!CreateProcessW(client.c_str(), buf.data(), nullptr, nullptr, FALSE, 0, nullptr,
                        workDir.c_str(), &si, &pi)) {
        wchar_t b2[128]; swprintf(b2, 128, L"CreateProcess failed (error %lu):\n", GetLastError());
        err = std::wstring(b2) + cmd; return false;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return true;
}

// Resolve a possibly-relative navigation URL against the login URL's origin so
// URLDownloadToFile always gets an absolute URL (e.g. "/download" -> "http://host/download").
static std::wstring MakeAbsolute(const std::wstring& url) {
    if (url.rfind(L"http://", 0) == 0 || url.rfind(L"https://", 0) == 0) return url;
    // derive scheme://host[:port] from loginUrl
    std::wstring base = g_cfg.loginUrl;
    size_t scheme = base.find(L"://");
    if (scheme == std::wstring::npos) return url;
    size_t hostStart = scheme + 3;
    size_t pathStart = base.find(L'/', hostStart);
    std::wstring origin = (pathStart == std::wstring::npos) ? base : base.substr(0, pathStart);
    if (!url.empty() && url[0] == L'/') return origin + url;
    return origin + L"/" + url;
}

// Fetch the ticket directly to <GameDir>\ticket.vr1 (uses WinINet cookie jar the
// WebBrowser control shares, so the authenticated /download succeeds), then launch.
// Fetch the ticket via WinINet directly into <GameDir>\ticket.vr1. Reads the PID
// from the response's Content-Disposition (filename="ticket_<pid>.vr1") since the
// /download URL itself carries no PID. WinINet shares the WebBrowser control's
// cookie jar, so the authenticated session carries automatically.
static void DownloadTicketAndLaunch(const std::wstring& rawUrl) {
    if (g_launched || g_handling) return;   // only one path may drive the fetch
    g_handling = true;
    std::wstring url = MakeAbsolute(rawUrl);
    Stage((L"D1: fetch " + url).c_str());

    // dest is decided AFTER we read the server's X-Game-Client-Path header below.
    std::wstring dest;

    // --- crack the URL into host / path / port / scheme ---
    URL_COMPONENTSW uc; ZeroMemory(&uc, sizeof uc); uc.dwStructSize = sizeof uc;
    wchar_t host[256] = L"", path[2048] = L"";
    uc.lpszHostName = host; uc.dwHostNameLength = 255;
    uc.lpszUrlPath = path;  uc.dwUrlPathLength = 2047;
    if (!InternetCrackUrlW(url.c_str(), 0, 0, &uc)) {
        ShowError(L"Could not parse the download URL:\n" + url); g_handling = false; return;
    }
    INTERNET_PORT port = uc.nPort;
    bool https = (uc.nScheme == INTERNET_SCHEME_HTTPS);

    HINTERNET hNet = InternetOpenW(L"FALauncher", INTERNET_OPEN_TYPE_PRECONFIG,
                                   nullptr, nullptr, 0);
    if (!hNet) { ShowError(L"InternetOpen failed."); g_handling = false; return; }

    HINTERNET hCon = InternetConnectW(hNet, host, port, nullptr, nullptr,
                                      INTERNET_SERVICE_HTTP, 0, 0);
    if (!hCon) { InternetCloseHandle(hNet); ShowError(L"InternetConnect failed:\n" + std::wstring(host)); g_handling = false; return; }

    DWORD flags = INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE;
    if (https) flags |= INTERNET_FLAG_SECURE;
    HINTERNET hReq = HttpOpenRequestW(hCon, L"GET", path, nullptr, nullptr, nullptr, flags, 0);
    if (!hReq) { InternetCloseHandle(hCon); InternetCloseHandle(hNet);
                 ShowError(L"HttpOpenRequest failed."); g_handling = false; return; }

    // Attach the WebBrowser control's session cookie for this URL so /download
    // sees us as logged in. (WinINet usually shares the jar, but set it explicitly
    // to be safe against process-isolated cookies.)
    {
        DWORD clen = 0;
        InternetGetCookieExW(url.c_str(), nullptr, nullptr, &clen, INTERNET_COOKIE_HTTPONLY, 0);
        if (clen) {
            std::wstring cookie(clen, L'\0');
            if (InternetGetCookieExW(url.c_str(), nullptr, &cookie[0], &clen,
                                     INTERNET_COOKIE_HTTPONLY, 0)) {
                if (!cookie.empty() && cookie.back() == L'\0') cookie.pop_back();
                std::wstring hdr = L"Cookie: " + cookie + L"\r\n";
                HttpAddRequestHeadersW(hReq, hdr.c_str(), (DWORD)-1,
                                       HTTP_ADDREQ_FLAG_ADD | HTTP_ADDREQ_FLAG_REPLACE);
            }
        }
    }

    if (!HttpSendRequestW(hReq, nullptr, 0, nullptr, 0)) {
        InternetCloseHandle(hReq); InternetCloseHandle(hCon); InternetCloseHandle(hNet);
        ShowError(L"HttpSendRequest failed for:\n" + url); g_handling = false; return;
    }

    // Check HTTP status.
    DWORD status = 0, slen = sizeof(status);
    HttpQueryInfoW(hReq, HTTP_QUERY_STATUS_CODE | HTTP_QUERY_FLAG_NUMBER, &status, &slen, nullptr);
    if (status != 200) {
        InternetCloseHandle(hReq); InternetCloseHandle(hCon); InternetCloseHandle(hNet);
        wchar_t b[128]; swprintf(b, 128, L"The server returned HTTP %lu for the ticket download.\n"
                                         L"(Are you logged in?)", status);
        ShowError(b); g_handling = false; return;
    }

    // Read the PID from Content-Disposition: attachment; filename="ticket_<pid>.vr1"
    std::wstring pid;
    {
        wchar_t cd[512] = L""; DWORD cdlen = sizeof(cd);
        if (HttpQueryInfoW(hReq, HTTP_QUERY_CONTENT_DISPOSITION, cd, &cdlen, nullptr))
            ExtractPidFromName(cd, pid);
    }

    // Read the account's stored client path from the server (X-Game-Client-Path).
    // L-FIX-7b: the ticket must land next to the client we will LAUNCH, so the
    // destination follows the SAME precedence as LaunchGame: a valid ini
    // install (GameDir\ClientExe exists) wins; the server's path is only a
    // fallback for legacy pilots without one.
    std::wstring serverClientPath, gameDir = g_cfg.gameDir;
    {
        wchar_t hv[1024] = L""; DWORD hl = sizeof(hv);
        // HTTP_QUERY_CUSTOM: put the header name in the buffer first.
        wcscpy(hv, L"X-Game-Client-Path");
        if (HttpQueryInfoW(hReq, HTTP_QUERY_CUSTOM, hv, &hl, nullptr) && hv[0]) {
            serverClientPath = hv;
            // L-FIX-3 (defensive): strip surrounding quotes if the account stored
            // the path quoted; they would otherwise poison FileExists and the
            // short-path conversion.
            if (serverClientPath.size() >= 2 && serverClientPath.front() == L'"' &&
                serverClientPath.back() == L'"')
                serverClientPath = serverClientPath.substr(1, serverClientPath.size() - 2);
            size_t slash = serverClientPath.find_last_of(L"\\/");
            if (slash != std::wstring::npos &&
                !FileExists(g_cfg.gameDir + L"\\" + g_cfg.clientExe)) {
                gameDir = serverClientPath.substr(0, slash);
                Stage(L"D0: ticket dir from server path");
            } else {
                Stage(L"D0: ticket dir from ini");
            }
        }
    }
    dest = gameDir + L"\\ticket.vr1";
    if (FileExists(dest)) DeleteFileW(dest.c_str());

    // Stream the body to <GameDir>\ticket.vr1.
    HANDLE hf = CreateFileW(dest.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
                            FILE_ATTRIBUTE_NORMAL, nullptr);
    if (hf == INVALID_HANDLE_VALUE) {
        InternetCloseHandle(hReq); InternetCloseHandle(hCon); InternetCloseHandle(hNet);
        ShowError(L"Could not create:\n" + dest + L"\n(Check GameDir is writable.)"); g_handling = false; return;
    }
    BYTE buf[8192]; DWORD got = 0; DWORD total = 0;
    while (InternetReadFile(hReq, buf, sizeof buf, &got) && got > 0) {
        DWORD wr = 0; WriteFile(hf, buf, got, &wr, nullptr); total += wr;
    }
    CloseHandle(hf);
    InternetCloseHandle(hReq); InternetCloseHandle(hCon); InternetCloseHandle(hNet);

    if (total == 0 || !FileExists(dest)) {
        ShowError(L"The ticket download was empty.\nURL:\n" + url); g_handling = false; return;
    }
    Stage((L"D2: saved " + std::to_wstring(total) + L" bytes, pid=" + pid).c_str());

    if (pid.empty()) {
        ShowError(L"Ticket saved to " + dest + L", but the PID could not be read from the "
                  L"server's Content-Disposition header.\n\nThe game was not launched.");
        g_handling = false; return;
    }

    std::wstring err;
    if (!LaunchGame(pid, err, serverClientPath)) { ShowError(err); g_handling = false; return; }
    g_launched = true;
    // L-FIX-10: no seeding - stop the download engine and exit with the game.
    StopAria2(1500);
    if (g_mainWnd) PostMessageW(g_mainWnd, WM_CLOSE, 0, 0);
}

// ============================================================================
//  ActiveX host for the WebBrowser control.
//
//  IMPORTANT: IOleInPlaceSite and IOleInPlaceFrame BOTH derive from IOleWindow,
//  so a single class implementing both has two conflicting IOleWindow vtables ->
//  the control's callback lands on the wrong slot -> access violation (0xC0000005)
//  during DoVerb activation. We therefore split the frame into its OWN object
//  (InPlaceFrame) and keep the site interfaces on Host. Each object has exactly
//  one IOleWindow, so every vtable is well-formed.
// ============================================================================

class Host;   // fwd

// -- The in-place frame: its own object, single IOleWindow lineage. -----------
class InPlaceFrame : public IOleInPlaceFrame {
public:
    LONG ref = 1;
    HWND hwnd = nullptr;
    explicit InPlaceFrame(HWND h) : hwnd(h) {}
    virtual ~InPlaceFrame() {}

    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IOleWindow || riid == IID_IOleInPlaceUIWindow ||
            riid == IID_IOleInPlaceFrame) {
            *ppv = static_cast<IOleInPlaceFrame*>(this); AddRef(); return S_OK;
        }
        *ppv = nullptr; return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&ref); }
    STDMETHODIMP_(ULONG) Release() override { LONG r = InterlockedDecrement(&ref); if (!r) delete this; return r; }

    // IOleWindow
    STDMETHODIMP GetWindow(HWND* p) override { if (!p) return E_POINTER; *p = hwnd; return S_OK; }
    STDMETHODIMP ContextSensitiveHelp(BOOL) override { return S_OK; }
    // IOleInPlaceUIWindow
    STDMETHODIMP GetBorder(LPRECT) override { return E_NOTIMPL; }
    STDMETHODIMP RequestBorderSpace(LPCBORDERWIDTHS) override { return E_NOTIMPL; }
    STDMETHODIMP SetBorderSpace(LPCBORDERWIDTHS) override { return S_OK; }
    STDMETHODIMP SetActiveObject(IOleInPlaceActiveObject*, LPCOLESTR) override { return S_OK; }
    // IOleInPlaceFrame
    STDMETHODIMP InsertMenus(HMENU, LPOLEMENUGROUPWIDTHS) override { return S_OK; }
    STDMETHODIMP SetMenu(HMENU, HOLEMENU, HWND) override { return S_OK; }
    STDMETHODIMP RemoveMenus(HMENU) override { return S_OK; }
    STDMETHODIMP SetStatusText(LPCOLESTR) override { return S_OK; }
    STDMETHODIMP EnableModeless(BOOL) override { return S_OK; }
    STDMETHODIMP TranslateAccelerator(LPMSG, WORD) override { return S_FALSE; }
};

// -- The site: IOleClientSite + IOleInPlaceSite + IDocHostUIHandler + events. --
//    Single IOleWindow (via IOleInPlaceSite), so no vtable collision.
class Host :
    public IOleClientSite,
    public IOleInPlaceSite,
    public IStorage,
    public IDocHostUIHandler,
    public IServiceProvider,
    public IDownloadManager,
    public DWebBrowserEvents2 {
public:
    LONG ref = 1;
    HWND hwnd = nullptr;
    DWORD cookie = 0;
    InPlaceFrame* frame = nullptr;
    explicit Host(HWND h) : hwnd(h) { frame = new InPlaceFrame(h); }
    virtual ~Host() { if (frame) frame->Release(); }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        *ppv = nullptr;
        if (riid == IID_IUnknown || riid == IID_IOleClientSite) *ppv = static_cast<IOleClientSite*>(this);
        else if (riid == IID_IOleInPlaceSite) *ppv = static_cast<IOleInPlaceSite*>(this);
        else if (riid == IID_IOleWindow)      *ppv = static_cast<IOleWindow*>(static_cast<IOleInPlaceSite*>(this));
        else if (riid == IID_IStorage)        *ppv = static_cast<IStorage*>(this);
        else if (riid == IID_IDocHostUIHandler) *ppv = static_cast<IDocHostUIHandler*>(this);
        else if (riid == IID_IServiceProvider)  *ppv = static_cast<IServiceProvider*>(this);
        else if (riid == IID_IDownloadManager)  *ppv = static_cast<IDownloadManager*>(this);
        else if (riid == IID_IDispatch || riid == DIID_DWebBrowserEvents2)
            *ppv = static_cast<DWebBrowserEvents2*>(this);
        else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&ref); }
    STDMETHODIMP_(ULONG) Release() override { LONG r = InterlockedDecrement(&ref); if (!r) delete this; return r; }

    // IServiceProvider: hand IE our IDownloadManager so ALL downloads route to us
    // (no browser download dialog ever appears).
    STDMETHODIMP QueryService(REFGUID guidService, REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        *ppv = nullptr;
        if (guidService == SID_SDownloadManager && riid == IID_IDownloadManager) {
            *ppv = static_cast<IDownloadManager*>(this); AddRef(); return S_OK;
        }
        return E_NOINTERFACE;
    }

    // IDownloadManager::Download - called by IE for every download instead of its
    // own dialog. We ignore the moniker/bind params and just fetch the ticket.
    STDMETHODIMP Download(IMoniker* pmk, IBindCtx*, DWORD, LONG, BINDINFO*,
                          LPCOLESTR, LPCOLESTR, UINT) override {
        std::wstring url;
        if (pmk) {
            LPOLESTR name = nullptr;
            if (SUCCEEDED(pmk->GetDisplayName(nullptr, nullptr, &name)) && name) {
                url = name; CoTaskMemFree(name);
            }
        }
        Stage((L"9d: IDownloadManager url=" + url).c_str());
        if (!g_launched && !g_handling && hwnd) {
            g_pendingUrl = url.empty() ? L"/download" : url;
            PostMessageW(hwnd, WM_DO_DOWNLOAD, 0, 0);
        }
        return S_OK;   // we handled it; IE shows no dialog
    }

    // IOleClientSite
    STDMETHODIMP SaveObject() override { return S_OK; }
    STDMETHODIMP GetMoniker(DWORD, DWORD, IMoniker** m) override { if (m) *m = nullptr; return E_NOTIMPL; }
    STDMETHODIMP GetContainer(IOleContainer** c) override { if (c) *c = nullptr; return E_NOINTERFACE; }
    STDMETHODIMP ShowObject() override { return S_OK; }
    STDMETHODIMP OnShowWindow(BOOL) override { return S_OK; }
    STDMETHODIMP RequestNewObjectLayout() override { return E_NOTIMPL; }

    // IOleWindow / IOleInPlaceSite
    STDMETHODIMP GetWindow(HWND* p) override { if (!p) return E_POINTER; *p = hwnd; return S_OK; }
    STDMETHODIMP ContextSensitiveHelp(BOOL) override { return S_OK; }
    STDMETHODIMP CanInPlaceActivate() override { return S_OK; }
    STDMETHODIMP OnInPlaceActivate() override { return S_OK; }
    STDMETHODIMP OnUIActivate() override { return S_OK; }
    STDMETHODIMP GetWindowContext(IOleInPlaceFrame** ppFrame, IOleInPlaceUIWindow** doc,
                                  LPRECT r, LPRECT cr, LPOLEINPLACEFRAMEINFO fi) override {
        if (ppFrame) { *ppFrame = frame; frame->AddRef(); }
        if (doc) *doc = nullptr;
        RECT rc; GetClientRect(hwnd, &rc);
        if (r)  *r = rc;
        if (cr) *cr = rc;
        if (fi) { fi->cb = sizeof(OLEINPLACEFRAMEINFO); fi->fMDIApp = FALSE;
                  fi->hwndFrame = hwnd; fi->haccel = nullptr; fi->cAccelEntries = 0; }
        return S_OK;
    }
    STDMETHODIMP Scroll(SIZE) override { return S_OK; }
    STDMETHODIMP OnUIDeactivate(BOOL) override { return S_OK; }
    STDMETHODIMP OnInPlaceDeactivate() override { return S_OK; }
    STDMETHODIMP DiscardUndoState() override { return S_OK; }
    STDMETHODIMP DeactivateAndUndo() override { return S_OK; }
    STDMETHODIMP OnPosRectChange(LPCRECT) override { return S_OK; }

    // IStorage (stubs)
    STDMETHODIMP CreateStream(const OLECHAR*, DWORD, DWORD, DWORD, IStream**) override { return E_NOTIMPL; }
    STDMETHODIMP OpenStream(const OLECHAR*, void*, DWORD, DWORD, IStream**) override { return E_NOTIMPL; }
    STDMETHODIMP CreateStorage(const OLECHAR*, DWORD, DWORD, DWORD, IStorage**) override { return E_NOTIMPL; }
    STDMETHODIMP OpenStorage(const OLECHAR*, IStorage*, DWORD, SNB, DWORD, IStorage**) override { return E_NOTIMPL; }
    STDMETHODIMP CopyTo(DWORD, const IID*, SNB, IStorage*) override { return E_NOTIMPL; }
    STDMETHODIMP MoveElementTo(const OLECHAR*, IStorage*, const OLECHAR*, DWORD) override { return E_NOTIMPL; }
    STDMETHODIMP Commit(DWORD) override { return E_NOTIMPL; }
    STDMETHODIMP Revert() override { return E_NOTIMPL; }
    STDMETHODIMP EnumElements(DWORD, void*, DWORD, IEnumSTATSTG**) override { return E_NOTIMPL; }
    STDMETHODIMP DestroyElement(const OLECHAR*) override { return E_NOTIMPL; }
    STDMETHODIMP RenameElement(const OLECHAR*, const OLECHAR*) override { return E_NOTIMPL; }
    STDMETHODIMP SetElementTimes(const OLECHAR*, const FILETIME*, const FILETIME*, const FILETIME*) override { return E_NOTIMPL; }
    STDMETHODIMP SetClass(REFCLSID) override { return S_OK; }
    STDMETHODIMP SetStateBits(DWORD, DWORD) override { return E_NOTIMPL; }
    STDMETHODIMP Stat(STATSTG*, DWORD) override { return E_NOTIMPL; }

    // IDocHostUIHandler
    STDMETHODIMP ShowContextMenu(DWORD, POINT*, IUnknown*, IDispatch*) override { return S_OK; }
    STDMETHODIMP GetHostInfo(DOCHOSTUIINFO* i) override {
        if (!i) return E_POINTER;
        i->cbSize = sizeof(DOCHOSTUIINFO);
        i->dwFlags = DOCHOSTUIFLAG_NO3DBORDER | DOCHOSTUIFLAG_FLAT_SCROLLBAR;
        i->dwDoubleClick = DOCHOSTUIDBLCLK_DEFAULT;
        return S_OK;
    }
    STDMETHODIMP ShowUI(DWORD, IOleInPlaceActiveObject*, IOleCommandTarget*,
                        IOleInPlaceFrame*, IOleInPlaceUIWindow*) override { return S_OK; }
    STDMETHODIMP HideUI() override { return S_OK; }
    STDMETHODIMP UpdateUI() override { return S_OK; }
    STDMETHODIMP EnableModeless(BOOL) override { return S_OK; }
    STDMETHODIMP OnDocWindowActivate(BOOL) override { return S_OK; }
    STDMETHODIMP OnFrameWindowActivate(BOOL) override { return S_OK; }
    STDMETHODIMP ResizeBorder(LPCRECT, IOleInPlaceUIWindow*, BOOL) override { return S_OK; }
    STDMETHODIMP TranslateAccelerator(LPMSG, const GUID*, DWORD) override { return S_FALSE; }
    STDMETHODIMP GetOptionKeyPath(LPOLESTR* k, DWORD) override { if (k) *k = nullptr; return S_FALSE; }
    STDMETHODIMP GetDropTarget(IDropTarget*, IDropTarget** t) override { if (t) *t = nullptr; return E_NOTIMPL; }
    STDMETHODIMP GetExternal(IDispatch** d) override { if (d) *d = nullptr; return E_NOTIMPL; }
    STDMETHODIMP TranslateUrl(DWORD, LPWSTR, LPWSTR* out) override { if (out) *out = nullptr; return E_NOTIMPL; }
    STDMETHODIMP FilterDataObject(IDataObject*, IDataObject** o) override { if (o) *o = nullptr; return E_NOTIMPL; }

    // IDispatch (event sink)
    STDMETHODIMP GetTypeInfoCount(UINT* c) override { if (c) *c = 0; return E_NOTIMPL; }
    STDMETHODIMP GetTypeInfo(UINT, LCID, ITypeInfo** t) override { if (t) *t = nullptr; return E_NOTIMPL; }
    STDMETHODIMP GetIDsOfNames(REFIID, LPOLESTR*, UINT, LCID, DISPID*) override { return E_NOTIMPL; }
    STDMETHODIMP Invoke(DISPID dispId, REFIID, LCID, WORD wFlags, DISPPARAMS* p,
                        VARIANT*, EXCEPINFO*, UINT*) override {
        // BeforeNavigate2: catch the navigation to /download, cancel it, fetch ourselves.
        // DocumentComplete: the login page finished loading. Mark it so the retry
        // timer stops re-navigating.
        if (dispId == DISPID_DOCUMENTCOMPLETE) {
            g_docLoaded = true;
            Stage(L"L: DocumentComplete");
            // L-FIX-2: if this is the login page, prefill the remembered username.
            if (!g_launched) PrefillLastUser();
            return S_OK;
        }

        if (dispId == DISPID_BEFORENAVIGATE2) {
            if (!(wFlags & DISPATCH_METHOD) || !p || !p->rgvarg || p->cArgs < 7) return S_OK;
            // L-FIX-2: the login form is being submitted (or we're navigating away
            // from a page that has a password field) - the old DOM is still alive
            // here, so this is the last moment to read the username box.
            if (!g_launched) CaptureLastUser();
            // The URL is normally rgvarg[5] as VT_BYREF|VT_BSTR, but depending on how the
            // navigation was initiated it can be a plain BSTR, or a VARIANT* wrapping one.
            // Resolve all of those, and if index 5 is empty, scan the other args for a BSTR
            // that looks like a URL (contains "://" or starts with "/").
            auto readBstr = [](VARIANT& v) -> std::wstring {
                VARIANT* pv = &v;
                if (pv->vt == (VT_BYREF | VT_VARIANT) && pv->pvarVal) pv = pv->pvarVal;
                if (pv->vt == (VT_BYREF | VT_BSTR)) return (pv->pbstrVal && *pv->pbstrVal) ? *pv->pbstrVal : L"";
                if (pv->vt == VT_BSTR)              return pv->bstrVal ? pv->bstrVal : L"";
                return L"";
            };
            std::wstring url = readBstr(p->rgvarg[5]);
            if (url.empty()) {
                for (UINT i = 0; i < p->cArgs; ++i) {
                    std::wstring cand = readBstr(p->rgvarg[i]);
                    if (cand.find(L"://") != std::wstring::npos ||
                        (!cand.empty() && cand[0] == L'/')) { url = cand; break; }
                }
            }

            { wchar_t vb[64]; swprintf(vb, 64, L"9b: BeforeNavigate2 vt=0x%04x url=", p->rgvarg[5].vt);
              std::wstring s = std::wstring(vb) + url; Stage(s.c_str()); }

            if (!url.empty()) {
                std::wstring low = url;
                std::transform(low.begin(), low.end(), low.begin(), ::towlower);
                // L-FIX-5: page commands travel as fake origin URLs; cancel the
                // navigation and post the action to the main thread.
                if (low.find(L"falauncher-install") != std::wstring::npos ||
                    low.find(L"falauncher-fixperms") != std::wstring::npos) {
                    VARIANT& vCancel = p->rgvarg[0];
                    if (vCancel.vt == (VT_BYREF | VT_BOOL) && vCancel.pboolVal)
                        *vCancel.pboolVal = VARIANT_TRUE;
                    if (hwnd)
                        PostMessageW(hwnd, low.find(L"fixperms") != std::wstring::npos
                                     ? WM_DO_FIXPERMS : WM_DO_INSTALL, 0, 0);
                    return S_OK;
                }
                if (low.find(L"/download") != std::wstring::npos ||
                    low.find(L"ticket_") != std::wstring::npos) {
                    VARIANT& vCancel = p->rgvarg[0];
                    if (vCancel.vt == (VT_BYREF | VT_BOOL) && vCancel.pboolVal)
                        *vCancel.pboolVal = VARIANT_TRUE;   // stop the browser's navigation/download
                    if (!g_launched && !g_handling && hwnd) {
                        g_pendingUrl = url;
                        PostMessageW(hwnd, WM_DO_DOWNLOAD, 0, 0);
                    }
                }
            }
            return S_OK;
        }

        // FileDownload: fires when a response is an attachment. If our BeforeNavigate2
        // catch missed (some IE builds skip it for direct attachment links), grab the
        // last navigated URL here and handle it, cancelling the browser's dialog.
        if (dispId == DISPID_FILEDOWNLOAD) {
            Stage(L"9c: FileDownload event");
            // Cancel the browser download dialog (arg[0] = Cancel, VT_BOOL|VT_BYREF).
            if (p && p->rgvarg && p->cArgs >= 1 &&
                p->rgvarg[0].vt == (VT_BOOL | VT_BYREF) && p->rgvarg[0].pboolVal)
                *p->rgvarg[0].pboolVal = VARIANT_TRUE;
            // Fetch using the URL the browser is currently pointed at.
            if (!g_launched && !g_handling && g_web && hwnd) {
                BSTR loc = nullptr;
                if (SUCCEEDED(g_web->get_LocationURL(&loc)) && loc) {
                    std::wstring url = loc; SysFreeString(loc);
                    std::wstring low = url;
                    std::transform(low.begin(), low.end(), low.begin(), ::towlower);
                    if (low.find(L"/download") != std::wstring::npos ||
                        low.find(L"ticket_") != std::wstring::npos) {
                        g_pendingUrl = url;
                        PostMessageW(hwnd, WM_DO_DOWNLOAD, 0, 0);
                    }
                }
            }
            return S_OK;
        }

        return S_OK;
    }
};

// ----------------------------------------------------------------------------
//  Control lifecycle
// ----------------------------------------------------------------------------
static Host*             g_host = nullptr;
static IOleObject*       g_oleObj = nullptr;
static IConnectionPoint* g_cp = nullptr;

// Write the current startup stage to <ExeDir>\launcher_stage.txt so that if the
// process dies hard (0xC0000005) we can still see exactly which call crashed.
static void Stage(const wchar_t* s) {
    static std::wstring path = ExeDir() + L"\\launcher_stage.txt";
    HANDLE h = CreateFileW(path.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ, nullptr,
                           OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h != INVALID_HANDLE_VALUE) {
        SetFilePointer(h, 0, nullptr, FILE_END);
        std::string a; for (const wchar_t* p = s; *p; ++p) a += (char)*p;
        a += "\r\n";
        DWORD wr; WriteFile(h, a.c_str(), (DWORD)a.size(), &wr, nullptr);
        FlushFileBuffers(h);
        CloseHandle(h);
    }
}

static bool CreateBrowser(HWND hwnd) {
    Stage(L"1: new Host");
    g_host = new Host(hwnd);

    Stage(L"2: CoCreateInstance(WebBrowser)");
    IOleObject* ole = nullptr;
    HRESULT hr = CoCreateInstance(CLSID_WebBrowser, nullptr, CLSCTX_INPROC_SERVER,
                                  IID_IOleObject, (void**)&ole);
    if (FAILED(hr) || !ole) {
        wchar_t b[128]; swprintf(b, 128, L"CoCreateInstance(WebBrowser) failed: hr=0x%08lX", hr);
        ShowError(b); return false;
    }
    g_oleObj = ole;

    Stage(L"3: SetClientSite");
    ole->SetClientSite(g_host);
    ole->SetHostNames(L"FALauncher", nullptr);

    RECT rc; GetClientRect(hwnd, &rc);
    Stage(L"4: OleSetContainedObject");
    OleSetContainedObject(ole, TRUE);
    Stage(L"5: DoVerb(INPLACEACTIVATE)");
    hr = ole->DoVerb(OLEIVERB_INPLACEACTIVATE, nullptr, g_host, 0, hwnd, &rc);
    if (FAILED(hr)) {
        wchar_t b[128]; swprintf(b, 128, L"DoVerb(INPLACEACTIVATE) failed: hr=0x%08lX", hr);
        ShowError(b); return false;
    }

    Stage(L"6: QI(IWebBrowser2)");
    hr = ole->QueryInterface(IID_IWebBrowser2, (void**)&g_web);
    if (FAILED(hr) || !g_web) {
        wchar_t b[128]; swprintf(b, 128, L"QI(IWebBrowser2) failed: hr=0x%08lX", hr);
        ShowError(b); return false;
    }

    // L-FIX-1: hold the control's active object for keyboard forwarding.
    // (Best-effort: if the QI fails we just run without TAB, as before.)
    ole->QueryInterface(IID_IOleInPlaceActiveObject, (void**)&g_ipao);

    Stage(L"7: Advise events");
    IConnectionPointContainer* cpc = nullptr;
    if (SUCCEEDED(ole->QueryInterface(IID_IConnectionPointContainer, (void**)&cpc)) && cpc) {
        if (SUCCEEDED(cpc->FindConnectionPoint(DIID_DWebBrowserEvents2, &g_cp)) && g_cp)
            g_cp->Advise(static_cast<IDispatch*>(static_cast<DWebBrowserEvents2*>(g_host)), &g_host->cookie);
        cpc->Release();
    }

    Stage(L"8: size control");
    g_web->put_Left(0); g_web->put_Top(0);
    g_web->put_Width(rc.right - rc.left);
    g_web->put_Height(rc.bottom - rc.top);

    Stage(L"9: Navigate");
    {
        // L-FIX-4: download mode starts on about:blank (the progress page is
        // painted into it); normal mode goes straight to the login page.
        std::wstring first = g_downloadMode ? std::wstring(L"about:blank") : g_cfg.loginUrl;
        BSTR url = SysAllocString(first.c_str());
        HRESULT hn = g_web->Navigate(url, nullptr, nullptr, nullptr, nullptr);
        SysFreeString(url);
        g_navAttempts = 1;
        if (FAILED(hn)) {
            wchar_t b[128]; swprintf(b, 128, L"Navigate failed: hr=0x%08lX", hn);
            ShowError(b); return false;
        }
        // Reliability: the legacy control sometimes accepts the navigation but the
        // page never renders (spins/blank). Start a timer that re-navigates if the
        // login page hasn't fired DocumentComplete within a couple seconds.
        SetTimer(hwnd, NAV_RETRY_TIMER, 2500, nullptr);
    }
    Stage(L"10: done");
    return true;
}

static void DestroyBrowser() {
    if (g_ipao) { g_ipao->Release(); g_ipao = nullptr; }   // L-FIX-1
    if (g_cp && g_host) { g_cp->Unadvise(g_host->cookie); g_cp->Release(); g_cp = nullptr; }
    if (g_web) { g_web->Release(); g_web = nullptr; }
    if (g_oleObj) { g_oleObj->Close(OLECLOSE_NOSAVE); g_oleObj->SetClientSite(nullptr); g_oleObj->Release(); g_oleObj = nullptr; }
    if (g_host) { g_host->Release(); g_host = nullptr; }
}

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_TIMER:
        if (wp == NAV_RETRY_TIMER) {
            if (g_docLoaded || g_launched) {
                KillTimer(hwnd, NAV_RETRY_TIMER);   // page loaded (or we're launching) - stop
            } else if (g_navAttempts < 5 && g_web) {
                // Page still hasn't rendered - re-navigate. Fixes the intermittent
                // "spins/blank" first-load of the legacy control.
                g_navAttempts++;
                Stage((L"R: retry navigate #" + std::to_wstring(g_navAttempts)).c_str());
                BSTR url = SysAllocString(g_cfg.loginUrl.c_str());
                g_web->Navigate(url, nullptr, nullptr, nullptr, nullptr);
                SysFreeString(url);
            } else {
                KillTimer(hwnd, NAV_RETRY_TIMER);   // give up retrying; leave what we have
            }
        }
        if (wp == DL_POLL_TIMER) { PollDownload(); }   // L-FIX-4
        return 0;
    case WM_DO_DOWNLOAD:
        // Runs on the main thread, AFTER the browser event that posted it has
        // returned — so the WinINet fetch no longer races IE's in-flight navigation.
        if (!g_pendingUrl.empty()) {
            std::wstring u = g_pendingUrl; g_pendingUrl.clear();
            DownloadTicketAndLaunch(u);
        }
        return 0;
    case WM_DO_INSTALL:            // L-FIX-5
        StartInstall();
        return 0;
    case WM_DO_FIXPERMS:           // L-FIX-5
        StartPermissionsFix();
        return 0;
    case WM_SIZE:
        if (g_web) { g_web->put_Width(LOWORD(lp)); g_web->put_Height(HIWORD(lp)); }
        return 0;
    case WM_DESTROY:
        // L-FIX-4c: the launcher now supervises the whole session (it hides
        // instead of exiting while the game runs), so aria2 always stops here.
        StopAria2(1500);
        // L-FIX-5: don't yank the disc out from under a running installer.
        if (g_instState != INST_RUNNING) DismountIso();
        DestroyBrowser();
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

// L-FIX-5f: 'game present' means ANY known client binary exists in the dir
// (4.20 classic ships FA.exe; the Deluxe ISO ships FA42R/D/B.EXE), plus
// whatever custom ClientExe the ini names.
static bool GameExeExistsIn(const std::wstring& dir) {
    const wchar_t* exes[] = { L"FA.EXE", L"FA42R.EXE", L"FA42D.EXE", L"FA42B.EXE" };
    for (auto e : exes)
        if (FileExists(dir + L"\\" + e)) return true;
    return FileExists(dir + L"\\" + g_cfg.clientExe);
}

// ----------------------------------------------------------------------------
//  Entry point
// ----------------------------------------------------------------------------
// Vectored exception handler: catches an access violation during control hosting
// and reports it (instead of the process dying silently), then lets the default
// handler terminate. Registered only around the browser-creation call.
static LONG WINAPI StartupVEH(EXCEPTION_POINTERS* ep) {
    DWORD code = ep && ep->ExceptionRecord ? ep->ExceptionRecord->ExceptionCode : 0;
    // Only report genuine faults, not C++/debug exceptions.
    if (code == EXCEPTION_ACCESS_VIOLATION ||
        code == EXCEPTION_ILLEGAL_INSTRUCTION ||
        code == EXCEPTION_IN_PAGE_ERROR ||
        code == EXCEPTION_PRIV_INSTRUCTION) {
        wchar_t b[256];
        swprintf(b, 256,
                 L"The launcher crashed while starting the embedded browser "
                 L"(exception 0x%08lX at %p).\n\nThe built-in Internet Explorer / "
                 L"MSHTML control appears unavailable for hosting on this system.",
                 code, ep && ep->ExceptionRecord ? ep->ExceptionRecord->ExceptionAddress : nullptr);
        MessageBoxW(nullptr, b, L"FA Secure Launcher", MB_OK | MB_ICONERROR);
    }
    return EXCEPTION_CONTINUE_SEARCH;   // let normal termination proceed after the box
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE, PWSTR, int nCmd) {
    HRESULT co = OleInitialize(nullptr);
    if (FAILED(co)) { ShowError(L"OLE initialisation failed."); return 1; }

    std::wstring ini = ExeDir() + L"\\launcher.ini", err;
    if (!LoadConfig(ini, g_cfg, err)) {
        ShowError(err + L"\n\nThe launcher must be installed by the Fighter Ace "
                        L"setup.\nPlease run FighterAce42_Setup.exe to (re)install.");
        OleUninitialize(); return 1;
    }
    // NOTE: we deliberately do NOT hard-fail here if GameDir is missing. The real
    // client path normally arrives from the server (X-Game-Client-Path header) at
    // launch time; GameDir/ClientExe in the ini are only a fallback. Validating the
    // client path happens in LaunchGame, which reports a clear error if neither the
    // server path nor the fallback resolves to a real FA.exe.

    // L-FIX-4: fill ExeDir-relative defaults and pick the starting mode.
    {
        std::wstring dir = ExeDir();
        if (g_cfg.downloadDir.empty()) g_cfg.downloadDir = dir + L"\\download";
        if (g_cfg.aria2Exe.empty())    g_cfg.aria2Exe    = dir + L"\\aria2c.exe";
        // L-FIX-6b: ini paths given as RELATIVE resolve against the launcher's
        // folder, not the process CWD (which differs for shortcuts/consoles).
        auto absify = [&dir](std::wstring& p) {
            if (p.size() >= 2 && (p[1] == L':' || (p[0] == L'\\' && p[1] == L'\\'))) return;
            if (!p.empty()) p = dir + L"\\" + p;
        };
        absify(g_cfg.downloadDir);
        absify(g_cfg.aria2Exe);

        std::wstring cl = GetCommandLineW() ? GetCommandLineW() : L"";
        std::transform(cl.begin(), cl.end(), cl.begin(), ::towlower);
        bool forceGet = cl.find(L"/getgame") != std::wstring::npos;

        std::wstring iso     = g_cfg.downloadDir + L"\\" + g_cfg.isoName;
        bool isoComplete     = FileExists(iso) && !FileExists(iso + L".aria2");
        // L-FIX-11: a saved mirror error page masquerading as a complete ISO
        // (over-quota HTML with no control file) is removed here, so the
        // pilot gets a clean download offer instead of a broken install.
        if (isoComplete && !IsIsoFileValid(iso)) {
            DeleteFileW(iso.c_str());
            isoComplete = false;
        }
        bool isoPartial      = FileExists(iso + L".aria2") ||
                               FileExists(MegaEncPath()) ||     // L-FIX-12:
                               FileExists(MegaDecPath());       // resume mega
        bool engineAvailable = FileExists(g_cfg.aria2Exe);   // L-FIX-10
        bool gameMissing     = !GameExeExistsIn(g_cfg.gameDir);   // L-FIX-5f

        if (forceGet) {
            g_downloadMode = true;
        } else if (engineAvailable && gameMissing && !g_cfg.gameInstalled) {
            // L-FIX-5e: GameInstalled=true in launcher.ini suppresses all of
            // these offers permanently, regardless of exe detection.
            // L-FIX-5: the offer depends on how far a previous download got.
            // (The account's real path may still arrive from the server, so
            // these are offers, not takeovers - "No" proceeds to login.)
            if (isoComplete) {
                if (MessageBoxW(nullptr,
                        L"The game ISO is already downloaded.\n\n"
                        L"Copy the game files to a folder of your choice now?",
                        L"FA Secure Launcher", MB_YESNO | MB_ICONQUESTION) == IDYES) {
                    g_downloadMode = true;   // progress page hosts the install flow
                    g_startInstall = true;
                }
            } else if (isoPartial) {
                if (MessageBoxW(nullptr,
                        L"A partly downloaded game ISO was found.\n\n"
                        L"Resume the download now?",
                        L"FA Secure Launcher", MB_YESNO | MB_ICONQUESTION) == IDYES)
                    g_downloadMode = true;
            } else {
                if (MessageBoxW(nullptr,
                        L"The game client was not found at the fallback path.\n\n"
                        L"Download Fighter Ace 4.2 Deluxe Edition now (4.35 GB,\n"
                        L"via direct download from the project mirror list)?",
                        L"FA Secure Launcher", MB_YESNO | MB_ICONQUESTION) == IDYES)
                    g_downloadMode = true;
            }
        }
    }

    WNDCLASSW wc; ZeroMemory(&wc, sizeof wc);
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInst;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"FALauncherWnd";
    RegisterClassW(&wc);

    int W = g_cfg.windowW, H = g_cfg.windowH;
    int sx = (GetSystemMetrics(SM_CXSCREEN) - W) / 2;
    int sy = (GetSystemMetrics(SM_CYSCREEN) - H) / 2;
    g_mainWnd = CreateWindowW(L"FALauncherWnd", L"FA Secure Launcher",
                              WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
                              sx, sy, W, H, nullptr, nullptr, hInst, nullptr);
    if (!g_mainWnd) { ShowError(L"Could not create the launcher window."); OleUninitialize(); return 1; }

    // Realise the window BEFORE hosting the control: the WebBrowser control's
    // in-place activation needs a shown window with a valid client rect, or it
    // can fail/fault. (Doing this after CreateBrowser was the blank/no-window bug.)
    ShowWindow(g_mainWnd, nCmd);
    UpdateWindow(g_mainWnd);

    PVOID veh = AddVectoredExceptionHandler(1, StartupVEH);
    bool browserOk = CreateBrowser(g_mainWnd);
    if (veh) RemoveVectoredExceptionHandler(veh);
    if (!browserOk) {
        // CreateBrowser already showed a specific ShowError (HRESULT), or the VEH
        // reported a crash. Just clean up.
        DestroyWindow(g_mainWnd); OleUninitialize(); return 1;
    }

    // Window is already shown; make sure the freshly-hosted control gets sized.
    { RECT rc; GetClientRect(g_mainWnd, &rc);
      if (g_web) { g_web->put_Width(rc.right - rc.left); g_web->put_Height(rc.bottom - rc.top); } }

    // L-FIX-4: spin up the transfer engine.
    if (g_downloadMode) {
        std::wstring aerr;
        if (StartAria2(aerr)) {
            SetTimer(g_mainWnd, DL_POLL_TIMER, 2000, nullptr);
            SwitchToNextMirror(true);   // L-FIX-10: mirrors are the primary source
        } else {
            ShowError(aerr + L"\n\nContinuing to the login page.");
            g_downloadMode = false;
            BSTR url = SysAllocString(g_cfg.loginUrl.c_str());
            if (g_web) g_web->Navigate(url, nullptr, nullptr, nullptr, nullptr);
            SysFreeString(url);
        }
        // L-FIX-5: the user already said Yes to installing at the prompt.
        if (g_downloadMode && g_startInstall)
            PostMessageW(g_mainWnd, WM_DO_INSTALL, 0, 0);
    }

    MSG m;
    while (GetMessageW(&m, nullptr, 0, 0)) {
        // L-FIX-1: offer every message to the hosted control's accelerator
        // handler FIRST. This is what makes TAB / Shift+TAB move focus between
        // the page's form fields (and arrows/Ctrl+A work) - without it, the
        // keystrokes go straight to the frame window and the page never sees
        // them as navigation keys. S_OK means the control consumed the message.
        if (g_ipao && g_ipao->TranslateAccelerator(&m) == S_OK) continue;
        TranslateMessage(&m);
        DispatchMessageW(&m);
    }

    OleUninitialize();
    return 0;
}
