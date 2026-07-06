# FA Secure Launcher (C++, embedded browser)

A compiled Win32 port of `fa_launcher.py`. Shows the server login page inside an
embedded browser window (the built-in Windows Internet Explorer / MSHTML
WebBrowser control), intercepts the ticket download, writes it directly to
the game folder as `ticket.vr1`, and launches `FA.exe`.

## Files

| File               | Purpose                                                       |
|--------------------|---------------------------------------------------------------|
| fa_launcher.exe    | The launcher (already built, self-contained).                 |
| launcher.ini       | MUST sit next to the exe. Server URL + settings.              |
| fa_launcher.cpp    | Source.                                                        |
| build_mingw.bat    | Build with MinGW-w64 (static, self-contained exe).            |
| build_msvc.bat     | Build with Visual Studio cl.exe (/MT, no redist needed).      |

## What it does

1. Reads launcher.ini (next to the exe).
2. Opens a window with the login page embedded (no external browser).
3. You log in on that page. When it navigates to the ticket download
   (/download, served as ticket_<pid>.vr1), the launcher cancels the browser
   download and fetches the bytes itself - using the embedded browser's own
   session cookies - writing straight to GameDir\ticket.vr1.
4. It reads <pid> from the download and launches
   FA.exe /NET /Name:<pid> <LaunchArgs> from GameDir, then closes.

The ticket never touches the Downloads folder - it goes directly into the game
directory, exactly like the original Python launcher.

## launcher.ini

    [Launcher]
    LoginUrl=http://192.168.1.50/login
    GameDir=C:\games\FA
    ClientExe=FA.exe
    LaunchArgs=/MK:0 "/MCD1:0 /MCD2:0 /MTD:0 /NoPreload /PPS:5 /FPS:50 /SDM:1000"
    WindowWidth=460
    WindowHeight=640

Change LoginUrl to point at any host/IP/port - no recompile needed.

## Error handling

Each failure shows a message box and exits non-zero:

- launcher.ini missing/unreadable, or GameDir doesn't exist.
- Embedded browser control couldn't be created.
- Login page (or a sub-page) failed to load.
- Ticket download failed, or couldn't be written to GameDir\ticket.vr1.
- PID couldn't be read from the download URL.
- FA.exe missing, or CreateProcess failed (with the OS error code).

## Requirements

- Windows with the built-in Internet Explorer/MSHTML control present. This is
  standard on Windows 7 through Windows 11 (even where the IE browser is
  "removed", the WebBrowser control remains for app hosting).
- The login page is a simple HTML form, which renders fine in this control. If
  you later make the page depend on very modern JS/CSS, consider a WebView2
  variant instead (ask and I'll produce it).

### Optional: modern document mode

The MSHTML control defaults to an old IE compatibility mode. The current login
page doesn't need anything newer, but if you ever want it to render in IE11
mode, add a FEATURE_BROWSER_EMULATION registry value for fa_launcher.exe
(DWORD 11001). Not required for the current server pages.

## Building

MinGW-w64 (recommended - one self-contained exe):

    build_mingw.bat

Visual Studio (from an "x64 Native Tools Command Prompt"):

    build_msvc.bat

The provided fa_launcher.exe was built with MinGW-w64 and links the runtime
statically, so only standard Windows DLLs are needed at run time
(kernel32, user32, ole32, oleaut32, urlmon, msvcrt).
