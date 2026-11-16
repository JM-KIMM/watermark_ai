param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
if ($Port -lt 1 -or $Port -gt 65535) { throw 'Invalid TCP port.' }
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw 'Run this script in PowerShell as Administrator. It only allows this QR TCP port from LocalSubnet on the Private profile.' }
$ruleName = "ExamWatermark-QR-LAN-$Port"
if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $ruleName -DisplayName "Exam Watermark QR LAN $Port" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private -RemoteAddress LocalSubnet | Out-Null
}
Write-Output "Allowed TCP $Port from the local subnet on Private networks."
