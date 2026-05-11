@echo off
setlocal
title RNC Analyst - Interface Principal

set "APP_DIR=%~dp0RNC_analyst"
if not exist "%APP_DIR%\desktop_app.py" (
    echo Nao encontrei a pasta do aplicativo:
    echo %APP_DIR%
    echo.
    echo Confira se este arquivo esta na pasta raiz "RNC Analyst".
    pause
    exit /b 1
)

cd /d "%APP_DIR%"

echo.
echo RNC Analyst
echo Interface principal: Desktop
echo.

set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "PY="
set "INSTALLED_PY_VERSION="
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
set "PY_VERSION_FILE=%PKG_DIR%\.python-version"
set "REQ_HASH_FILE=%PKG_DIR%\.requirements-hash"

if exist "%PY_VERSION_FILE%" (
    set /p INSTALLED_PY_VERSION=<"%PY_VERSION_FILE%"
)

if not "%INSTALLED_PY_VERSION%"=="" (
    if not "%INSTALLED_PY_VERSION%"=="%PY_VERSION%" (
        echo Versao do Python mudou de %INSTALLED_PY_VERSION% para %PY_VERSION%.
        echo Limpando dependencias locais para evitar incompatibilidade...
        rmdir /s /q "%PKG_DIR%"
    )
)

if not exist "%PKG_DIR%" mkdir "%PKG_DIR%"

for /f "usebackq delims=" %%h in (`%PY% -c "import hashlib; print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())"`) do set "REQ_HASH=%%h"

if exist "%REQ_HASH_FILE%" (
    set /p INSTALLED_REQ_HASH=<"%REQ_HASH_FILE%"
)

set "NEED_INSTALL=0"
if not exist "%PKG_DIR%\PySide6" set "NEED_INSTALL=1"
if "%INSTALLED_REQ_HASH%"=="" set "NEED_INSTALL=1"
if not "%INSTALLED_REQ_HASH%"=="%REQ_HASH%" set "NEED_INSTALL=1"

if "%NEED_INSTALL%"=="1" (
    echo Instalando/atualizando dependencias...
    echo Se o app ja estiver aberto, feche a janela antiga antes de continuar.
    %PY% -m pip install --upgrade --target "%PKG_DIR%" -r requirements.txt
    if errorlevel 1 (
        echo Falha ao instalar dependencias.
        echo Dica: feche qualquer RNC Analyst aberto e execute este .bat novamente.
        pause
        exit /b 1
    )
    echo %PY_VERSION%>"%PY_VERSION_FILE%"
    echo %REQ_HASH%>"%REQ_HASH_FILE%"
) else (
    echo Dependencias locais ja estao atualizadas.
)

set "PYTHONPATH=%PKG_DIR%;%PYTHONPATH%"

echo.
echo Iniciando RNC Analyst Desktop...
%PY% desktop_app.py

pause
