[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet(
        'catalog',
        'tools',
        'search',
        'blocks',
        'realtime',
        'candle',
        'trend',
        'tick',
        'sort',
        'subscribe',
        'fields',
        'datahub-get',
        'sectors',
        'watchlist',
        'sector',
        'call',
        'cloud-get',
        'status'
    )]
    [string]$Action,

    [Parameter(Position = 1)]
    [string]$Target,

    [string]$Fields,
    [int]$Period = 5,
    [int]$AdjustType = 0,
    [int]$Count = 60,
    [int]$Offset = 0,
    [long]$BeginTime,
    [long]$EndTime,
    [long]$TradeDate,
    [int]$TradeClass,
    [string]$Api,
    [int]$Block = 14,
    [int]$SortField = 199112,
    [int]$SortOrder = 1,
    [string]$ExcludeBlocks,

    [ValidateSet(
        'datahub',
        'dataaccessor',
        'subscribe',
        'fields',
        'cloud'
    )]
    [string]$Source = 'datahub',

    [ValidateSet('realtime', 'candle', 'trend', 'tick')]
    [string]$DataType,

    [string]$Query,
    [int]$Limit = 20,
    [switch]$All,
    [string]$Tool,
    [string]$ArgumentsJson = '{}',

    [ValidateSet(
        'SubscribeRealtime',
        'SubscribeIntradayCandle',
        'SubscribeIntradayTrend',
        'SubscribeTrend',
        'SubscribeIntradayTick',
        'SubscribeTick'
    )]
    [string]$SubscribeApi,

    [int]$TimeoutMs = 10000,
    [string]$User,

    [ValidateSet('auto', 'local', 'cloud')]
    [string]$Mode = 'auto',

    [string]$ApiKeyEnv = 'HITHINK_API_KEY',
    [string]$AssetType,
    [int]$HttpTimeoutSec = 20,
    [switch]$IncludeMeta
)

$ErrorActionPreference = 'Stop'

$helper = Join-Path $PSScriptRoot 'lumi_mcp.ps1'
$referenceRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'references'
$script:SelectedSource = 'builtin'
$script:Attempts = [System.Collections.Generic.List[object]]::new()
$script:HasFields = $PSBoundParameters.ContainsKey('Fields')
$script:HasBeginTime = $PSBoundParameters.ContainsKey('BeginTime')
$script:HasEndTime = $PSBoundParameters.ContainsKey('EndTime')
$script:HasTradeDate = $PSBoundParameters.ContainsKey('TradeDate')

function Invoke-LumiTool {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [hashtable]$Arguments
    )

    $toolArguments = @{
        name = $Name
        args = $Arguments
    } | ConvertTo-Json -Depth 30 -Compress

    $helperArguments = @(
        '-NoProfile',
        '-File', $helper,
        '-Action', 'call-tool',
        '-ToolName', 'tool_execute',
        '-ArgumentsJson', $toolArguments
    )
    if ($User) {
        $helperArguments += @('-User', $User)
    }

    $output = & pwsh @helperArguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Lumi MCP call failed: $($output -join ' ')"
    }

    $envelope = ($output -join "`n") | ConvertFrom-Json
    if ($envelope.error) {
        throw ($envelope.error | ConvertTo-Json -Depth 8 -Compress)
    }
    if ($envelope.result.isError) {
        throw "Lumi tool '$Name' returned an error."
    }

    $textPart = $envelope.result.content |
        Where-Object { $_.type -eq 'text' } |
        Select-Object -First 1
    if (-not $textPart) {
        throw "Lumi tool '$Name' returned no text payload."
    }

    $result = $textPart.text | ConvertFrom-Json
    if (-not $result.success) {
        $message = if ($result.error) {
            [string]$result.error
        }
        else {
            'unknown tool error'
        }
        throw "Lumi tool '$Name' failed: $message"
    }

    $payload = $result.data
    if (
        $null -ne $payload -and
        $payload -isnot [System.Array] -and
        $payload.PSObject.Properties.Name -contains 'success'
    ) {
        if (-not $payload.success) {
            $message = if ($payload.error) {
                [string]$payload.error
            }
            else {
                'unknown data error'
            }
            throw "Lumi tool '$Name' failed: $message"
        }
        if ($payload.PSObject.Properties.Name -contains 'data') {
            return $payload.data
        }
    }

    return $payload
}

function Get-CloudBaseUrl {
    $value = if ([string]::IsNullOrWhiteSpace($env:THS_MARKET_CLOUD_BASE_URL)) {
        'https://fuyao.aicubes.cn'
    }
    else {
        $env:THS_MARKET_CLOUD_BASE_URL
    }

    $uri = $null
    if (-not [uri]::TryCreate($value, [UriKind]::Absolute, [ref]$uri)) {
        throw 'THS_MARKET_CLOUD_BASE_URL is not an absolute URL.'
    }
    if ($uri.UserInfo -or $uri.Fragment) {
        throw 'The cloud base URL must not contain credentials or fragments.'
    }
    if ($uri.Scheme -ne 'https' -and -not ($uri.Scheme -eq 'http' -and $uri.IsLoopback)) {
        throw 'The cloud base URL must use HTTPS. HTTP is allowed only for loopback tests.'
    }
    return $uri.GetLeftPart([UriPartial]::Authority).TrimEnd('/')
}

