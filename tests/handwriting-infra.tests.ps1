. (Join-Path $PSScriptRoot 'assert.ps1')
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot 'arm-expression.ps1')
. (Get-RepoPath 'scripts/handwriting-settings.ps1')

function New-TestAiSettings {
    $settings = Get-HandwritingDeploymentSettings -ReadValue { param($name) '' }
    $settings.AZURE_AI_PUBLIC_NETWORK_ACCESS = 'Enabled'
    $settings.AZURE_AI_ALLOWED_CLIENT_IPV4 = '203.0.113.8'
    return $settings
}

function New-TestModelEvidence {
    return @{
        Models = @([pscustomobject] @{
            kind = 'AIServices'
            model = [pscustomobject] @{
                name = 'gpt-4.1'; version = '2025-04-14'; lifecycleStatus = 'GenerallyAvailable'
                deprecation = [pscustomobject] @{ inference = $null }
                skus = @([pscustomobject] @{
                    name = 'Standard'; usageName = 'OpenAI.Standard.gpt4.1'
                    capacity = [pscustomobject] @{ minimum = 1; maximum = 100; step = 1 }
                })
            }
        })
        Usage = @([pscustomobject] @{
            name = [pscustomobject] @{ value = 'OpenAI.Standard.gpt4.1' }
            limit = 100; currentValue = 0
        })
    }
}

Test-Case 'AI settings require one explicit public IPv4 and explicit roles' {
    $settings = New-TestAiSettings
    Assert-HandwritingDeploymentSettings -Settings $settings -AssignRoles $true -OperatorCount 1
    foreach ($bad in @('', '0.0.0.0', '0.0.0.0/0', '203.0.113.8/32', '::1', '127.0.0.1', '10.1.2.3', '192.168.1.2', '224.1.2.3', '1.2.3', '01.2.3.4')) {
        Assert-Throws -Action { Assert-HandwritingClientIpv4 -Value $bad } -Message 'Unsafe client addresses must fail closed.'
    }
    Assert-Throws -Action {
        Assert-HandwritingDeploymentSettings -Settings $settings -AssignRoles $false -OperatorCount 1
    } -Message 'AI cannot silently omit operator grants.'
    Assert-Throws -Action {
        Assert-HandwritingDeploymentSettings -Settings $settings -AssignRoles $true -OperatorCount 0
    } -Message 'AI requires an explicit operator.'
    $settings.AZURE_AI_PUBLIC_NETWORK_ACCESS = 'Disabled'
    Assert-Throws -Action {
        Assert-HandwritingDeploymentSettings -Settings $settings -AssignRoles $true -OperatorCount 1
    } -Message 'Do not pretend private AI access is implemented.'
}

Test-Case 'AI preflight rejects unpinned models and invalid capacities' {
    foreach ($bad in @('latest', '', '2025-1-1')) {
        $settings = New-TestAiSettings
        $settings.AZURE_VISION_MODEL_VERSION = $bad
        Assert-Throws -Action {
            Assert-HandwritingDeploymentSettings -Settings $settings -AssignRoles $true -OperatorCount 1
        } -Message 'A model version must be pinned.'
    }
    foreach ($bad in @('0', '-1', '1.5', 'many')) {
        $settings = New-TestAiSettings
        $settings.AZURE_VISION_CAPACITY = $bad
        Assert-Throws -Action {
            Assert-HandwritingDeploymentSettings -Settings $settings -AssignRoles $true -OperatorCount 1
        } -Message 'Capacity must be a positive integer.'
    }
}

Test-Case 'Model discovery uses nested SKU metadata and real regional quota' {
    $settings = New-TestAiSettings
    $evidence = New-TestModelEvidence
    Assert-HandwritingModelQuota -Settings $settings @evidence
    $evidence.Usage[0].currentValue = 95
    Assert-Throws -Action { Assert-HandwritingModelQuota -Settings $settings @evidence } `
        -Message 'Insufficient quota must stop deployment.'
    $evidence = New-TestModelEvidence
    $evidence.Models[0].model.skus[0].name = 'GlobalStandard'
    Assert-Throws -Action { Assert-HandwritingModelQuota -Settings $settings @evidence } `
        -Message 'There is no global fallback.'
    $evidence = New-TestModelEvidence
    $evidence.Models[0].model.version = '2025-01-01'
    Assert-Throws -Action { Assert-HandwritingModelQuota -Settings $settings @evidence } `
        -Message 'A different pinned version cannot satisfy the request.'
    $evidence = New-TestModelEvidence
    $evidence.Models[0].model.deprecation.inference = '2020-01-01T00:00:00Z'
    Assert-Throws -Action { Assert-HandwritingModelQuota -Settings $settings @evidence } `
        -Message 'A retired model cannot be deployed.'
}

