@echo off
title CMC AI (Ollama) Setup

echo.
echo [CMC AI Setup] Checking for Ollama...
where ollama >nul 2>&1
if errorlevel 1 (
    echo.
    echo Ollama is not installed on this system.
    echo.
    echo 1 - Download and install Ollama from:
    echo     https://ollama.com/download
    echo 2 - After installing, run this script again.
    echo.
    pause
    exit /b 1
)

echo.
echo [CMC AI Setup] Ollama found.
echo.

set MODEL=qwen2.5:7b-instruct
echo Pulling model "%MODEL%" (best for CMC assistant)...
echo.
ollama pull %MODEL%
if errorlevel 1 (
    echo.
    echo [ERROR] ollama pull failed. Check your Ollama installation and try again.
    echo.
    pause
    exit /b 1
)

echo.
echo Setting environment variable CMC_AI_MODEL to "%MODEL%"...
setx CMC_AI_MODEL "%MODEL%" >nul

echo.
echo [CMC AI Setup] Done.
echo The CMC embedded assistant will use the model "%MODEL%".
echo Make sure Ollama is running before using "ai" commands in CMC.
echo.
pause
