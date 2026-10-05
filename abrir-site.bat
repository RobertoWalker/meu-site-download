@echo off
cd /d "%~dp0"
title Site de Download de Video
echo Iniciando o site... (nao feche esta janela enquanto estiver usando)
echo.
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5000"
python app.py
echo.
echo O servidor parou. Se apareceu algum erro acima, copie e me mande.
pause