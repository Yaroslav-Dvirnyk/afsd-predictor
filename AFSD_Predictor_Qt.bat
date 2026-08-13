@echo off
chcp 65001 >nul
cd /d "%~dp0"
python afsd_qt.py
if errorlevel 1 (
    echo.
    echo If the window did not open, make sure Python is installed along with
    echo the PySide6, numpy and matplotlib packages:
    echo     pip install PySide6 numpy matplotlib
    pause
)
