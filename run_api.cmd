@echo off
setlocal

cd /d "%~dp0"

set "APP_ENV=development"
set "APP_DEMO_MODE=true"
set "RELOAD_ARGUMENT=--reload"

:parse_arguments
if "%~1"=="" goto start_api

if /I "%~1"=="--no-reload" (
    set "RELOAD_ARGUMENT="
    shift
    goto parse_arguments
)

if /I "%~1"=="--without-mocks" (
    set "APP_DEMO_MODE=false"
    shift
    goto parse_arguments
)

echo Argumento desconocido: %~1
echo Uso: run_api.cmd [--no-reload] [--without-mocks]
echo.
pause
exit /b 2

:start_api
if exist ".venv\Scripts\python.exe" goto ensure_dependencies

echo No se encontro el entorno virtual .venv.
echo Buscando Python 3.12 o superior...

py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "BASE_PYTHON=py -3.12"
    goto create_environment
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "BASE_PYTHON=python"
    goto create_environment
)

echo.
echo ERROR: Python 3.12 o superior no esta instalado.
echo Descarguelo desde: https://www.python.org/downloads/windows/
echo Durante la instalacion marque la opcion "Add python.exe to PATH".
echo Luego vuelva a ejecutar run_api.cmd.
echo.
pause
exit /b 1

:create_environment
echo Creando el entorno virtual .venv...
%BASE_PYTHON% -m venv .venv
if errorlevel 1 goto setup_error

:ensure_dependencies
".venv\Scripts\python.exe" -c "import fastapi, uvicorn" >nul 2>&1
if not errorlevel 1 goto launch_api

echo Instalando dependencias del proyecto por primera vez...
".venv\Scripts\python.exe" -m pip install -e ".[dev]"
if errorlevel 1 goto setup_error

:launch_api
echo.
echo Iniciando Niche Social Network API...
echo Swagger: http://127.0.0.1:8000/docs
echo Demo mode: %APP_DEMO_MODE%
echo Para detener la API presione Ctrl+C.
echo.

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 %RELOAD_ARGUMENT%
if errorlevel 1 goto api_error
exit /b 0

:setup_error
echo.
echo ERROR: No se pudo preparar el entorno virtual o instalar las dependencias.
echo Revise la conexion a Internet y los mensajes anteriores.
echo.
pause
exit /b 1

:api_error
echo.
echo ERROR: La API no pudo iniciarse. Revise los mensajes anteriores.
echo.
pause
exit /b 1
