@echo off
setlocal
cd /d "%~dp0"

set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "PY="

if exist "%CODEX_PY%" set "PY=%CODEX_PY%"

if "%PY%"=="" (
    where py >nul 2>nul
    if %errorlevel%==0 set "PY=py -3"
)

if "%PY%"=="" (
    where python >nul 2>nul
    if %errorlevel%==0 set "PY=python"
)

if "%PY%"=="" (
    echo Python nao encontrado.
    echo Instale Python 3.11+ ou execute pelo Codex, que fornece um runtime local.
    pause
    exit /b 1
)

set "PKG_DIR=%CD%\.packages"
set "PY_VERSION_FILE=%PKG_DIR%\.python-version"

for /f "usebackq delims=" %%v in (`%PY% -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))"`) do set "PY_VERSION=%%v"

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

echo Instalando/atualizando dependencias...
%PY% -m pip install --upgrade --target "%PKG_DIR%" -r requirements.txt
if %errorlevel% neq 0 (
    echo Falha ao instalar dependencias.
    pause
    exit /b 1
)
echo %PY_VERSION%>"%PY_VERSION_FILE%"

set "PYTHONPATH=%PKG_DIR%;%PYTHONPATH%"

echo Iniciando RNC Analyst...
%PY% -m streamlit run app.py --global.developmentMode false --server.port 8501

pause
