@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup.bat first.
  pause
  exit /b 1
)

if exist phone-password.txt goto have_password
set /p PW=Pick a password for opening the app from your phone: 
>phone-password.txt echo(%PW%
:have_password
set /p PHOTO3D_PASSWORD=<phone-password.txt

if exist github-token.txt goto have_token
echo.
echo For a permanent address at https://ringoshitoitsu1.github.io/3DPrinterGenerator/
echo paste a GitHub token with the "gist" permission (see README).
echo Or just press Enter to skip.
set /p TK=GitHub token: 
>github-token.txt echo(%TK%
:have_token
set /p PHOTO3D_GITHUB_TOKEN=<github-token.txt

echo.
echo Starting... Your phone address:
echo     https://ringoshitoitsu1.github.io/3DPrinterGenerator/
echo (Without a GitHub token, use the "public URL" line below instead.)
echo Keep this window open. Closing it turns the app off.
echo.
.venv\Scripts\python app.py --no-browser --public-link %*
pause
