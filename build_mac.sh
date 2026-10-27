#!/bin/bash
set -e
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt pyinstaller
python3 -m PyInstaller --noconfirm --clean --windowed --name PhotoOrganizerAI --collect-all PIL --collect-all imagehash app.py
printf '\nCompleted: dist/PhotoOrganizerAI.app\n'
