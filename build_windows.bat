@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install --upgrade pip
if errorlevel 1 goto fail
py -3 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail
py -3 -m PyInstaller --noconfirm --clean --windowed --onefile --name PhotoOrganizerAI --collect-all PIL --collect-all imagehash app.py
if errorlevel 1 goto fail
echo Completed: dist\PhotoOrganizerAI.exe
pause
exit /b 0
:fail
echo Build failed. Python 3.10+ is required on the BUILD computer.
pause
exit /b 1