function Get-CloudApiKeyInfo {
    $environmentNames = @($ApiKeyEnv, 'HITHINK_API_KEY', 'FUYAO_API_KEY') |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -Unique

    foreach ($name in $environmentNames) {
        $value = [Environment]::GetEnvironmentVariable($name, 'Process')
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return @{
                Key = $value
                Source = "env:$name"
            }
        }
    }

    $encryptedPath = Join-Path $env:LOCALAPPDATA 'ThsMarketQuery\fuyao-api-key.dpapi'
    if (Test-Path -LiteralPath $encryptedPath) {
        try {
            $encrypted = Get-Content -LiteralPath $encryptedPath -Raw
            $secure = ConvertTo-SecureString -String $encrypted.Trim()
            $value = [System.Net.NetworkCredential]::new('', $secure).Password
        }
        catch {
            throw 'The encrypted Fuyao API Key could not be read for the current Windows user.'
        }
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return @{
                Key = $value
                Source = 'dpapi:current-user'
            }
        }
    }

    throw "Fuyao API Key is not configured. Set $ApiKeyEnv or run cloud_key.ps1 -Action set."
}

function Test-CloudApiKeyConfigured {
    try {
        $null = Get-CloudApiKeyInfo
        return $true
    }
    catch {
        return $false
    }
}

function Test-LocalBridgeConfigured {
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
        if ($config -match '"lumi"\s*:\s*\{' -and $config -match '"Authorization"\s*:\s*"Bearer\s+') {
            return $true
        }
    }
    return $false
}

function Protect-CloudMessage {
    param(
        [string]$Message,
        [string]$ApiKey
    )

    $safe = if ($Message) { $Message } else { 'unknown cloud error' }
    if ($ApiKey) {
        $safe = $safe.Replace($ApiKey, '[redacted]')
    }
    $safe = $safe -replace '(?i)(x-api-key\s*[:=]\s*)\S+', '$1[redacted]'
    $safe = $safe -replace '(?i)(authorization\s*[:=]\s*bearer\s+)\S+', '$1[redacted]'
    return $safe.Trim()
}

function Add-CloudAttempt {
    param(
        [string]$Source,
        [bool]$Success,
        [string]$Message
    )

    $script:Attempts.Add([ordered]@{
        source = $Source
        success = $Success
        message = $Message
    })
}

function ConvertTo-CloudPath {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw 'A /api/... path is required.'
    }

    if ($Value.StartsWith('/api/')) {
        if ($Value -match '[\r\n#]') {
            throw 'Cloud API paths must not contain newlines or fragments.'
        }
        $pathOnly = ($Value -split '\?', 2)[0]
        if ($pathOnly -match '/dump/.*/download-url$') {
            throw 'Short-lived market dump download URLs are intentionally blocked.'
        }
        return $Value
    }

    $uri = $null
    if (-not [uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri)) {
        throw 'A /api/... path or absolute Fuyao API URL is required.'
    }
    if ($uri.UserInfo -or $uri.Fragment) {
        throw 'Cloud API URLs must not contain credentials or fragments.'
    }

    $allowedHosts = @(
        ([uri](Get-CloudBaseUrl)).Host
        'fuyao.aicubes.cn'
        'datahub.10jqka.com.cn'
    )
    if ($uri.Host -notin $allowedHosts) {
        throw "Cloud API host '$($uri.Host)' is not allowed."
    }
    if (-not $uri.AbsolutePath.StartsWith('/api/')) {
        throw 'Only /api/ paths are supported.'
    }
    if ($uri.AbsolutePath -match '/dump/.*/download-url$') {
        throw 'Short-lived market dump download URLs are intentionally blocked.'
    }
    return $uri.PathAndQuery
}

function Add-CloudQueryString {
    param(
        [string]$Url,
        [hashtable]$Parameters
    )

    if ($null -eq $Parameters -or $Parameters.Count -eq 0) {
        return $Url
    }

    $pairs = [System.Collections.Generic.List[string]]::new()
    foreach ($name in $Parameters.Keys) {
        $value = $Parameters[$name]
        if ($null -eq $value) {
            continue
        }
        if ($value -is [System.Array]) {
            $value = @($value | ForEach-Object { [string]$_ }) -join ','
        }
        elseif ($value -is [bool]) {
            $value = if ($value) { 'true' } else { 'false' }
        }
        elseif ($value -is [System.Collections.IEnumerable] -and $value -isnot [string]) {
            $value = @($value | ForEach-Object { [string]$_ }) -join ','
        }
        else {
            $value = [string]$value
        }
        $pairs.Add(
            "$([uri]::EscapeDataString([string]$name))=$([uri]::EscapeDataString($value))"
        )
    }

    if ($pairs.Count -eq 0) {
        return $Url
    }
    $separator = if ($Url.Contains('?')) { '&' } else { '?' }
    return "$Url$separator$($pairs -join '&')"
}

