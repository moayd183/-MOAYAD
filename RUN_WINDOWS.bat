@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel% equ 0 (
  set "PYTHON=py -3"
) else (
  set "PYTHON=python"
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python environment...
  %PYTHON% -m venv .venv
  if errorlevel 1 goto error
)
echo Installing scientific dependencies (requires internet on first run)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-science.txt
if errorlevel 1 goto error
echo.
echo Open http://127.0.0.1:8000 in your browser.
echo Press CTRL+C to stop the server.
".venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
pause
exit /b 0
:error
echo Error. Check Python version and internet connection, then retry.
pause
exit /b 1
