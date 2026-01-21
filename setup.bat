@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║       White Mirror Service Agent - Windows Setup              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.
echo   Platform:    windows
echo   Virtual Env: venv-windows
echo.

set VENV_DIR=venv-windows

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ Python not found
    echo    Please install Python 3.10+ and add to PATH
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo   Python Ver:  %PYTHON_VERSION%
echo.

if exist "%VENV_DIR%" (
    echo ⚠️  Virtual environment already exists: %VENV_DIR%
    set /p REPLY="Recreate it? [y/N] "
    if /i "!REPLY!"=="y" (
        echo 🗑️  Removing existing venv...
        rmdir /s /q "%VENV_DIR%"
    ) else (
        echo ✅ Using existing venv
        call "%VENV_DIR%\Scripts\activate.bat"
        pip install -q --upgrade pip
        pip install -q -r requirements.txt
        echo ✅ Dependencies updated
        exit /b 0
    )
)

echo 📦 Creating virtual environment...
python -m venv "%VENV_DIR%"

echo 🔧 Activating...
call "%VENV_DIR%\Scripts\activate.bat"

echo 📥 Upgrading pip...
pip install -q --upgrade pip

echo 📥 Installing dependencies...
pip install -q -r requirements.txt

echo 📥 Installing NVIDIA GPU support...
pip install -q pynvml

set CONFIG_FILE=config-windows.yaml
if not exist "%CONFIG_FILE%" (
    if exist "config.yaml.example" (
        echo 📝 Creating platform config: %CONFIG_FILE%
        copy config.yaml.example "%CONFIG_FILE%" >nul
    )
)

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                    ✅ Setup Complete!                         ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.
echo   To start the Service Agent:
echo.
echo     start.bat
echo.
echo   Or in PowerShell:
echo.
echo     .\start.ps1
echo.
echo   The UI will automatically open in your browser at:
echo     http://localhost:9100/ui
echo.

endlocal
