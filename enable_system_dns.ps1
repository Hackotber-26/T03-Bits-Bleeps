# Enable Odikyu DNS Shield as Windows System DNS
$adapter = Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object -First 1

if (-not $adapter) {
    Write-Host "[!] No active network adapter found." -ForegroundColor Red
    exit 1
}

Write-Host "[*] Setting DNS for adapter '$($adapter.Name)' to 127.0.0.1 (Odikyu DNS Shield)..." -ForegroundColor Cyan
Set-DnsClientServerAddress -InterfaceAlias $adapter.Name -ServerAddresses ("127.0.0.1", "1.1.1.1")
Clear-DnsClientCache
Write-Host "[+] SUCCESS! Your system is now protected by Odikyu DNS Shield." -ForegroundColor Green
Write-Host "[*] All browser tabs, apps, and system network requests will now be filtered." -ForegroundColor Yellow
Write-Host "[*] Run 'disable_system_dns.ps1' whenever you want to revert back to default."
