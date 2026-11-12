@echo off
REM Builds captionX-Setup-<version>.exe on Windows. Needs: Python 3.10+, Node 18+, pnpm. Inno Setup is installed for you if missing.
setlocal
cd /d "%~dp0"
echo.
echo === captionX Windows build ===

where python >nul 2>nul || (echo Python was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH" & exit /b 1)
where pnpm >nul 2>nul || (echo pnpm was not found. Run: npm install -g pnpm & exit /b 1)

echo.
echo [1/5] Building the web interface...
pushd frontend
call pnpm install || (popd & echo pnpm install failed & exit /b 1)
call pnpm build || (popd & echo pnpm build failed & exit /b 1)
popd

echo.
echo [2/5] Python build environment...
if not exist .build-venv\Scripts\python.exe python -m venv .build-venv || (echo venv failed & exit /b 1)
call .build-venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
pip install --quiet -r backend\requirements.txt -r backend\requirements-build.txt || (echo pip install failed & exit /b 1)

echo.
echo [3/5] ffmpeg...
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\get-ffmpeg.ps1 || (echo ffmpeg download failed & exit /b 1)

echo.
echo [4/5] Packaging the app (PyInstaller)...
if exist dist-win rmdir /s /q dist-win
pyinstaller packaging\captionX.spec --noconfirm --distpath dist-win --workpath build-win || (echo PyInstaller failed & exit /b 1)

for /f %%v in ('python -c "import re;print(re.search(r'\"(.+?)\"',open('backend/app/__init__.py').read()).group(1))"') do set VER=%%v

echo.
echo [5/5] Building the installer (Inno Setup)...
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if "%ISCC%"=="" (
  echo Inno Setup not found. Installing it with winget...
  winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements
  if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
  if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
)
if "%ISCC%"=="" (echo Could not find Inno Setup. Install it from https://jrsoftware.org/isdl.php and run this file again. & exit /b 1)
"%ISCC%" /DAppVersion=%VER% packaging\captionX.iss || (echo Inno Setup failed & exit /b 1)

echo.
echo Done. Your installer:
echo   %~dp0dist-installer\captionX-Setup-%VER%.exe
explorer dist-installer
