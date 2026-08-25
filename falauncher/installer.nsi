; ============================================================================
;  Fighter Ace 4.2 - NSIS installer (L-FIX-8c)
;  Standard, AV-recognized installer stub replacing the custom self-extractor.
;  Installs the launcher toolset to <target>\launcher, records InstallTarget=,
;  and hands over to fa_launcher.exe /getgame for download + game install.
;  L-FIX-8c: legacy Direct3D wrapper DLLs (d3d8.dll, d3d9.dll) are deployed
;  to the game root ($INSTDIR) during extraction, so they sit beside FA.exe
;  once the launcher copy-installs the game into the same folder, fixing the
;  full-screen bugs. Pristine copies are also kept in launcher\redist so a
;  hand-repair is always possible.
;  Build:  makensis installer.nsi   (needs fa_launcher.exe + payload\ beside
;  it; payload\ must now also contain d3d8.dll and d3d9.dll)
; ============================================================================
Unicode true
!include "MUI2.nsh"

Name "Fighter Ace 4.2"
OutFile "FighterAce42_Setup.exe"
; No admin needed: authenticated users may create folders in C:\ root, and
; everything else stays inside the chosen folder / HKCU.
RequestExecutionLevel user
; NSIS auto-appends the last component (FA42) when the user browses elsewhere,
; which reproduces the launcher's old "create a game subfolder" rule.
InstallDir "C:\Games\FA42"
InstallDirRegKey HKCU "Software\FighterAce42" "InstallDir"
SetCompressor /SOLID lzma

VIProductVersion "4.2.0.0"
VIAddVersionKey "ProductName"     "Fighter Ace 4.2 Revival"
VIAddVersionKey "CompanyName"     "Fighter Ace Revival Project"
VIAddVersionKey "FileDescription" "Fighter Ace 4.2 Installer"
VIAddVersionKey "FileVersion"     "4.2.0.0"
VIAddVersionKey "LegalCopyright"  "Fighter Ace community game-preservation project"

!define MUI_WELCOMEPAGE_TITLE "Welcome back, pilot!"
!define MUI_WELCOMEPAGE_TEXT "This wizard installs the Fighter Ace 4.2 launcher.$\r$\n$\r$\nAfter setup, the launcher downloads the game (about 4.4 GB), installs it, and takes you to the login page.$\r$\n$\r$\nClick Next to continue."
!insertmacro MUI_PAGE_WELCOME
!define MUI_DIRECTORYPAGE_TEXT_TOP "Choose where Fighter Ace 4.2 will live. The game files, the launcher and the downloaded data all stay inside this one folder."
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\launcher\fa_launcher.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS "/getgame"
!define MUI_FINISHPAGE_RUN_TEXT "Start the launcher now (downloads and installs the game)"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  ; L-FIX-8c: legacy Direct3D wrapper DLLs into the GAME ROOT. The launcher
  ; later copy-installs the game into this same folder ($INSTDIR ==
  ; InstallTarget), so these land beside FA.exe. Unconditional File (default
  ; overwrite) so a reinstall/upgrade always propagates the current wrappers.
  SetOutPath "$INSTDIR"
  File "payload\d3d8.dll"
  File "payload\d3d9.dll"

  SetOutPath "$INSTDIR\launcher"
  File "fa_launcher.exe"
  File "payload\aria2c.exe"
  File "payload\aria2-COPYING.txt"
  ; L-FIX-8c: pristine copies for manual repair / re-assertion if anything
  ; (e.g. an ISO file of the same name) ever clobbers the game-root pair.
  SetOutPath "$INSTDIR\launcher\redist"
  File "payload\d3d8.dll"
  File "payload\d3d9.dll"
  SetOutPath "$INSTDIR\launcher"
  ; Never clobber a pilot's settings on reinstall/upgrade.
  IfFileExists "$INSTDIR\launcher\launcher.ini" +2 0
    File /oname=launcher.ini "payload\launcher.ini"
  WriteINIStr "$INSTDIR\launcher\launcher.ini" "Launcher" "InstallTarget" "$INSTDIR"

  WriteRegStr HKCU "Software\FighterAce42" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\launcher\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FighterAce42" \
                   "DisplayName" "Fighter Ace 4.2"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FighterAce42" \
                   "UninstallString" '"$INSTDIR\launcher\uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FighterAce42" \
                   "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FighterAce42" \
                   "DisplayVersion" "4.2"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FighterAce42" \
                   "Publisher" "Fighter Ace Revival Project"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FighterAce42" \
                   "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FighterAce42" \
                   "NoRepair" 1
SectionEnd

Section "Uninstall"
  ; The uninstaller runs from a temp copy, so removing the tree is safe.
  ; Guard: only remove a folder that really is one of ours.
  ReadRegStr $0 HKCU "Software\FighterAce42" "InstallDir"
  Delete "$DESKTOP\Fighter Ace 4.2.lnk"
  StrCmp $0 "" done 0
  IfFileExists "$0\launcher\fa_launcher.exe" 0 done
    RMDir /r "$0"
  done:
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FighterAce42"
  DeleteRegKey HKCU "Software\FighterAce42"
SectionEnd
