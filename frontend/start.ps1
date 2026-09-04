[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 6173,
    [switch]$Install
)

$ErrorActionPreference = "Stop"

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $npmCommand) {
    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
}
if ($null -eq $npmCommand) {
    throw "未找到 npm。请先安装 Node.js，并将其加入 PATH。"
}

Push-Location $PSScriptRoot
try {
    if ($Install -or -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "node_modules"))) {
        Write-Host "正在安装前端依赖..."
        & $npmCommand.Source install
        if ($LASTEXITCODE -ne 0) {
            throw "前端依赖安装失败，退出代码：$LASTEXITCODE"
        }
    }

    Write-Host "前端页面：http://localhost:$Port"
    & $npmCommand.Source run dev -- --port $Port
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
