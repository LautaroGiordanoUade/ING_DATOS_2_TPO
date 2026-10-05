param(
    [switch]$NoReload,
    [switch]$WithoutMocks
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

$env:APP_ENV = "development"
$env:APP_DEMO_MODE = if ($WithoutMocks) { "false" } else { "true" }

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000")
if (-not $NoReload) {
    $uvicornArgs += "--reload"
}

Push-Location $projectRoot
try {
    if (Test-Path -LiteralPath $venvPython) {
        & $venvPython @uvicornArgs
    }
    else {
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if ($null -eq $launcher) {
            throw "No se encontró .venv ni el launcher 'py'. Instale Python 3.12+."
        }
        & py -3.12 @uvicornArgs
    }
    if ($LASTEXITCODE -ne 0) {
        throw "La API no pudo iniciarse. Verifique Python 3.12 y las dependencias del proyecto."
    }
}
finally {
    Pop-Location
}
