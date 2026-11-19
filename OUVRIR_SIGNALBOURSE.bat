@echo off
title SignalBourse
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
echo Verification des modules (la premiere fois, cela prend une minute)...
%PY% -m pip install -r requirements.txt --quiet --disable-pip-version-check
echo.
echo Demarrage de SignalBourse : le tableau de bord va s'ouvrir dans ton navigateur.
echo Laisse cette fenetre ouverte (tu peux la reduire). Ferme-la pour arreter.
%PY% signal_bourse.py app
pause
