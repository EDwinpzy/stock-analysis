param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('list-tools', 'call-tool', 'search-tools', 'exact-tools')]
    [string]$Action,

    [string]$ToolName,

    [string]$ArgumentsJson = '{}',

    [string]$Query,

    [string]$ToolNames,

    [string]$User
)

$ErrorActionPreference = 'Stop'

function Get-LumiMcpConnection {
    $relativeConfigPath = 'agent-sdk\opencode\config\opencode.jsonc'
    $candidates = @()
    if ($User) {
        $candidates = @(
            Join-Path $env:USERPROFILE "lumi\users\$User\$relativeConfigPath"
        )
    }
    else {
        $usersRoot = Join-Path $env:USERPROFILE 'lumi\users'
        if (Test-Path -LiteralPath $usersRoot) {
            $candidates = @(
                Get-ChildItem -LiteralPath $usersRoot -Directory |
                    Sort-Object LastWriteTime -Descending |
                    ForEach-Object {
                        Join-Path $_.FullName $relativeConfigPath
                    }
            )
        }
    }

    foreach ($configPath in $candidates) {
        if (-not (Test-Path -LiteralPath $configPath)) {
            continue
        }

        $config = Get-Content -LiteralPath $configPath -Raw
        $tokenMatch = [regex]::Match(
            $config,
            '"lumi"\s*:\s*\{[\s\S]*?"Authorization"\s*:\s*"Bearer\s+([^"]+)"'
        )
        $urlMatch = [regex]::Match(
            $config,
            '"lumi"\s*:\s*\{[\s\S]*?"url"\s*:\s*"([^"]+)"'
        )

        if ($tokenMatch.Success -and $urlMatch.Success) {
            return @{
                Url = $urlMatch.Groups[1].Value
                Token = $tokenMatch.Groups[1].Value
            }
        }
    }

    throw 'The local Lumi MCP endpoint or authorization was not found. Start Lumi with its MCP bridge enabled, or pass -User explicitly.'
}

function Invoke-McpRequest {
    param(
        [hashtable]$Connection,
        [string]$Body,
        [string]$SessionId
    )

    $headers = @{
        Authorization = "Bearer $($Connection.Token)"
        Accept = 'application/json, text/event-stream'
    }
    if ($SessionId) {
        $headers['mcp-session-id'] = $SessionId
    }

    return Invoke-WebRequest `
        -Uri $Connection.Url `
        -Method Post `
        -Headers $headers `
        -ContentType 'application/json' `
        -Body $Body `
        -TimeoutSec 40
}

function Convert-SseResponse {
    param([string]$Content)

    $data = ($Content -split "`n" | Where-Object { $_ -like 'data: *' } | Select-Object -Last 1)
    if (-not $data) {
        throw 'No JSON data was returned by the Lumi MCP endpoint.'
    }

    $payload = $data.Substring(6) | ConvertFrom-Json
    if ($payload.error) {
        throw ($payload.error | ConvertTo-Json -Depth 10 -Compress)
    }
    return $payload
}

function Invoke-LumiMcp {
    param(
        [hashtable]$Connection,
        [int]$Id,
        [string]$Method,
        $Params
    )

    $request = @{
        jsonrpc = '2.0'
        id = $Id
        method = $Method
    }
    if ($null -ne $Params) {
        $request.params = $Params
    }

    $response = Invoke-McpRequest `
        -Connection $Connection `
        -Body ($request | ConvertTo-Json -Depth 30 -Compress)
    return Convert-SseResponse $response.Content
}

$connection = Get-LumiMcpConnection
$request = @{
    jsonrpc = '2.0'
    id = 1
    method = 'initialize'
    params = @{
        protocolVersion = '2025-03-26'
        capabilities = @{}
        clientInfo = @{
            name = 'lumi-api-discovery'
            version = '1.0'
        }
    }
} | ConvertTo-Json -Depth 12 -Compress

$initResponse = Invoke-McpRequest -Connection $connection -Body $request
$null = Convert-SseResponse $initResponse.Content
$sessionId = [string]$initResponse.Headers['mcp-session-id']

$initialized = @{
    jsonrpc = '2.0'
    method = 'notifications/initialized'
} | ConvertTo-Json -Compress
try {
    $null = Invoke-McpRequest -Connection $connection -Body $initialized -SessionId $sessionId
}
catch {
    # Some MCP implementations return no response body for this notification.
}

$headers = @{
    Authorization = "Bearer $($connection.Token)"
    Accept = 'application/json, text/event-stream'
    'mcp-session-id' = $sessionId
}

switch ($Action) {
    'list-tools' {
        $request = @{
            jsonrpc = '2.0'
            id = 2
            method = 'tools/list'
            params = @{}
        } | ConvertTo-Json -Depth 10 -Compress
    }
    'call-tool' {
        if (-not $ToolName) {
            throw '-ToolName is required for call-tool.'
        }
        $argsObject = $ArgumentsJson | ConvertFrom-Json -AsHashtable
        $request = @{
            jsonrpc = '2.0'
            id = 2
            method = 'tools/call'
            params = @{
                name = $ToolName
                arguments = $argsObject
            }
        } | ConvertTo-Json -Depth 30 -Compress
    }
    'search-tools' {
        if (-not $Query) {
            throw '-Query is required for search-tools.'
        }
        $request = @{
            jsonrpc = '2.0'
            id = 2
            method = 'tools/call'
            params = @{
                name = 'tool_search'
                arguments = @{
                    mode = 'query'
                    query = $Query
                    limit = 20
                }
            }
        } | ConvertTo-Json -Depth 15 -Compress
    }
    'exact-tools' {
        if (-not $ToolNames) {
            throw '-ToolNames is required for exact-tools.'
        }
        $request = @{
            jsonrpc = '2.0'
            id = 2
            method = 'tools/call'
            params = @{
                name = 'tool_search'
                arguments = @{
                    mode = 'exact'
                    tool_names = @($ToolNames -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
                }
            }
        } | ConvertTo-Json -Depth 15 -Compress
    }
}

$response = Invoke-McpRequest -Connection $connection -Body $request -SessionId $sessionId
$result = Convert-SseResponse $response.Content
$result | ConvertTo-Json -Depth 40