function Invoke-CloudApi {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathOrUrl,

        [hashtable]$Parameters = @{},

        [switch]$AllowBusinessError
    )

    $baseUrl = Get-CloudBaseUrl
    $path = ConvertTo-CloudPath $PathOrUrl
    $url = Add-CloudQueryString -Url "$baseUrl$path" -Parameters $Parameters
    $keyInfo = Get-CloudApiKeyInfo
    $apiKey = [string]$keyInfo.Key

    $headers = @{
        'X-api-key' = $apiKey
        Accept = 'application/json'
        'User-Agent' = 'codex-market-query/3.23.13'
    }

    $maxAttempts = 3
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            $response = Invoke-WebRequest `
                -Uri $url `
                -Method Get `
                -Headers $headers `
                -TimeoutSec $HttpTimeoutSec `
                -MaximumRedirection 0 `
                -SkipHttpErrorCheck
        }
        catch {
            $message = Protect-CloudMessage -Message $_.Exception.Message -ApiKey $apiKey
            if ($attempt -lt $maxAttempts) {
                Start-Sleep -Milliseconds (250 * $attempt)
                continue
            }
            throw "Cloud request failed after $attempt attempts: $message"
        }

        $status = [int]$response.StatusCode
        if ($status -ge 300 -and $status -lt 400) {
            throw 'Cloud API redirects are blocked to prevent credential forwarding.'
        }
        if ($status -eq 429 -and $attempt -lt $maxAttempts) {
            Start-Sleep -Seconds $attempt
            continue
        }
        if ($status -ge 500 -and $attempt -lt $maxAttempts) {
            Start-Sleep -Milliseconds (400 * $attempt)
            continue
        }

        $body = $null
        if (-not [string]::IsNullOrWhiteSpace($response.Content)) {
            try {
                $body = $response.Content | ConvertFrom-Json
            }
            catch {
                throw "Cloud API returned non-JSON content (HTTP $status)."
            }
        }

        if ($status -eq 401 -or $status -eq 403) {
            throw "Cloud authentication failed with HTTP $status."
        }
        if ($status -eq 429) {
            throw 'Cloud API rate limit was exceeded (HTTP 429). Retry later.'
        }
        if ($status -ge 400) {
            $message = if ($body.message) { [string]$body.message } else { 'no message' }
            throw "Cloud API returned HTTP ${status}: $message"
        }
        if ($null -eq $body) {
            throw "Cloud API returned an empty response (HTTP $status)."
        }

        $code = 0
        if ($null -ne $body.code) {
            $code = [int]$body.code
        }
        if ($code -ne 0 -and -not $AllowBusinessError) {
            $message = Protect-CloudMessage -Message ([string]$body.message) -ApiKey $apiKey
            throw "Cloud API business error code=${code}: $message"
        }

        return $body
    }

    throw 'Cloud request exhausted its retry budget.'
}

function Resolve-CloudSecurity {
    param([string]$Keyword)

    $response = Invoke-CloudApi -PathOrUrl '/api/meta/tickers/search' -Parameters @{
        q = $Keyword
        limit = 5
    }
    $items = @($response.data.item)
    if ($items.Count -eq 0) {
        throw "No security matched '$Keyword' in the cloud API."
    }
    $hit = $items |
        Where-Object { $_.asset_type -in @('a-share', 'a-share-index', 'fund-etf', 'fund-lof') } |
        Select-Object -First 1
    if (-not $hit) {
        $hit = $items | Select-Object -First 1
    }

    $market = switch ([string]$hit.exchange) {
        'SH' { 'USHA' }
        'SZ' { 'USZA' }
        'BJ' { 'USBJ' }
        default { [string]$hit.exchange }
    }

    return [ordered]@{
        keyword = $Keyword
        name = [string]$hit.name
        security = [string]$hit.thscode
        thscode = [string]$hit.thscode
        ticker = [string]$hit.ticker
        exchange = [string]$hit.exchange
        asset_type = [string]$hit.asset_type
        market = $market
        code = [string]$hit.ticker
    }
}

function Resolve-CloudSecurities {
    param([string]$Value)

    $targets = Split-SecurityTargets $Value
    return @(
        $targets | ForEach-Object { Resolve-CloudSecurity $_ }
    )
}

function ConvertTo-IdList {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return @()
    }

    return @(
        $Value -split '[,\s;]+' |
            Where-Object { $_ } |
            ForEach-Object { [int]$_ }
    )
}

function Split-SecurityTargets {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw 'A security code, name, or pinyin keyword is required.'
    }

    $targets = @(
        $Value -split '[,，;；]+' |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
    )
    if ($targets.Count -eq 0) {
        throw 'A security code, name, or pinyin keyword is required.'
    }
    return $targets
}

function Get-LumiSearchHits {
    param($Data)

    if ($null -eq $Data) {
        return @()
    }
    if ($Data.PSObject.Properties.Name -contains 'results') {
        return @(
            $Data.results |
                ForEach-Object { @($_.hits) } |
                Where-Object { $_ }
        )
    }
    if ($Data -is [System.Array]) {
        return @($Data)
    }
    return @($Data)
}

function Resolve-LumiSecurities {
    param([string]$Value)

    $targets = Split-SecurityTargets $Value
    $securities = @()

    foreach ($keyword in $targets) {
        $result = Invoke-LumiTool -Name 'search_securities' -Arguments @{
            keyword = $keyword
            limit = 5
        }
        $hit = Get-LumiSearchHits $result | Select-Object -First 1
        if (-not $hit -or -not $hit.market -or -not $hit.code) {
            throw "No security matched '$keyword'."
        }
        $securities += @{
            market = [string]$hit.market
            code = [string]$hit.code
            keyword = $keyword
            name = [string]$hit.name
            security = [string]$hit.security
        }
    }

    return $securities
}

function Invoke-SecurityQuery {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ToolName,

        [Parameter(Mandatory = $true)]
        [hashtable]$Arguments,

        [switch]$Single
    )

    $securities = @(Resolve-LumiSecurities $Target)
    if ($Single -and $securities.Count -ne 1) {
        throw "$ToolName only accepts one security per request."
    }

    $Arguments['securities'] = @(
        $securities | ForEach-Object {
            @{
                market = $_.market
                code = $_.code
            }
        }
    )
    $data = Invoke-LumiTool -Name $ToolName -Arguments $Arguments
    return [ordered]@{
        securities = @(
            $securities | ForEach-Object {
                [ordered]@{
                    keyword = $_.keyword
                    name = $_.name
                    security = $_.security
                    market = $_.market
                    code = $_.code
                }
            }
        )
        data = $data
    }
}

