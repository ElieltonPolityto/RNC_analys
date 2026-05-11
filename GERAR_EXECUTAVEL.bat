@echo off
setlocal EnableExtensions
title RNC Analyst - Gerar Executavel

set "ROOT_DIR=%~dp0"
set "APP_DIR=%ROOT_DIR%RNC_analyst"
set "LOG_FILE=%ROOT_DIR%rnc_analyst_build.log"

>"%LOG_FILE%" (
    echo RNC Analyst build
    echo Data/hora: %DATE% %TIME%
    echo Pasta raiz: %ROOT_DIR%
    echo.
)

echo.
echo RNC Analyst - Gerador de Executavel
echo Log desta execucao: %LOG_FILE%
echo.

if not exist "%APP_DIR%\desktop_app.py" (
    call :fail "Nao encontrei desktop_app.py em %APP_DIR%"
)

cd /d "%APP_DIR%" || call :fail "Nao foi possivel acessar %APP_DIR%"

set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "PY="

if exist "%CODEX_PY%" set "PY=%CODEX_PY%"

if "%PY%"=="" (
    where py >>"%LOG_FILE%" 2>&1
    if not errorlevel 1 set "PY=py -3"
)

if "%PY%"=="" (
    where python >>"%LOG_FILE%" 2>&1
    if not errorlevel 1 set "PY=python"
)

if "%PY%"=="" (
    echo Python nao encontrado.
    echo Instale Python 3.11 ou superior e marque "Add python.exe to PATH".
    echo Download: https://www.python.org/downloads/windows/
    call :fail "Python nao encontrado."
)

for /f "usebackq delims=" %%v in (`%PY% -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))" 2^>^>"%LOG_FILE%"`) do set "PY_VERSION=%%v"
if "%PY_VERSION%"=="" call :fail "Nao foi possivel executar o Python encontrado."

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "Python %PY_VERSION% e antigo demais. Instale Python 3.11 ou superior."

set "PY_TAG=py%PY_VERSION:.=%"
set "PKG_DIR=%APP_DIR%\.packages_runtime\%PY_TAG%"
set "BUILD_PKGS=%APP_DIR%\.packages_build\%PY_TAG%"
set "REQ_HASH_FILE=%PKG_DIR%\.requirements-hash"

if not exist "%PKG_DIR%" mkdir "%PKG_DIR%" >>"%LOG_FILE%" 2>&1
if not exist "%BUILD_PKGS%" mkdir "%BUILD_PKGS%" >>"%LOG_FILE%" 2>&1

for /f "usebackq delims=" %%h in (`%PY% -c "import hashlib; print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())" 2^>^>"%LOG_FILE%"`) do set "REQ_HASH=%%h"
if "%REQ_HASH%"=="" call :fail "Nao foi possivel ler requirements.txt."

set "INSTALLED_REQ_HASH="
if exist "%REQ_HASH_FILE%" set /p INSTALLED_REQ_HASH=<"%REQ_HASH_FILE%"

set "NEED_RUNTIME_INSTALL=0"
if not exist "%PKG_DIR%\PySide6" set "NEED_RUNTIME_INSTALL=1"
if "%INSTALLED_REQ_HASH%"=="" set "NEED_RUNTIME_INSTALL=1"
if not "%INSTALLED_REQ_HASH%"=="%REQ_HASH%" set "NEED_RUNTIME_INSTALL=1"

if "%NEED_RUNTIME_INSTALL%"=="1" (
    echo Instalando/atualizando dependencias do aplicativo...
    %PY% -m pip install --upgrade --target "%PKG_DIR%" -r requirements.txt >>"%LOG_FILE%" 2>&1
    if errorlevel 1 call :fail "Falha ao instalar dependencias do aplicativo."
    echo %REQ_HASH%>"%REQ_HASH_FILE%"
) else (
    echo Dependencias do aplicativo ja estao atualizadas.
)

if not exist "%BUILD_PKGS%\PyInstaller" (
    echo Instalando PyInstaller...
    %PY% -m pip install --upgrade --target "%BUILD_PKGS%" pyinstaller >>"%LOG_FILE%" 2>&1
    if errorlevel 1 call :fail "Falha ao instalar PyInstaller."
) else (
    echo PyInstaller ja esta instalado.
)

set "PYTHONPATH=%BUILD_PKGS%;%PKG_DIR%;%APP_DIR%\.packages;%PYTHONPATH%"

echo.
echo Gerando executavel. Isso pode demorar alguns minutos...
%PY% -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onedir ^
    --windowed ^
    --name RNC_Analyst ^
    --paths "%PKG_DIR%" ^
    --paths "%APP_DIR%\.packages" ^
    --collect-all chromadb ^
    --collect-all reportlab ^
    --collect-all openpyxl ^
    --distpath "%ROOT_DIR%dist" ^
    --workpath "%ROOT_DIR%build\pyinstaller" ^
    --specpath "%ROOT_DIR%build" ^
    desktop_app.py >>"%LOG_FILE%" 2>&1

if errorlevel 1 call :fail "PyInstaller falhou ao gerar o executavel."

if not exist "%ROOT_DIR%dist\RNC_Analyst\prompts" mkdir "%ROOT_DIR%dist\RNC_Analyst\prompts" >>"%LOG_FILE%" 2>&1
copy /Y "%APP_DIR%\.env.example" "%ROOT_DIR%dist\RNC_Analyst\.env.example" >>"%LOG_FILE%" 2>&1
copy /Y "%APP_DIR%\prompts\instrucoes_base.txt" "%ROOT_DIR%dist\RNC_Analyst\prompts\instrucoes_base.txt" >>"%LOG_FILE%" 2>&1

set "ZIP_FILE=%ROOT_DIR%dist\RNC_Analyst_executavel.zip"
echo Gerando ZIP para copiar para outro PC...
if exist "%ZIP_FILE%" del /F /Q "%ZIP_FILE%" >>"%LOG_FILE%" 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -LiteralPath '%ROOT_DIR%dist\RNC_Analyst' -DestinationPath '%ZIP_FILE%' -Force" >>"%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo Aviso: nao foi possivel gerar o ZIP. Use a pasta dist\RNC_Analyst.
    echo AVISO: falha ao gerar ZIP.>>"%LOG_FILE%"
) else (
    echo ZIP gerado:
    echo %ZIP_FILE%
)

echo.
echo Executavel gerado com sucesso:
echo %ROOT_DIR%dist\RNC_Analyst\RNC_Analyst.exe
echo.
echo Para levar para outro PC, copie a pasta inteira:
echo %ROOT_DIR%dist\RNC_Analyst
echo.
if not "%RNC_BUILD_NO_PAUSE%"=="1" pause
exit /b 0

:fail
echo.
echo ERRO: %~1
echo.
echo Detalhes no log:
echo %LOG_FILE%
echo.
echo ERRO: %~1>>"%LOG_FILE%"
if not "%RNC_BUILD_NO_PAUSE%"=="1" pause
exit /b 1
