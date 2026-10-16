# Install for the current Windows user. Read docs/windows.md before running.
[CmdletBinding()]
param([switch]$EnableSystemProxy)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$State = Join-Path $env:LOCALAPPDATA 'Anonimo'
$Backup = Join-Path $State 'installation.json'
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$PythonW = Join-Path $Root '.venv\Scripts\pythonw.exe'
$Internet = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
$TaskName = 'Anonimo-Background'

if (-not $EnableSystemProxy) {
    throw 'Use -EnableSystemProxy to install the local CA, autostart and current-user HTTPS proxy.'
}
if (-not (Test-Path $PythonW)) { throw 'First run: uv sync --locked --extra proxy' }
if (Test-Path $Backup) { throw 'Already installed. Use Uninstall-Background.ps1 before reinstalling.' }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { throw 'Task name already exists.' }
$Current = Get-ItemProperty $Internet
if ($Current.ProxyEnable -eq 1 -or $Current.AutoConfigURL) {
    throw 'An existing proxy/PAC is configured. Ask IT to chain Anonimo with that proxy; this installer will not replace it.'
}
foreach ($PolicyPath in @('HKCU:\Software\Policies\Microsoft\Windows\CurrentVersion\Internet Settings',
                          'HKLM:\Software\Policies\Microsoft\Windows\CurrentVersion\Internet Settings')) {
    if (Test-Path $PolicyPath) { throw 'Managed Internet policy detected. Use an IT-managed pilot deployment.' }
}
foreach ($Port in @(8765, 8877)) {
    $Client = New-Object System.Net.Sockets.TcpClient
    try { $Client.Connect('127.0.0.1', $Port); throw "Port $Port is already occupied." }
    catch [System.Net.Sockets.SocketException] { }
    finally { $Client.Dispose() }
}
New-Item -ItemType Directory -Force $State | Out-Null
# Protect the local CA private key, API token and installation state.
$Sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $State /inheritance:r /grant:r "*${Sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not restrict the state directory ACL.' }
$Policy = Join-Path $State 'policy.yaml'
if (-not (Test-Path $Policy)) { Copy-Item (Join-Path $Root 'policy.yaml') $Policy }
$CaDirectory = Join-Path $State 'proxy'
& $Python -m anonimo init-ca --state-dir $CaDirectory
if ($LASTEXITCODE -ne 0) { throw 'CA initialization failed.' }
$CaFile = Join-Path $CaDirectory 'mitmproxy-ca-cert.cer'
$Certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($CaFile)
$AlreadyTrusted = Test-Path "Cert:\CurrentUser\Root\$($Certificate.Thumbprint)"
$Saved = @{}
foreach ($Name in @('ProxyEnable', 'ProxyServer', 'ProxyOverride')) {
    $Property = $Current.PSObject.Properties[$Name]
    $Saved[$Name] = @{ exists = ($null -ne $Property); value = $(if ($Property) { $Property.Value } else { $null }) }
}
@{ proxy = $Saved; thumbprint = $Certificate.Thumbprint; certificate_added = (-not $AlreadyTrusted);
   proxy_server = 'http=127.0.0.1:8877;https=127.0.0.1:8877'; root = $Root } |
    ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $Backup
try {
    if (-not $AlreadyTrusted) { Import-Certificate -FilePath $CaFile -CertStoreLocation 'Cert:\CurrentUser\Root' | Out-Null }
    $Arguments = '-m anonimo background --policy "{0}" --token-file "{1}" --state-dir "{2}"' -f $Policy, (Join-Path $State 'token'), $CaDirectory
    $Action = New-ScheduledTaskAction -Execute $PythonW -Argument $Arguments -WorkingDirectory $Root
    $User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
    $Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        try {
            $Health = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health' -TimeoutSec 1
            if ($Health.status -eq 'ok') {
                $Probe = New-Object System.Net.Sockets.TcpClient
                try { $Probe.Connect('127.0.0.1', 8877); $Ready = $true } finally { $Probe.Dispose() }
                break
            }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $Ready) { throw 'Background service did not become ready.' }
    & $Python (Join-Path $PSScriptRoot 'smoke_api.py') --token-file (Join-Path $State 'token')
    if ($LASTEXITCODE -ne 0) { throw 'Functional API readiness check failed.' }
    Set-ItemProperty $Internet -Name ProxyServer -Value 'http=127.0.0.1:8877;https=127.0.0.1:8877'
    Set-ItemProperty $Internet -Name ProxyOverride -Value '<local>;localhost;127.0.0.1'
    Set-ItemProperty $Internet -Name ProxyEnable -Type DWord -Value 1
    . (Join-Path $PSScriptRoot 'Notify-ProxyChange.ps1')
    Write-Host 'Anonimo is running and will start at login. Restart Chrome/Edge. Local policy and CA are in LocalAppData\Anonimo.'
} catch {
    & (Join-Path $PSScriptRoot 'Uninstall-Background.ps1') -RestoreAfterFailedInstall
    throw
}
