[CmdletBinding()]
param([switch]$RestoreAfterFailedInstall)
$ErrorActionPreference = 'Stop'
$State = Join-Path $env:LOCALAPPDATA 'Anonimo'
$Backup = Join-Path $State 'installation.json'
$Internet = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
if (-not (Test-Path $Backup)) { throw 'No Anonimo installation backup found.' }
$Saved = Get-Content -Raw $Backup | ConvertFrom-Json
$Current = Get-ItemProperty $Internet
if (-not $RestoreAfterFailedInstall -and $Current.ProxyServer -ne $Saved.proxy_server) {
    throw 'Proxy settings changed after installation. Ask IT to restore settings before uninstalling.'
}
foreach ($Name in @('ProxyEnable', 'ProxyServer', 'ProxyOverride')) {
    $Entry = $Saved.proxy.$Name
    if ($Entry.exists) {
        Set-ItemProperty $Internet -Name $Name -Value $Entry.value
    } else {
        Remove-ItemProperty $Internet -Name $Name -ErrorAction SilentlyContinue
    }
}
. (Join-Path $PSScriptRoot 'Notify-ProxyChange.ps1')
if (Get-ScheduledTask -TaskName 'Anonimo-Background' -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName 'Anonimo-Background'
    Unregister-ScheduledTask -TaskName 'Anonimo-Background' -Confirm:$false
}
if ($Saved.certificate_added) {
    Remove-Item "Cert:\CurrentUser\Root\$($Saved.thumbprint)" -ErrorAction SilentlyContinue
}
Remove-Item $Backup
Write-Host 'Autostart and the Anonimo trust entry were removed; previous proxy settings restored. Policy and local keys were retained.'
