@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup.bat first.
  pause
  exit /b 1
)
if not exist phone-password.txt (
  set /p PW=Pick a password for using this from your phone: 
  call echo %%PW%%> phone-password.txt
)
set /p PHOTO3D_PASSWORD=<phone-password.txt
echo.
echo Open this on your phone (Tailscale on):  http://%COMPUTERNAME%:7860
echo.
.venv\Scripts\python app.py --share-on-network --no-browser %*
pause
