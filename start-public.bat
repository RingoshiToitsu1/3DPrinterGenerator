@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup.bat first.
  pause
  exit /b 1
)
if not exist phone-password.txt (
  set /p PW=Pick a password for opening the app from your phone: 
  call echo %%PW%%> phone-password.txt
)
set /p PHOTO3D_PASSWORD=<phone-password.txt
echo.
echo Starting... in a moment, look for the line:
echo     * Running on public URL: https://xxxxxxxx.gradio.live
echo Open that address on your phone. It changes every time you start this.
echo Keep this window open. Closing it turns the app off.
echo.
.venv\Scripts\python app.py --no-browser --public-link %*
pause