function ConvertFrom-ArgumentsJson {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return @{}
    }
    try {
        $parsed = $Value | ConvertFrom-Json -AsHashtable
    }
    catch {
        throw "ArgumentsJson is not a valid JSON object: $($_.Exception.Message)"
    }
    if ($parsed -isnot [hashtable]) {
        throw 'ArgumentsJson must contain one JSON object.'
    }
    return $parsed
}

function Get-CatalogRows {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('datahub', 'dataaccessor', 'subscribe', 'fields', 'cloud')]
        [string]$CatalogSource
    )

    $file = switch ($CatalogSource) {
        'datahub' { 'datahub-apis.csv' }
        'dataaccessor' { 'dataaccessor-apis.csv' }
        'subscribe' { 'dataaccessor-subscribe-apis.csv' }
        'fields' { 'dataaccessor-fields.csv' }
        'cloud' { 'cloud-apis.csv' }
    }
    return @(
        Import-Csv -LiteralPath (Join-Path $referenceRoot $file) |
            ForEach-Object {
                $row = $_
                $properties = [ordered]@{ catalog = $CatalogSource }
                foreach ($property in $row.PSObject.Properties) {
                    $properties[$property.Name] = $property.Value
                }
                [pscustomobject]$properties
            }
    )
}

function Invoke-DataHubGet {
    param([string]$UrlOrPath)

    if ([string]::IsNullOrWhiteSpace($UrlOrPath)) {
        throw 'datahub-get requires an absolute URL or /api/... path.'
    }

    $url = $UrlOrPath
    if ($url -match '^/api/') {
        $url = "https://datahub.10jqka.com.cn$url"
    }
    elseif ($url -match '^api/') {
        $url = "https://datahub.10jqka.com.cn/$url"
    }

    $uri = $null
    if (-not [uri]::TryCreate($url, [UriKind]::Absolute, [ref]$uri)) {
        throw 'datahub-get requires an absolute URL or /api/... path.'
    }
    if ($uri.Scheme -ne 'https' -or $uri.Host -ne 'datahub.10jqka.com.cn') {
        throw 'datahub-get only permits https://datahub.10jqka.com.cn URLs.'
    }
    if (-not $uri.AbsolutePath.StartsWith('/api/')) {
        throw 'datahub-get only permits /api/ paths on DataHub.'
    }
    if ($uri.UserInfo -or $uri.Fragment) {
        throw 'datahub-get rejects URL credentials and fragments.'
    }
    if ($uri.AbsolutePath -match '/dump/.*/download-url$') {
        throw 'Short-lived market dump download URLs are intentionally blocked.'
    }

    $body = Invoke-LumiTool -Name 'http_get' -Arguments @{ url = $url }
    if ($body -is [string]) {
        try {
            $body = $body | ConvertFrom-Json
        }
        catch {
        }
    }
    return $body
}

function Get-CloudCatalogRows {
    return @(
        Import-Csv -LiteralPath (Join-Path $referenceRoot 'cloud-apis.csv') |
            ForEach-Object {
                [ordered]@{
                    catalog = 'cloud'
                    method = $_.method
                    path = $_.path
                    title = $_.title
                    availability = $_.availability
                    requiredParams = $_.requiredParams
                    optionalParams = $_.optionalParams
                    pageUrl = $_.pageUrl
                }
            }
    )
}

function ConvertTo-CloudSearchItem {
    param($Item)

    return [ordered]@{
        security = [string]$Item.thscode
        name = [string]$Item.name
        code = [string]$Item.ticker
        market = [string]$Item.exchange
        thscode = [string]$Item.thscode
        ticker = [string]$Item.ticker
        exchange = [string]$Item.exchange
        asset_type = [string]$Item.asset_type
        currency = [string]$Item.currency
        list_date = $Item.list_date
        end_date = $Item.end_date
        last_trade_date = $Item.last_trade_date
        last_delivery_date = $Item.last_delivery_date
    }
}

function Invoke-CloudSearch {
    param([string]$Keyword)

    $parameters = @{
        q = $Keyword
        limit = [Math]::Min([Math]::Max($Limit, 1), 50)
    }
    if ($AssetType) {
        $parameters['asset_type'] = $AssetType
    }

    $response = Invoke-CloudApi `
        -PathOrUrl '/api/meta/tickers/search' `
        -Parameters $parameters
    $items = @($response.data.item)
    return [ordered]@{
        request_id = $response.request_id
        timestamp = $response.data.timestamp
        items = @($items | ForEach-Object { ConvertTo-CloudSearchItem $_ })
    }
}

function Invoke-CloudBlocks {
    $parameters = @{
        q = $Target
        asset_type = 'a-share-index'
        limit = [Math]::Min([Math]::Max($Limit, 1), 50)
    }
    $response = Invoke-CloudApi `
        -PathOrUrl '/api/meta/tickers/search' `
        -Parameters $parameters
    return [ordered]@{
        request_id = $response.request_id
        timestamp = $response.data.timestamp
        items = @(
            $response.data.item |
                ForEach-Object {
                    $item = ConvertTo-CloudSearchItem $_
                    $item['market'] = 'THS'
                    $item
                }
        )
    }
}

