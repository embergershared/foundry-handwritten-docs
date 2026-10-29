targetScope = 'resourceGroup'

@minLength(2)
@maxLength(64)
param name string
param location string = resourceGroup().location
param tags object = {}

@allowed([
  'Enabled'
  'Disabled'
])
param publicNetworkAccess string = 'Disabled'

@description('Single explicitly approved workstation IPv4. Empty means deny all clients.')
@maxLength(15)
param allowedClientIpv4 string = ''
param operatorPrincipalIds array = []
param enableRoleAssignments bool = true
param logAnalyticsWorkspaceId string = ''

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: name
  location: location
  tags: tags
  kind: 'FormRecognizer'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: name
    disableLocalAuth: true
    publicNetworkAccess: publicNetworkAccess
    networkAcls: {
      defaultAction: 'Deny'
      ipRules: empty(allowedClientIpv4)
        ? []
        : [
            {
              value: allowedClientIpv4
            }
          ]
      virtualNetworkRules: []
    }
  }
}

resource users 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for principalId in (enableRoleAssignments ? operatorPrincipalIds : []): {
    name: guid(account.id, principalId, 'a97b65f3-24c7-4388-baec-2e87135dc908')
    scope: account
    properties: {
      principalId: principalId
      roleDefinitionId: subscriptionResourceId(
        'Microsoft.Authorization/roleDefinitions',
        'a97b65f3-24c7-4388-baec-2e87135dc908'
      )
    }
  }
]

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsWorkspaceId)) {
  name: 'metrics'
  scope: account
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
    logs: []
  }
}

output id string = account.id
output name string = account.name
output endpoint string = account.properties.endpoint
