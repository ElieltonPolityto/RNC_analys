@echo off
setlocal
title RNC Analyst - Fallback Streamlit Antigo
cd /d "%~dp0"

echo.
echo ATENCAO: este launcher abre a interface antiga em Streamlit.
echo Para uso normal, feche esta janela e abra:
echo ..\ABRIR_RNC_ANALYST.bat
echo.
choice /C SN /N /M "Continuar mesmo assim com o fallback antigo? (S/N): "
if errorlevel 2 exit /b 0

set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "PY="
set "INSTALLED_REQ_HASH="

if exist "%CODEX_PY%" set "PY=%CODEX_PY%"

if "%PY%"=="" (
    where py >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)

if "%PY%"=="" (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)

if "%PY%"=="" (
    echo Python nao encontrado.
    echo Instale Python 3.11+ ou execute pelo Codex, que fornece um runtime local.
    pause
    exit /b 1
)

for /f "usebackq delims=" %%v in (`%PY% -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))"`) do set "PY_VERSION=%%v"

set "PKG_ROOT=%CD%\.packages_runtime"
set "PY_TAG=py%PY_VERSION:.=%"
set "PKG_DIR=%PKG_ROOT%\%PY_TAG%"
set "REQ_HASH_FILE=%PKG_DIR%\.requirements-hash"

if not exist "%PKG_DIR%" mkdir "%PKG_DIR%"

for /f "usebackq delims=" %%h in (`%PY% -c "import hashlib; print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())"`) do set "REQ_HASH=%%h"

if exist "%REQ_HASH_FILE%" (
    set /p INSTALLED_REQ_HASH=<"%REQ_HASH_FILE%"
)

set "NEED_INSTALL=0"
if not exist "%PKG_DIR%\streamlit" set "NEED_INSTALL=1"
if "%INSTALLED_REQ_HASH%"=="" set "NEED_INSTALL=1"
if not "%INSTALLED_REQ_HASH%"=="%REQ_HASH%" set "NEED_INSTALL=1"

if "%NEED_INSTALL%"=="1" (
    echo Instalando/atualizando dependencias...
    %PY% -m pip install --upgrade --target "%PKG_DIR%" -r requirements.txt
    if errorlevel 1 (
        echo Falha ao instalar dependencias.
        pause
        exit /b 1
    )
    echo %REQ_HASH%>"%REQ_HASH_FILE%"
) else (
    echo Dependencias locais ja estao atualizadas.
)

set "PYTHONPATH=%PKG_DIR%;%PYTHONPATH%"

echo.
echo Iniciando RNC Analyst Streamlit antigo...
%PY% -m streamlit run app.py --global.developmentMode false --server.port 8501

pause