Test-Case 'Both recognition modules disable keys and all network bypasses' {
    foreach ($moduleName in @('ai-foundry', 'document-intelligence')) {
        $template = Get-CompiledTemplate -BicepPath (Get-RepoPath "infra/modules/$moduleName/main.bicep")
        $account = @($template.resources | Where-Object type -eq 'Microsoft.CognitiveServices/accounts')[0]
        Assert-Equal -Actual $account.properties.disableLocalAuth -Expected $true -Message 'Keys must be disabled.'
        Assert-Equal -Actual $account.properties.networkAcls.defaultAction -Expected 'Deny' -Message 'No default allow.'
        if ($moduleName -eq 'ai-foundry') {
            Assert-Equal -Actual $account.properties.networkAcls.bypass -Expected 'None' -Message 'No trusted-service bypass.'
        }
        else {
            Assert-True -Condition ($null -eq $account.properties.networkAcls.PSObject.Properties['bypass']) `
                -Message 'FormRecognizer rejects even bypass None; do not emit its unsupported trusted-service setting.'
        }
        Assert-True -Condition ($account.properties.networkAcls.ipRules -match 'allowedClientIpv4') -Message 'Only explicit client IP.'
        $metrics = @($template.resources | Where-Object type -eq 'Microsoft.Insights/diagnosticSettings')[0]
        Assert-Equal -Actual $metrics.properties.metrics[0].category -Expected 'AllMetrics' -Message 'Only metrics.'
        Assert-Equal -Actual $metrics.properties.logs.Count -Expected 0 -Message 'No request/content logs.'
    }
}

Test-Case 'Foundry project and inference grants use distinct scopes' {
    $template = Get-CompiledTemplate -BicepPath (Get-RepoPath 'infra/modules/ai-foundry/main.bicep')
    $roles = @($template.resources | Where-Object type -eq 'Microsoft.Authorization/roleAssignments')
    Assert-Equal -Actual $roles.Count -Expected 2 -Message 'Separate project and account grants.'
    $inference = @($roles | Where-Object { $_.properties.roleDefinitionId -match '5e0bd9bd' })[0]
    $project = @($roles | Where-Object { $_.properties.roleDefinitionId -match '53ca6127' })[0]
    Assert-NotMatch -Actual $inference.scope -Pattern 'projects' -Message 'Inference scope is the account.'
    Assert-Match -Actual $project.scope -Pattern 'projects' -Message 'Azure AI User is project-scoped.'
}

Test-Case 'Recognition services remain opt-in in every existing profile' {
    Assert-Equal -Actual (Invoke-ArmExpression -Expression '[false()]' -Template ([pscustomobject] @{})) `
        -Expected $false -Message 'The evaluator supports compiled boolean constants.'
    Assert-Equal -Actual (Invoke-ArmExpression -Expression '[true()]' -Template ([pscustomobject] @{})) `
        -Expected $true -Message 'The evaluator supports compiled boolean constants.'
    $template = Get-CompiledTemplate -BicepPath (Get-RepoPath 'infra/main.bicep')
    foreach ($profileName in @('core', 'private', 'full')) {
        $flags = Get-ProfileFeatureFlags -Template $template -ProfileName $profileName
        Assert-Equal -Actual $flags.deployAiFoundry -Expected $false -Message 'Foundry is not a profile default.'
        Assert-Equal -Actual $flags.deployDocumentIntelligence -Expected $false -Message 'DI is not a profile default.'
    }
    $flags = Get-ProfileFeatureFlags -Template $template -ProfileName core -Overrides @{ aiFoundry = $true; documentIntelligence = $true }
    Assert-Equal -Actual $flags.deployAiFoundry -Expected $true -Message 'Explicit Foundry opt-in.'
    Assert-Equal -Actual $flags.deployDocumentIntelligence -Expected $true -Message 'Explicit DI opt-in.'
    $composition = Get-Content -Raw (Get-RepoPath 'infra/main.bicep')
    Assert-Match -Actual $composition -Pattern "sku: 'Standard'" -Message 'Composition never defaults to a global deployment.'
}
