function Assert-HandwritingClientIpv4 {
    param([Parameter(Mandatory)] [AllowEmptyString()] [string] $Value)

    $address = $null
    if (-not [Net.IPAddress]::TryParse($Value, [ref] $address) -or
        $address.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
        $address.ToString() -cne $Value) {
        throw 'AZURE_AI_ALLOWED_CLIENT_IPV4 must be one canonical IPv4 address, not a CIDR, hostname or IPv6 address.'
    }
    $bytes = $address.GetAddressBytes()
    if ($bytes[0] -eq 0 -or $bytes[0] -eq 10 -or $bytes[0] -eq 127 -or $bytes[0] -ge 224 -or
        ($bytes[0] -eq 169 -and $bytes[1] -eq 254) -or
        ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
        ($bytes[0] -eq 192 -and $bytes[1] -eq 168) -or
        ($bytes[0] -eq 100 -and $bytes[1] -ge 64 -and $bytes[1] -le 127)) {
        throw 'AZURE_AI_ALLOWED_CLIENT_IPV4 must be the approved public workstation egress address.'
    }
}

function Get-HandwritingDeploymentSettings {
    param([Parameter(Mandatory)] [scriptblock] $ReadValue)

    $defaults = [ordered] @{
        AZURE_AI_PUBLIC_NETWORK_ACCESS = 'Disabled'
        AZURE_AI_ALLOWED_CLIENT_IPV4 = ''
        AZURE_VISION_DEPLOYMENT = 'handwriting-vision'
        AZURE_VISION_MODEL = 'gpt-4.1'
        AZURE_VISION_MODEL_VERSION = '2025-04-14'
        AZURE_VISION_CAPACITY = '10'
    }
    $settings = @{}
    foreach ($name in $defaults.Keys) {
        $value = & $ReadValue $name
        $settings[$name] = if ([string]::IsNullOrWhiteSpace($value)) { $defaults[$name] } else { $value.Trim() }
    }
    return $settings
}

function Assert-HandwritingDeploymentSettings {
    param(
        [Parameter(Mandatory)] [hashtable] $Settings,
        [Parameter(Mandatory)] [bool] $AssignRoles,
        [Parameter(Mandatory)] [int] $OperatorCount
    )

    if ($Settings.AZURE_AI_PUBLIC_NETWORK_ACCESS -cne 'Enabled') {
        throw 'AI opt-ins currently require explicitly approved public access. Private AI endpoints are not composed; do not enable AI services until a reachable access design is approved.'
    }
    Assert-HandwritingClientIpv4 -Value $Settings.AZURE_AI_ALLOWED_CLIENT_IPV4
    if (-not $AssignRoles -or $OperatorCount -lt 1) {
        throw 'AI opt-ins require roleAssignments and at least one explicit AZURE_OPERATOR_PRINCIPAL_IDS entry.'
    }
    if ($Settings.AZURE_VISION_DEPLOYMENT -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$') {
        throw 'AZURE_VISION_DEPLOYMENT must be a valid 1-64 character deployment name.'
    }
    if ($Settings.AZURE_VISION_MODEL -cnotmatch '^[a-z0-9][a-z0-9.-]+$' -or
        $Settings.AZURE_VISION_MODEL_VERSION -cnotmatch '^\d{4}-\d{2}-\d{2}$') {
        throw 'AI model name and pinned yyyy-MM-dd version are required; latest is not supported.'
    }
    $capacity = 0
    if (-not [int]::TryParse($Settings.AZURE_VISION_CAPACITY, [ref] $capacity) -or $capacity -lt 1) {
        throw 'AZURE_VISION_CAPACITY must be a positive integer.'
    }
}

function Assert-HandwritingModelQuota {
    param(
        [Parameter(Mandatory)] [hashtable] $Settings,
        [Parameter(Mandatory)] [object[]] $Models,
        [Parameter(Mandatory)] [object[]] $Usage
    )

    $matches = @($Models | Where-Object {
        $_.kind -eq 'AIServices' -and $_.model.name -ceq $Settings.AZURE_VISION_MODEL -and
        $_.model.version -ceq $Settings.AZURE_VISION_MODEL_VERSION
    })
    if ($matches.Count -ne 1) {
        throw 'Pinned vision model/version is unavailable or ambiguous in the selected region.'
    }
    $model = $matches[0].model
    if ($model.lifecycleStatus -in @('Deprecated', 'Disabled') -or
        ($model.deprecation.inference -and [DateTimeOffset]::Parse($model.deprecation.inference) -le [DateTimeOffset]::UtcNow)) {
        throw 'The pinned vision model is retired or disabled. Obtain approval for a replacement.'
    }
    $skus = @($model.skus | Where-Object name -CEQ 'Standard')
    if ($skus.Count -ne 1) {
        throw 'Regional Standard SKU is unavailable; no global or provisioned fallback is permitted.'
    }
    $capacity = [int] $Settings.AZURE_VISION_CAPACITY
    $limits = $skus[0].capacity
    if (($null -ne $limits.minimum -and $capacity -lt $limits.minimum) -or
        ($null -ne $limits.maximum -and $capacity -gt $limits.maximum) -or
        ($null -ne $limits.step -and $limits.step -gt 0 -and
            (($capacity - [int] $limits.minimum) % $limits.step) -ne 0)) {
        throw 'Requested capacity does not satisfy the advertised model SKU limits.'
    }
    $quotas = @($Usage | Where-Object { $_.name.value -ceq $skus[0].usageName })
    if ($quotas.Count -ne 1 -or $null -eq $quotas[0].limit -or $null -eq $quotas[0].currentValue -or
        ($quotas[0].limit - $quotas[0].currentValue) -lt $capacity) {
        throw 'Regional model quota is missing or insufficient; no automatic quota increase is permitted.'
    }
}
