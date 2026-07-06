@echo off
REM ==========================================================================
REM  Build fa_launcher.exe with MinGW-w64 (g++).
REM  Produces a fully static, self-contained 64-bit Windows GUI exe.
REM ==========================================================================
setlocal
g++ -std=c++17 -O2 -municode -mwindows ^
    -static -static-libgcc -static-libstdc++ ^
    fa_launcher.cpp -o fa_launcher.exe ^
    -lole32 -loleaut32 -luser32 -lgdi32 -lshell32 -lurlmon -lwininet -ladvapi32 -luuid
if %ERRORLEVEL% neq 0 ( echo. & echo BUILD FAILED. & exit /b %ERRORLEVEL% )
echo. & echo Build OK -^> fa_launcher.exe
echo Keep launcher.ini next to the exe.
endlocal
