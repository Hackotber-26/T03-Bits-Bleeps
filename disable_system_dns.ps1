# Revert Windows System DNS back to Automatic (DHCP)
$adapter = Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object -First 1

if (-not $adapter) {
    Write-Host "[!] No active network adapter found." -ForegroundColor Red
    exit 1
}

Write-Host "[*] Resetting DNS for adapter '$($adapter.Name)' to automatic (DHCP)..." -ForegroundColor Cyan
Set-DnsClientServerAddress -InterfaceAlias $adapter.Name -ResetServerAddresses
Clear-DnsClientCache
Write-Host "[+] SUCCESS! System DNS has been restored to default." -ForegroundColor Green
