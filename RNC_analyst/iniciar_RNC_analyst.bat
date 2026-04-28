@echo off
setlocal
cd /d "%~dp0"

set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "PY="

where py >nul 2>nul
if %errorlevel%==0 set "PY=py -3"

if "%PY%"=="" (
    where python >nul 2>nul
    if %errorlevel%==0 set "PY=python"
)

if "%PY%"=="" (
    if exist "%CODEX_PY%" set "PY=%CODEX_PY%"
)

if "%PY%"=="" (
    echo Python nao encontrado.
    echo Instale Python 3.11+ ou execute pelo Codex, que fornece um runtime local.
    pause
    exit /b 1
)

set "PKG_DIR=%CD%\.packages"
if not exist "%PKG_DIR%" mkdir "%PKG_DIR%"

echo Instalando/atualizando dependencias...
%PY% -m pip install --upgrade --target "%PKG_DIR%" -r requirements.txt

set "PYTHONPATH=%PKG_DIR%;%PYTHONPATH%"

echo Iniciando RNC Analyst...
%PY% -m streamlit run app.py --global.developmentMode false

pause
