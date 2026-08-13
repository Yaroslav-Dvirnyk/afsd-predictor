@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem Собранная версия (не требует Python) — если она есть, запускаем её
if exist "dist\AFSD_Predictor_Qt\AFSD_Predictor_Qt.exe" (
    start "" "dist\AFSD_Predictor_Qt\AFSD_Predictor_Qt.exe"
    exit /b
)

python afsd_qt.py
if errorlevel 1 (
    echo.
    echo If the window did not open, make sure Python is installed along with
    echo the PySide6, numpy and matplotlib packages:
    echo     pip install -r requirements-qt.txt
    pause
)
