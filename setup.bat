@echo off
setlocal

cd /d "%~dp0"
title AI Tutor Setup

echo ==================================================
echo AI Tutor Setup
echo ==================================================
echo Project root: %CD%
echo.

set "PORTABLE_PYTHON=%~dp0runtime\python\python.exe"
set "PYTHON_CMD="

if exist "%PORTABLE_PYTHON%" (
    set "PYTHON_CMD=%PORTABLE_PYTHON%"
    echo [INFO] Using portable Python: %PORTABLE_PYTHON%
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
        echo [INFO] Using system Python from PATH.
    ) else (
        where py >nul 2>nul
        if not errorlevel 1 (
            set "PYTHON_CMD=py -3"
            echo [INFO] Using Python launcher: py -3
        )
    )
)

if not defined PYTHON_CMD (
    echo [ERROR] Python was not found.
    echo [ERROR] Install Python or place a portable runtime at runtime\python\python.exe
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0requirements.txt" (
    echo [ERROR] requirements.txt was not found in the project root.
    echo.
    pause
    exit /b 1
)

echo [STEP] Creating virtual environment...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 (
    echo [ERROR] Failed to create .venv
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0.venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment activation script was not created.
    echo.
    pause
    exit /b 1
)

echo [STEP] Activating virtual environment...
call "%~dp0.venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate .venv
    echo.
    pause
    exit /b 1
)

echo [STEP] Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip
    echo.
    pause
    exit /b 1
)

echo [STEP] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    echo.
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Setup completed successfully.
echo [NEXT] Double-click run_app.bat to start the AI Tutor.
echo.
pause
exit /b 0
