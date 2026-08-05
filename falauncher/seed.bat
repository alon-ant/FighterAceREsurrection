@echo off
REM ===========================================================================
REM  FA42 Deluxe ISO - dedicated seeder
REM  Run this on the SERVER machine (or any always-on PC) so the swarm always
REM  has at least one reachable seed. This runs OUTSIDE the launcher, so it
REM  keeps seeding regardless of launchers opening and closing.
REM
REM  One-time setup for full connectability:
REM    1. Router: forward TCP and UDP port 6888 to this machine (same panel
REM       where the FA server ports are forwarded).
REM    2. Firewall: the first run opens a visible console, so Windows Firewall
REM       will show its allow prompt - click Allow. (Private + Public.)
REM
REM  The ISO (or a partial download) must be in .\download - this script will
REM  finish downloading it first if it is incomplete.
REM  Stop seeding with Ctrl+C or by closing the window.
REM ===========================================================================
cd /d "%~dp0"
aria2c.exe -T FA42DeluxeEdition_iso.torrent --dir=download ^
  --continue=true --bt-seed-unverified=true --seed-ratio=0.0 ^
  --enable-dht=true --bt-enable-lpd=true ^
  --dht-entry-point=dht.transmissionbt.com:6881 ^
  --listen-port=6888 --dht-listen-port=6888 ^
  --summary-interval=30
pause
