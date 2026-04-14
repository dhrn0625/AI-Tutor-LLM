@echo off
setlocal

cd /d "%~dp0"
title AI Tutor Launcher

echo ==================================================
echo AI Tutor Launcher
echo ==================================================
echo Project root: %CD%
echo.

set "PORTABLE_PYTHON=%~dp0runtime\python\python.exe"
set "VENV_DIR=%~dp0.venv"
set "VENV_ACTIVATE=%VENV_DIR%\Scripts\activate.bat"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "API_HOST=127.0.0.1"
set "API_PORT=8000"
set "STREAMLIT_PORT=8501"
set "AITUTOR_API_BASE_URL=http://%API_HOST%:%API_PORT%"
if not defined AITUTOR_OLLAMA_URL set "AITUTOR_OLLAMA_URL=http://127.0.0.1:11434/api/generate"
if not defined AITUTOR_OLLAMA_TAGS_URL set "AITUTOR_OLLAMA_TAGS_URL=%AITUTOR_OLLAMA_URL:/api/generate=/api/tags%"
set "OLLAMA_HEALTH_URL=%AITUTOR_OLLAMA_TAGS_URL%"

if exist "%PORTABLE_PYTHON%" (
    echo [INFO] Portable Python detected: %PORTABLE_PYTHON%
) else (
    echo [INFO] Portable Python not found. Using the virtual environment interpreter.
)

if not exist "%VENV_DIR%" (
    echo [ERROR] Virtual environment not found.
    echo [ERROR] Run setup.bat first.
    echo.
    pause
    exit /b 1
)

if not exist "%VENV_ACTIVATE%" (
    echo [ERROR] Could not find %VENV_ACTIVATE%
    echo.
    pause
    exit /b 1
)

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Could not find %VENV_PYTHON%
    echo [ERROR] Run setup.bat again to rebuild the environment.
    echo.
    pause
    exit /b 1
)

echo [STEP] Activating virtual environment...
call "%VENV_ACTIVATE%"
if errorlevel 1 (
    echo [ERROR] Failed to activate .venv
    echo.
    pause
    exit /b 1
)

echo [STEP] Checking Ollama availability...
python -c "import urllib.request; urllib.request.urlopen('%OLLAMA_HEALTH_URL%', timeout=3).read()"
if not "%ERRORLEVEL%"=="0" (
    echo [WARN] Ollama is not reachable at %OLLAMA_HEALTH_URL%
    echo [WARN] The app will open, but chat requests will fail until Ollama is running.
    echo [WARN] Ensure Ollama is running in the same network environment.
    echo [WARN] If Ollama runs elsewhere, set AITUTOR_OLLAMA_URL before launching.
    echo [WARN] Try: http://localhost:11434/api/generate
    echo [WARN] Try: http://host.docker.internal:11434/api/generate
    echo [WARN] Try: http://^<WSL-bridge-IP^>:11434/api/generate
    echo.
) else (
    echo [INFO] Ollama is reachable.
)

if not exist "%~dp0api.py" (
    echo [ERROR] FastAPI entry point api.py was not found.
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0streamlit_app.py" (
    echo [ERROR] Streamlit entry point streamlit_app.py was not found.
    echo.
    pause
    exit /b 1
)

echo [STEP] Starting FastAPI backend in a new window...
start "AI Tutor API" cmd /k python -m uvicorn api:app --host %API_HOST% --port %API_PORT% --log-level debug

echo [STEP] Waiting for backend startup...
timeout /t 3 /nobreak >nul

echo [STEP] Launching Streamlit frontend...
echo [INFO] The browser should open automatically.
echo.
set "AITUTOR_API_BASE_URL=%AITUTOR_API_BASE_URL%"
streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port %STREAMLIT_PORT% --browser.serverAddress 127.0.0.1
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
    echo [ERROR] Streamlit exited with code %EXIT_CODE%.
) else (
    echo [INFO] AI Tutor closed cleanly.
)
echo.
pause
exit /b %EXIT_CODE%
