@echo off
setlocal EnableExtensions
title RNC Analyst - Interface Principal

set "ROOT_DIR=%~dp0"
set "APP_DIR=%ROOT_DIR%RNC_analyst"
set "LOG_FILE=%ROOT_DIR%rnc_analyst_launcher.log"
set "DIAGNOSTIC_ONLY=0"

if /I "%~1"=="--diagnostico" set "DIAGNOSTIC_ONLY=1"

>"%LOG_FILE%" (
    echo RNC Analyst launcher
    echo Data/hora: %DATE% %TIME%
    echo Pasta raiz: %ROOT_DIR%
    echo.
)

echo.
echo RNC Analyst
echo Interface principal: Desktop
echo Log desta execucao: %LOG_FILE%
echo.

if not exist "%APP_DIR%\desktop_app.py" (
    call :fail "Nao encontrei a pasta do aplicativo: %APP_DIR%"
)

cd /d "%APP_DIR%" || call :fail "Nao foi possivel acessar a pasta do aplicativo: %APP_DIR%"

set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "PY="
set "INSTALLED_PY_VERSION="
set "INSTALLED_REQ_HASH="

if exist "%CODEX_PY%" (
    set "PY=%CODEX_PY%"
    call :log "Python encontrado no runtime do Codex: %CODEX_PY%"
)

if "%PY%"=="" (
    where py >>"%LOG_FILE%" 2>&1
    if not errorlevel 1 (
        set "PY=py -3"
        call :log "Python encontrado pelo launcher py -3."
    )
)

if "%PY%"=="" (
    where python >>"%LOG_FILE%" 2>&1
    if not errorlevel 1 (
        set "PY=python"
        call :log "Python encontrado no PATH."
    )
)

if "%PY%"=="" (
    echo Python nao encontrado.
    echo.
    echo Para usar o RNC Analyst neste PC:
    echo 1. Instale Python 3.11 ou superior.
    echo 2. Durante a instalacao, marque "Add python.exe to PATH".
    echo 3. Feche esta janela e execute ABRIR_RNC_ANALYST.bat novamente.
    echo.
    echo Download: https://www.python.org/downloads/windows/
    echo.
    call :fail "Python nao encontrado neste computador."
)

for /f "usebackq delims=" %%v in (`%PY% -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))" 2^>^>"%LOG_FILE%"`) do set "PY_VERSION=%%v"

if "%PY_VERSION%"=="" (
    call :fail "Nao foi possivel executar o Python encontrado."
)

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >>"%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo Python encontrado, mas a versao e antiga: %PY_VERSION%
    echo Instale Python 3.11 ou superior e marque "Add python.exe to PATH".
    echo Download: https://www.python.org/downloads/windows/
    echo.
    call :fail "Python %PY_VERSION% e antigo demais."
)

echo Python detectado: %PY_VERSION%
call :log "Python detectado: %PY_VERSION%"

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
        call :log "Limpando dependencias por mudanca de Python."
        rmdir /s /q "%PKG_DIR%" >>"%LOG_FILE%" 2>&1
    )
)

if not exist "%PKG_DIR%" mkdir "%PKG_DIR%" >>"%LOG_FILE%" 2>&1

for /f "usebackq delims=" %%h in (`%PY% -c "import hashlib; print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())" 2^>^>"%LOG_FILE%"`) do set "REQ_HASH=%%h"

if "%REQ_HASH%"=="" (
    call :fail "Nao foi possivel ler requirements.txt."
)

if exist "%REQ_HASH_FILE%" (
    set /p INSTALLED_REQ_HASH=<"%REQ_HASH_FILE%"
)

set "NEED_INSTALL=0"
if not exist "%PKG_DIR%\PySide6" set "NEED_INSTALL=1"
if "%INSTALLED_REQ_HASH%"=="" set "NEED_INSTALL=1"
if not "%INSTALLED_REQ_HASH%"=="%REQ_HASH%" set "NEED_INSTALL=1"

if "%NEED_INSTALL%"=="1" (
    if exist "%PKG_DIR%" (
        echo Dependencias mudaram. Limpando pacotes locais antigos...
        call :log "Limpando pacotes locais antigos em %PKG_DIR%."
        rmdir /s /q "%PKG_DIR%" >>"%LOG_FILE%" 2>&1
        mkdir "%PKG_DIR%" >>"%LOG_FILE%" 2>&1
    )
    echo Instalando/atualizando dependencias. Isso pode demorar alguns minutos...
    call :log "Instalando dependencias em %PKG_DIR%."
    %PY% -m pip install --upgrade --target "%PKG_DIR%" -r requirements.txt >>"%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo Falha ao instalar dependencias.
        echo.
        echo Verifique se este PC tem internet liberada e se o antivirus/proxy nao bloqueou o pip.
        echo Detalhes no log:
        echo %LOG_FILE%
        echo.
        call :fail "pip install falhou."
    )
    echo %PY_VERSION%>"%PY_VERSION_FILE%"
    echo %REQ_HASH%>"%REQ_HASH_FILE%"
) else (
    echo Dependencias locais ja estao atualizadas.
    call :log "Dependencias ja estavam atualizadas."
)

set "PYTHONPATH=%PKG_DIR%;%PYTHONPATH%"

if "%DIAGNOSTIC_ONLY%"=="1" (
    echo.
    echo Diagnostico concluido com sucesso. O aplicativo nao foi aberto.
    call :log "Diagnostico concluido sem abrir o aplicativo."
    exit /b 0
)

echo.
echo Iniciando RNC Analyst Desktop...
call :log "Iniciando desktop_app.py."
%PY% desktop_app.py >>"%LOG_FILE%" 2>&1
set "APP_EXIT=%ERRORLEVEL%"

if not "%APP_EXIT%"=="0" (
    echo.
    echo O aplicativo encerrou com erro: %APP_EXIT%
    echo Detalhes no log:
    echo %LOG_FILE%
    echo.
    pause
    exit /b %APP_EXIT%
)

echo.
echo RNC Analyst encerrado.
pause
exit /b 0

:log
echo %~1>>"%LOG_FILE%"
exit /b 0

:fail
echo.
echo ERRO: %~1
echo.
echo Detalhes foram salvos em:
echo %LOG_FILE%
echo.
echo A janela vai ficar aberta. Tire uma foto desta tela ou envie o arquivo de log.
echo.
echo ERRO: %~1>>"%LOG_FILE%"
pause
exit /b 1
