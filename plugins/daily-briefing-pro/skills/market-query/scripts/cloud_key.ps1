[CmdletBinding()]
param(
    [ValidateSet('set', 'status', 'clear')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'

$keyDirectory = Join-Path $env:LOCALAPPDATA 'ThsMarketQuery'
$keyPath = Join-Path $keyDirectory 'fuyao-api-key.dpapi'

$result = switch ($Action) {
    'set' {
        $secureKey = Read-Host -AsSecureString 'Paste the Fuyao API Key (input is hidden)'
        $plainKey = [System.Net.NetworkCredential]::new('', $secureKey).Password
        if ([string]::IsNullOrWhiteSpace($plainKey) -or $plainKey.Length -lt 16) {
            throw 'The API Key is empty or unexpectedly short; nothing was saved.'
        }

        $null = New-Item -ItemType Directory -Force -Path $keyDirectory
        ConvertFrom-SecureString -SecureString $secureKey |
            Set-Content -LiteralPath $keyPath -Encoding ascii

        [ordered]@{
            ok = $true
            action = 'set'
            storage = 'Windows DPAPI (current user)'
            path = $keyPath
            keyPrinted = $false
        }
    }
    'status' {
        [ordered]@{
            configured = Test-Path -LiteralPath $keyPath
            storage = 'Windows DPAPI (current user)'
            path = $keyPath
            keyPrinted = $false
        }
    }
    'clear' {
        if (Test-Path -LiteralPath $keyPath) {
            Remove-Item -LiteralPath $keyPath -Force
            $removed = $true
        }
        else {
            $removed = $false
        }
        [ordered]@{
            ok = $true
            action = 'clear'
            removed = $removed
            keyPrinted = $false
        }
    }
}

$result | ConvertTo-Json -Depth 5
