[CmdletBinding()]
param(
    [string]$BindAddress = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 9010,
    [switch]$NoReload,
    [switch]$Install
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvDirectory = Join-Path $projectRoot ".venv"
$pythonExecutable = Join-Path $venvDirectory "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "未找到 Python。请先安装 Python 3.11 或更高版本，并将其加入 PATH。"
    }

    Write-Host "正在创建 Python 虚拟环境：$venvDirectory"
    & $pythonCommand.Source -m venv $venvDirectory
    $Install = $true
}

$dependenciesAvailable = $false
if (-not $Install) {
    & $pythonExecutable -c "import akshare, baostock, uvicorn" 2>$null
    $dependenciesAvailable = $LASTEXITCODE -eq 0
}

if ($Install -or -not $dependenciesAvailable) {
    Write-Host "正在安装后端依赖..."
    & $pythonExecutable -m pip install -e "$PSScriptRoot[dev]"
    if ($LASTEXITCODE -ne 0) {
        throw "后端依赖安装失败，退出代码：$LASTEXITCODE"
    }
}

$uvicornArguments = @(
    "-m", "uvicorn", "app.main:app",
    "--host", $BindAddress,
    "--port", $Port.ToString()
)
if (-not $NoReload) {
    $uvicornArguments += "--reload"
}

Write-Host "后端服务：http://${BindAddress}:$Port"
Write-Host "API 文档：http://${BindAddress}:$Port/docs"

Push-Location $PSScriptRoot
try {
    & $pythonExecutable @uvicornArguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