function Invoke-CloudRealtime {
    $securities = @(Resolve-CloudSecurities $Target)
    $response = Invoke-CloudApi `
        -PathOrUrl '/api/a-share/prices/snapshot' `
        -Parameters @{
            thscodes = @($securities | ForEach-Object { $_.thscode }) -join ','
        }

    $rows = @($response.data.item)
    $data = [ordered]@{}
    $fieldMap = [ordered]@{
        '5' = 'thscode'
        '6' = 'prev_price'
        '7' = 'open_price'
        '8' = 'high_price'
        '9' = 'low_price'
        '10' = 'last_price'
        '13' = 'volume'
        '19' = 'turnover'
        '55' = 'name'
        '199112' = 'price_change_ratio_pct'
        '264648' = 'price_change'
    }

    foreach ($security in $securities) {
        $row = $rows | Where-Object { $_.thscode -eq $security.thscode } | Select-Object -First 1
        if (-not $row) {
            continue
        }
        $record = [ordered]@{
            '5' = [string]$row.thscode
            '55' = [string]$security.name
        }
        foreach ($fieldId in $fieldMap.Keys) {
            if ($fieldId -in @('5', '55')) {
                continue
            }
            $propertyName = $fieldMap[$fieldId]
            if ($row.PSObject.Properties.Name -contains $propertyName) {
                $record[$fieldId] = $row.$propertyName
            }
        }
        $record['name'] = [string]$security.name
        $record['thscode'] = [string]$row.thscode
        $record['ticker'] = [string]$row.ticker
        $record['last_price'] = $row.last_price
        $record['price_change'] = $row.price_change
        $record['price_change_ratio_pct'] = $row.price_change_ratio_pct
        $record['open_price'] = $row.open_price
        $record['high_price'] = $row.high_price
        $record['low_price'] = $row.low_price
        $record['prev_price'] = $row.prev_price
        $record['volume'] = $row.volume
        $record['turnover'] = $row.turnover

        $key = $security.market + $security.code
        $data[$key] = $record
    }

    if ($data.Count -eq 0) {
        throw 'The cloud snapshot returned no matching securities.'
    }

    return [ordered]@{
        request_id = $response.request_id
        timestamp = $response.data.timestamp
        securities = @($securities)
        data = $data
    }
}

function ConvertTo-CloudMilliseconds {
    param([long]$Value)

    if ($Value -le 0) {
        throw 'Time values must be positive.'
    }
    if ($Value -lt 100000000000) {
        return $Value * 1000
    }
    return $Value
}

function Invoke-CloudCandle {
    if ($Period -ne 5) {
        throw 'The Fuyao cloud API currently supports A-share daily K-line only (Period=5).'
    }

    $securities = @(Resolve-CloudSecurities $Target)
    if ($securities.Count -ne 1) {
        throw 'Cloud candle_query accepts exactly one security per request.'
    }
    $security = $securities[0]

    if ($HasBeginTime -ne $HasEndTime) {
        throw 'candle requires both -BeginTime and -EndTime, or neither.'
    }

    if ($HasBeginTime -and $HasEndTime) {
        $startMs = ConvertTo-CloudMilliseconds $BeginTime
        $endMs = ConvertTo-CloudMilliseconds $EndTime
    }
    elseif ($HasTradeDate) {
        $date = [datetime]::ParseExact(
            [string]$TradeDate,
            'yyyyMMdd',
            [System.Globalization.CultureInfo]::InvariantCulture
        )
        $start = [DateTimeOffset]::new(
            [datetime]::SpecifyKind($date, [DateTimeKind]::Unspecified),
            [TimeSpan]::FromHours(8)
        )
        $startMs = $start.ToUnixTimeMilliseconds()
        $endMs = $start.AddDays(1).AddMilliseconds(-1).ToUnixTimeMilliseconds()
    }
    else {
        $endMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        $lookbackDays = [Math]::Min(
            3650,
            [Math]::Max(14, [Math]::Ceiling([Math]::Max($Count, 1) * 2.2))
        )
        $startMs = [DateTimeOffset]::UtcNow.AddDays(-$lookbackDays).ToUnixTimeMilliseconds()
    }

    if ($startMs -gt $endMs) {
        throw 'candle start time must not be later than end time.'
    }

    $adjust = switch ($AdjustType) {
        0 { 'none' }
        1 { 'forward' }
        2 { 'backward' }
        default { throw "Unsupported AdjustType '$AdjustType'. Use 0, 1, or 2." }
    }

    $response = Invoke-CloudApi `
        -PathOrUrl '/api/a-share/prices/historical' `
        -Parameters @{
            thscode = $security.thscode
            interval = '1d'
            start = $startMs
            end = $endMs
            adjust = $adjust
        }

    $bars = @(
        $response.data.item |
            Sort-Object date_ms |
            Select-Object -Last ([Math]::Max($Count, 1)) |
            ForEach-Object {
                $date = [DateTimeOffset]::FromUnixTimeMilliseconds(
                    [long]$_.date_ms
                ).ToOffset([TimeSpan]::FromHours(8))
                [ordered]@{
                    '1' = [int]$date.ToString('yyyyMMdd')
                    '7' = $_.open_price
                    '8' = $_.high_price
                    '9' = $_.low_price
                    '11' = $_.close_price
                    '13' = $_.volume
                    '19' = $_.turnover
                    time = [long]$date.ToUnixTimeSeconds()
                    date_ms = [long]$_.date_ms
                }
            }
    )

    $key = $security.market + $security.code
    return [ordered]@{
        request_id = $response.request_id
        timestamp = $response.data.timestamp
        securities = @($securities)
        period = 5
        adjustType = $AdjustType
        data = [ordered]@{
            $key = $bars
        }
    }
}

