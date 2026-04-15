@echo off
chcp 65001 >NUL
title Research Pipeline

echo.
echo ============================================================
echo  Research Pipeline -- Continuous Research Loop
echo ============================================================
echo.

:: Check Ollama is running
echo [1/2] Checking Ollama...
curl -s http://localhost:11434/api/tags >NUL 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Ollama is not running.
    echo  Start Ollama first, then re-run this script.
    echo.
    pause
    exit /b 1
)
echo  Ollama: OK

:: Check model is available
echo [2/2] Checking model qwen3.5:4b...
curl -s http://localhost:11434/api/tags 2>NUL | findstr /C:"qwen3.5:4b" >NUL 2>&1
if errorlevel 1 (
    echo  Model not found -- pulling qwen3.5:4b ...
    ollama pull qwen3.5:4b
)
echo  Model: OK

echo.
echo  Starting pipeline  ^(Ctrl+C to stop^)
echo  Logs: logs\pipeline_%date:~-4,4%-%date:~-10,2%-%date:~-7,2%.log
echo.
echo ============================================================
echo.

python run.py

echo.
echo  Pipeline stopped.
pause
