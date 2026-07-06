@echo off
REM ==========================================================================
REM  Build fa_launcher.exe with Microsoft Visual C++ (cl.exe).
REM  Run from an "x64 Native Tools Command Prompt for VS".
REM  /MT static-links the CRT so no VC++ redistributable is needed.
REM ==========================================================================
setlocal
cl /nologo /std:c++17 /O2 /MT /EHsc /DUNICODE /D_UNICODE ^
   fa_launcher.cpp ^
   /link /SUBSYSTEM:WINDOWS /ENTRY:wWinMainCRTStartup ^
   ole32.lib oleaut32.lib user32.lib gdi32.lib shell32.lib urlmon.lib wininet.lib advapi32.lib uuid.lib
if %ERRORLEVEL% neq 0 ( echo. & echo BUILD FAILED. & exit /b %ERRORLEVEL% )
del fa_launcher.obj 2>nul
echo. & echo Build OK -^> fa_launcher.exe
echo Keep launcher.ini next to the exe.
endlocal