function Invoke-CloudSector {
    if ([string]::IsNullOrWhiteSpace($Target)) {
        throw 'sector requires an index thscode or block name.'
    }

    $sector = $null
    if ($Target -match '^[0-9A-Za-z]+\.[A-Za-z]{2}$') {
        $sector = [ordered]@{
            name = $Target
            thscode = $Target.ToUpperInvariant()
            ticker = ($Target -split '\.')[0]
            exchange = ($Target -split '\.')[-1]
            asset_type = 'a-share-index'
        }
    }
    else {
        $search = Invoke-CloudApi `
            -PathOrUrl '/api/meta/tickers/search' `
            -Parameters @{
                q = $Target
                asset_type = 'a-share-index'
                limit = 5
            }
        $hit = @($search.data.item) | Select-Object -First 1
        if (-not $hit) {
            throw "No cloud sector matched '$Target'."
        }
        $sector = [ordered]@{
            name = [string]$hit.name
            thscode = [string]$hit.thscode
            ticker = [string]$hit.ticker
            exchange = [string]$hit.exchange
            asset_type = [string]$hit.asset_type
        }
    }

    $response = Invoke-CloudApi `
        -PathOrUrl '/api/a-share-index/constituents/ths-stock-list' `
        -Parameters @{ thscode = $sector.thscode }
    return [ordered]@{
        request_id = $response.request_id
        timestamp = $response.data.timestamp
        sector = $sector
        members = @($response.data.item)
    }
}

function Invoke-CloudGet {
    $parameters = ConvertFrom-ArgumentsJson $ArgumentsJson
    return Invoke-CloudApi -PathOrUrl $Target -Parameters $parameters
}

function Invoke-DataSource {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Operation,

        [scriptblock]$Cloud,

        [scriptblock]$Local,

        [bool]$CloudSupported = $true,

        [bool]$PreferLocal = $false
    )

    $cloudConfigured = $false
    if ($CloudSupported) {
        $cloudConfigured = Test-CloudApiKeyConfigured
    }

    if ($Mode -eq 'cloud') {
        if (-not $CloudSupported -or -not $Cloud) {
            throw "$Operation is not available through the Fuyao cloud API. Use -Mode local."
        }
        if (-not $cloudConfigured) {
            throw "$Operation requires a Fuyao API Key. Set $ApiKeyEnv or run cloud_key.ps1 -Action set."
        }
        try {
            $result = & $Cloud
            Add-CloudAttempt -Source 'cloud' -Success $true -Message ''
            $script:SelectedSource = 'cloud'
            return $result
        }
        catch {
            $message = Protect-CloudMessage -Message $_.Exception.Message -ApiKey $null
            Add-CloudAttempt -Source 'cloud' -Success $false -Message $message
            throw "$Operation failed via cloud: $message"
        }
    }

    if ($Mode -eq 'local') {
        if (-not $Local) {
            throw "$Operation is only available through the Fuyao cloud API. Use -Mode cloud."
        }
        try {
            $result = & $Local
            Add-CloudAttempt -Source 'local' -Success $true -Message ''
            $script:SelectedSource = 'local'
            return $result
        }
        catch {
            $message = $_.Exception.Message
            Add-CloudAttempt -Source 'local' -Success $false -Message $message
            throw "$Operation failed via local MCP: $message"
        }
    }

    if (-not $Local -and $CloudSupported -and -not $cloudConfigured) {
        throw "$Operation requires a Fuyao API Key. Set $ApiKeyEnv or run cloud_key.ps1 -Action set."
    }

    $cloudError = $null
    $localError = $null

    if ($PreferLocal -and $Local) {
        try {
            $result = & $Local
            Add-CloudAttempt -Source 'local' -Success $true -Message ''
            $script:SelectedSource = 'local'
            return $result
        }
        catch {
            $localError = $_.Exception.Message
            Add-CloudAttempt -Source 'local' -Success $false -Message $localError
        }
    }

    if ($CloudSupported -and $Cloud -and $cloudConfigured) {
        try {
            $result = & $Cloud
            Add-CloudAttempt -Source 'cloud' -Success $true -Message ''
            $script:SelectedSource = 'cloud'
            return $result
        }
        catch {
            $cloudError = Protect-CloudMessage -Message $_.Exception.Message -ApiKey $null
            Add-CloudAttempt -Source 'cloud' -Success $false -Message $cloudError
        }
    }

    if (-not $PreferLocal -and $Local) {
        try {
            $result = & $Local
            Add-CloudAttempt -Source 'local' -Success $true -Message ''
            $script:SelectedSource = 'local'
            return $result
        }
        catch {
            $localError = $_.Exception.Message
            Add-CloudAttempt -Source 'local' -Success $false -Message $localError
        }
    }

    if ($localError -and $cloudError) {
        throw "$Operation failed via both sources. Cloud: $cloudError Local: $localError"
    }
    if ($localError) {
        throw "$Operation failed via local MCP: $localError"
    }
    if ($cloudError) {
        throw "$Operation failed via cloud: $cloudError"
    }
    throw "$Operation has no available data source."
}

