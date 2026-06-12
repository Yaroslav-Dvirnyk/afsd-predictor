@echo off
chcp 65001 >nul
cd /d "%~dp0"
python afsd_predictor.py
if errorlevel 1 (
    echo.
    echo If the window did not open, make sure Python with tkinter is installed,
    echo along with the numpy and matplotlib packages:
    echo     pip install numpy matplotlib
    pause
)
