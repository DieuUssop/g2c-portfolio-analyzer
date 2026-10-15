@echo off
REM Double-cliquer pour ajouter a la base locale les listes officielles des titres (Euronext, Xetra).
REM A faire avec Internet. Duree : une a quelques minutes.
cd /d "%~dp0"
if exist python\python.exe (
    python\python.exe mettre_a_jour_titres.py
) else (
    python mettre_a_jour_titres.py
)
pause
