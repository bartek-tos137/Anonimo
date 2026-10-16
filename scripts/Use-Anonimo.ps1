# Launch an IDE/CLI through the already-running local proxy, keeping parent settings intact.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Client,
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$ClientArgs
)
$ErrorActionPreference = 'Stop'
$State = Join-Path $env:LOCALAPPDATA 'Anonimo'
$Ca = Join-Path $State 'proxy\mitmproxy-ca-cert.pem'
if (-not (Test-Path $Ca)) { throw 'First initialize Anonimo with Install-Background.ps1.' }
$Health = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health' -TimeoutSec 2
if ($Health.status -ne 'ok') { throw 'Anonimo is not ready.' }
$Names = @('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'no_proxy', 'NODE_EXTRA_CA_CERTS')
$Previous = @{}
foreach ($Name in $Names) { $Previous[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process') }
try {
    $env:HTTP_PROXY = 'http://127.0.0.1:8877'
    $env:HTTPS_PROXY = 'http://127.0.0.1:8877'
    $env:NO_PROXY = '127.0.0.1,localhost,::1'
    if ($Previous['NODE_EXTRA_CA_CERTS']) {
        $Combined = Join-Path $State 'node-ca-bundle.pem'
        (Get-Content -Raw $Previous['NODE_EXTRA_CA_CERTS']) + "`n" + (Get-Content -Raw $Ca) |
            Set-Content -Encoding ascii $Combined
        $env:NODE_EXTRA_CA_CERTS = $Combined
    } else { $env:NODE_EXTRA_CA_CERTS = $Ca }
    & $Client @ClientArgs
    $ClientExitCode = $LASTEXITCODE
} finally {
    foreach ($Name in $Names) { [Environment]::SetEnvironmentVariable($Name, $Previous[$Name], 'Process') }
}
exit $ClientExitCode
