@echo off
cd /d "%~dp0"

echo.
echo  ================================
echo   Claude Desktop Buddy - Setup
echo  ================================
echo.

python -m venv venv
venv\Scripts\pip install -r requirements.txt

echo.
echo  Done! Double-click start.bat to run.
pause
