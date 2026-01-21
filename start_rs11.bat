@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

echo.
echo ====================================================================
echo        White Mirror Service Agent - RS11 (Windows)
echo ====================================================================
echo.
echo   Machine ID:  rs11
echo   Virtual Env: venv_rs11
echo.

set VENV_DIR=venv_rs11

if not exist "%VENV_DIR%" (
    echo Virtual environment not found: %VENV_DIR%
    echo Please create it with: python -m venv venv_rs11
    exit /b 1
)

echo Starting Service Agent...
echo.

call "%VENV_DIR%\Scripts\activate.bat"

set WM_AGENT_PLATFORM=windows
set WM_AGENT_MACHINE_ID=rs11

if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "%%a=%%b"
    )
)

python main.py %*

endlocal
