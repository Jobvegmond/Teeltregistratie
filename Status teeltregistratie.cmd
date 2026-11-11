@echo off
rem Start de statusmonitor van de teeltregistratie en opent hem in de browser (http://127.0.0.1:8600).
rem Mag ook als kopie of snelkoppeling op het bureaublad staan: hij zoekt zelf de projectmap op.
rem Laat dit venster open zolang je de status wilt zien; sluiten stopt de monitor.
title Status teeltregistratie
set "MAP=%~dp0"
if not exist "%MAP%statusmonitor.py" set "MAP=%USERPROFILE%\OneDrive - KwekerijVanEgmond\Claude en AI\Teeltregistratie\"
if not exist "%MAP%statusmonitor.py" (
    echo statusmonitor.py niet gevonden in "%MAP%".
    pause
    exit /b 1
)
cd /d "%MAP%"
py statusmonitor.py
if errorlevel 1 pause
