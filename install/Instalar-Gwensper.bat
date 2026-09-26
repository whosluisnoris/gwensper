@echo off
title Instalador de Gwensper
echo Descargando el instalador de Gwensper...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; & ([scriptblock]::Create((Invoke-RestMethod 'https://raw.githubusercontent.com/whosluisnoris/gwensper/main/install/install.ps1').TrimStart([char]0xFEFF))) -NoPause"
echo.
pause