$output = switch ($Action) {
    'catalog' {
        $script:SelectedSource = 'catalog'
        $rows = @(Get-CatalogRows -CatalogSource $Source)
        if ($Query) {
            $rows = @(
                $rows |
                    Where-Object {
                        $line = ($_.PSObject.Properties.Value | ForEach-Object { [string]$_ }) -join ' '
                        $line.IndexOf($Query, [StringComparison]::OrdinalIgnoreCase) -ge 0
                    }
            )
        }
        $total = $rows.Count
        if (-not $All -and $rows.Count -gt $Limit) {
            $rows = @($rows | Select-Object -First $Limit)
        }
        [ordered]@{
            source = $Source
            count = $rows.Count
            total = $total
            truncated = -not $All -and $total -gt $rows.Count
            items = @($rows)
        }
    }
    'tools' {
        Invoke-DataSource -Operation 'tools' -CloudSupported $false -PreferLocal $true -Local {
            $helperArguments = @(
                '-NoProfile',
                '-File', $helper,
                '-Action', 'list-tools'
            )
            if ($User) {
                $helperArguments += @('-User', $User)
            }
            $processOutput = & pwsh @helperArguments 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Lumi MCP call failed: $($processOutput -join ' ')"
            }
            $result = ($processOutput -join "`n") | ConvertFrom-Json
            $tools = @(
                $result.result.tools |
                    Select-Object -First $Limit |
                    ForEach-Object {
                        [ordered]@{
                            name = $_.name
                            description = $_.description
                        }
                    }
            )
            [ordered]@{
                count = $tools.Count
                items = $tools
            }
        }
    }
    'search' {
        $targets = Split-SecurityTargets $Target
        $keyword = $targets | Select-Object -First 1
        Invoke-DataSource -Operation 'search' -PreferLocal $true -Cloud {
            Invoke-CloudSearch $keyword
        } -Local {
            Invoke-LumiTool -Name 'search_securities' -Arguments @{
                keyword = $keyword
                limit = $Limit
            }
        }
    }
    'blocks' {
        if ([string]::IsNullOrWhiteSpace($Target)) {
            throw 'blocks requires a block-name keyword.'
        }
        Invoke-DataSource -Operation 'blocks' -PreferLocal $true -Cloud {
            Invoke-CloudBlocks
        } -Local {
            Invoke-LumiTool -Name 'search_blocks' -Arguments @{
                keyword = $Target
                limit = $Limit
            }
        }
    }
    'realtime' {
        $realtimeFields = if ($HasFields) {
            $Fields
        }
        else {
            '6,7,8,9,10,13,19,55,199112,264648'
        }
        Invoke-DataSource -Operation 'realtime' -PreferLocal $true -Cloud {
            Invoke-CloudRealtime
        } -Local {
            Invoke-SecurityQuery -ToolName 'realtime_query' -Arguments @{
                fields = ConvertTo-IdList $realtimeFields
            }
        }
    }
    'candle' {
        $candleFields = if ($HasFields) {
            $Fields
        }
        else {
            '1,7,8,9,11,13,19'
        }
        $timeRange = if ($HasBeginTime -or $HasEndTime) {
            if (-not $HasBeginTime -or -not $HasEndTime) {
                throw 'candle requires both -BeginTime and -EndTime, or neither.'
            }
            @{
                beginTime = $BeginTime
                endTime = $EndTime
            }
        }
        elseif ($HasTradeDate) {
            @{ tradeDate = $TradeDate }
        }
        else {
            @{
                offset = $Count
                toLatest = $true
            }
        }

        Invoke-DataSource `
            -Operation 'candle' `
            -PreferLocal $true `
            -CloudSupported ($Period -eq 5) `
            -Cloud {
                Invoke-CloudCandle
            } `
            -Local {
                Invoke-SecurityQuery -ToolName 'candle_query' -Arguments @{
                    fields = ConvertTo-IdList $candleFields
                    period = $Period
                    adjustType = $AdjustType
                    timeRange = $timeRange
                } -Single
            }
    }
    'trend' {
        $trendFields = if ($HasFields) { $Fields } else { '1,10,13,19' }
        $arguments = @{
            fields = ConvertTo-IdList $trendFields
        }
        if ($Api) {
            $arguments['api'] = $Api
        }
        if ($PSBoundParameters.ContainsKey('TradeClass')) {
            $arguments['tradeClass'] = $TradeClass
        }
        elseif ($Api -eq 'RequestTrendDataAsync') {
            $arguments['tradeClass'] = 1
        }
        if ($HasTradeDate) {
            $arguments['tradeDate'] = $TradeDate
        }
        Invoke-DataSource -Operation 'trend' -CloudSupported $false -PreferLocal $true -Local {
            Invoke-SecurityQuery -ToolName 'trend_query' -Arguments $arguments
        }
    }
    'tick' {
        $tickFields = if ($HasFields) { $Fields } else { '1,10,12,18,49' }
        $arguments = @{
            fields = ConvertTo-IdList $tickFields
            count = $Count
        }
        if ($Api) {
            $arguments['api'] = $Api
        }
        Invoke-DataSource -Operation 'tick' -CloudSupported $false -PreferLocal $true -Local {
            Invoke-SecurityQuery -ToolName 'tick_query' -Arguments $arguments
        }
    }
    'sort' {
        $arguments = @{
            block = $Block
            sortField = $SortField
            sortOrder = $SortOrder
            offset = $Offset
            count = [Math]::Min($Count, 200)
        }
        if ($ExcludeBlocks) {
            $arguments['excludeBlocks'] = ConvertTo-IdList $ExcludeBlocks
        }
        Invoke-DataSource -Operation 'sort' -CloudSupported $false -PreferLocal $true -Local {
            Invoke-LumiTool -Name 'sort_query' -Arguments $arguments
        }
    }
    'subscribe' {
        if (-not $SubscribeApi) {
            throw 'subscribe requires -SubscribeApi.'
        }
        $parameters = ConvertFrom-ArgumentsJson $ArgumentsJson
        if ($Target) {
            $securities = @(Resolve-LumiSecurities $Target)
            $parameters['securities'] = @(
                $securities | ForEach-Object {
                    @{
                        market = $_.market
                        code = $_.code
                    }
                }
            )
        }
        if ($HasFields) {
            $parameters['fields'] = ConvertTo-IdList $Fields
        }
        Invoke-DataSource -Operation 'subscribe' -CloudSupported $false -PreferLocal $true -Local {
            Invoke-LumiTool -Name 'data_subscribe' -Arguments @{
                api = $SubscribeApi
                parameters = $parameters
                timeout_ms = $TimeoutMs
            }
        }
    }
    'fields' {
        $script:SelectedSource = 'catalog'
        $rows = @(Get-CatalogRows -CatalogSource 'fields')
        if ($DataType) {
            $rows = @($rows | Where-Object { $_.dataType -eq $DataType })
        }
        if ($Query) {
            $rows = @(
                $rows |
                    Where-Object {
                        $line = ($_.PSObject.Properties.Value | ForEach-Object { [string]$_ }) -join ' '
                        $line.IndexOf($Query, [StringComparison]::OrdinalIgnoreCase) -ge 0
                    }
            )
        }
        $total = $rows.Count
        if (-not $All -and $rows.Count -gt $Limit) {
            $rows = @($rows | Select-Object -First $Limit)
        }
        [ordered]@{
            count = $rows.Count
            total = $total
            truncated = -not $All -and $total -gt $rows.Count
            items = @($rows)
        }
    }
    'datahub-get' {
        Invoke-DataSource -Operation 'datahub-get' -PreferLocal $true -Cloud {
            Invoke-CloudApi -PathOrUrl $Target
        } -Local {
            $result = Invoke-DataHubGet -UrlOrPath $Target
            if ($Mode -eq 'auto' -and $null -ne $result.code -and [int]$result.code -ne 0) {
                throw "Local DataHub business error code=$([int]$result.code): $($result.message)"
            }
            $result
        }
    }
    'sectors' {
        Invoke-DataSource -Operation 'sectors' -CloudSupported $false -PreferLocal $true -Local {
            Invoke-LumiTool -Name 'manageSector' -Arguments @{
                operation = 'query'
            }
        }
    }
    'watchlist' {
        Invoke-DataSource -Operation 'watchlist' -CloudSupported $false -PreferLocal $true -Local {
            Invoke-LumiTool -Name 'manageSector' -Arguments @{
                operation = 'query'
                sectorId = '-1'
            }
        }
    }
    'sector' {
        if ([string]::IsNullOrWhiteSpace($Target)) {
            throw 'sector requires a numeric sector ID or group name.'
        }
        $arguments = @{ operation = 'query' }
        if ($Target -match '^\d+$') {
            $arguments['sectorId'] = $Target
        }
        else {
            $arguments['sectorName'] = $Target
        }
        $cloudSectorSupported = $Target -notmatch '^\d+$'
        Invoke-DataSource `
            -Operation 'sector' `
            -PreferLocal $true `
            -CloudSupported $cloudSectorSupported `
            -Cloud {
                Invoke-CloudSector
            } `
            -Local {
                Invoke-LumiTool -Name 'manageSector' -Arguments $arguments
            }
    }
    'call' {
        $readOnlyTools = @(
            'search_securities',
            'search_blocks',
            'search_fields',
            'realtime_query',
            'candle_query',
            'trend_query',
            'tick_query',
            'sort_query',
            'data_subscribe',
            'indicator_query',
            'wencai_query',
            'manageSector',
            'read_doc'
        )
        if ([string]::IsNullOrWhiteSpace($Tool)) {
            throw 'call requires -Tool.'
        }
        if ($Tool -notin $readOnlyTools) {
            throw "Tool '$Tool' is not on the read-only query allowlist."
        }
        $arguments = ConvertFrom-ArgumentsJson $ArgumentsJson
        if ($Tool -eq 'manageSector' -and $arguments['operation'] -ne 'query') {
            throw 'This skill only exposes manageSector with operation=query.'
        }
        Invoke-DataSource -Operation 'call' -CloudSupported $false -PreferLocal $true -Local {
            Invoke-LumiTool -Name $Tool -Arguments $arguments
        }
    }
    'cloud-get' {
        if ([string]::IsNullOrWhiteSpace($Target)) {
            throw 'cloud-get requires a /api/... path or Fuyao API URL.'
        }
        Invoke-DataSource -Operation 'cloud-get' -Cloud {
            Invoke-CloudGet
        }
    }
    'status' {
        $script:SelectedSource = 'status'
        [ordered]@{
            mode = $Mode
            local = [ordered]@{
                configured = Test-LocalBridgeConfigured
                source = 'Lumi MCP'
                scope = 'Windows desktop client'
            }
            cloud = [ordered]@{
                configured = Test-CloudApiKeyConfigured
                source = 'Hithink Fuyao REST API'
                baseUrl = Get-CloudBaseUrl
                apiKeyEnv = $ApiKeyEnv
                encryptedKeyPath = Join-Path $env:LOCALAPPDATA 'ThsMarketQuery\fuyao-api-key.dpapi'
            }
            capabilities = [ordered]@{
                cloud = @(
                    'search',
                    'blocks',
                    'realtime',
                    'candle-daily',
                    'sector-by-index',
                    'datahub-get',
                    'cloud-get',
                    'catalog-cloud'
                )
                localOnly = @(
                    'candle-intraday-week-month',
                    'trend',
                    'tick',
                    'sort',
                    'subscribe',
                    'watchlist',
                    'sectors',
                    'call'
                )
            }
        }
    }
}

if ($IncludeMeta) {
    [ordered]@{
        _meta = [ordered]@{
            requestedMode = $Mode
            source = $script:SelectedSource
            attempts = @($script:Attempts)
            fetchedAt = [DateTimeOffset]::UtcNow.ToString('o')
        }
        data = $output
    } | ConvertTo-Json -Depth 40
}
else {
    $output | ConvertTo-Json -Depth 40
}
