targetScope = 'resourceGroup'

@description('Specify the Azure region to place the application definition.')
param location string = resourceGroup().location

@description('Specify the Application Client Id.')
param applicationClientId string

@description('Specify the Enterprise Application Object Id.')
param applicationClientPrincipalOid string

@description('Enable telemetry for deployed resources.')
param enableTelemetry bool = true

// Variables
var rg_unique_id = '${replace('main', '-', '')}${uniqueString(resourceGroup().id, 'main', location)}'

/*
 __   _______   _______ .__   __. .___________. __  .___________.____    ____
|  | |       \ |   ____||  \ |  | |           ||  | |           |\   \  /   /
|  | |  .--.  ||  |__   |   \|  | `---|  |----`|  | `---|  |----` \   \/   /
|  | |  |  |  ||   __|  |  . `  |     |  |     |  |     |  |       \_    _/
|  | |  '--'  ||  |____ |  |\   |     |  |     |  |     |  |         |  |
|__| |_______/ |_______||__| \__|     |__|     |__|     |__|         |__|
*/
module stampIdentity 'br/public:avm/res/managed-identity/user-assigned-identity:0.4.1' = {
  name: 'main-user-managed-identity'
  params: {
    name: rg_unique_id
    location: location
    enableTelemetry: enableTelemetry
    tags: {
      layer: 'Main Resources'
      id: rg_unique_id
      purpose: 'minimal-osdu'
    }
  }
}

/*
     ___      .__   __.      ___       __      ____    ____ .___________. __    ______     _______.
    /   \     |  \ |  |     /   \     |  |     \   \  /   / |           ||  |  /      |   /       |
   /  ^  \    |   \|  |    /  ^  \    |  |      \   \/   /  `---|  |----`|  | |  ,----'  |   (----`
  /  /_\  \   |  . `  |   /  /_\  \   |  |       \_    _/       |  |     |  | |  |        \   \
 /  _____  \  |  |\   |  /  _____  \  |  `----.    |  |         |  |     |  | |  `----.----)   |
/__/     \__\ |__| \__| /__/     \__\ |_______|    |__|         |__|     |__|  \______|_______/
*/
module logAnalytics 'br/public:avm/res/operational-insights/workspace:0.11.2' = {
  name: 'main-log-analytics'
  params: {
    name: rg_unique_id
    location: location
    enableTelemetry: enableTelemetry
    tags: {
      layer: 'Main Resources'
      id: rg_unique_id
      purpose: 'minimal-osdu'
    }
    skuName: 'PerGB2018'
  }
}

/*
 __  .__   __.      _______. __    _______  __    __  .___________.    _______.
|  | |  \ |  |     /       ||  |  /  _____||  |  |  | |           |   /       |
|  | |   \|  |    |   (----`|  | |  |  __  |  |__|  | `---|  |----`  |   (----`
|  | |  . `  |     \   \    |  | |  | |_ | |   __   |     |  |        \   \
|  | |  |\   | .----)   |   |  | |  |__| | |  |  |  |     |  |    .----)   |
|__| |__| \__| |_______/    |__|  \______| |__|  |__|     |__|    |_______/
*/
module insights 'br/public:avm/res/insights/component:0.6.0' = {
  name: 'main-insights'
  params: {
    name: '${replace('main', '-', '')}${uniqueString(resourceGroup().id, 'main', location)}'
    location: location
    enableTelemetry: enableTelemetry
    tags: {
      layer: 'Main Resources'
      id: rg_unique_id
      purpose: 'minimal-osdu'
    }
    kind: 'web'
    workspaceResourceId: logAnalytics.outputs.resourceId
    diagnosticSettings: [
      {
        metricCategories: [
          {
            category: 'AllMetrics'
          }
        ]
        name: 'customSetting'
        workspaceResourceId: logAnalytics.outputs.resourceId
      }
    ]
  }
}

/*
 __  ___  ___________    ____ ____    ____  ___      __    __   __      .___________. 
|  |/  / |   ____\   \  /   / \   \  /   / /   \    |  |  |  | |  |     |           |
|  '  /  |  |__   \   \/   /   \   \/   / /  ^  \   |  |  |  | |  |     `---|  |----`
|    <   |   __|   \_    _/     \      / /  /_\  \  |  |  |  | |  |         |  |     
|  .  \  |  |____    |  |        \    / /  _____  \ |  `--'  | |  `----.    |  |     
|__|\__\ |_______|   |__|         \__/ /__/     \__\ \______/  |_______|    |__|     
*/
module keyvault 'br/public:avm/res/key-vault/vault:0.12.1' = {
  name: 'main-keyvault'
  params: {
    name: rg_unique_id
    location: location
    enableTelemetry: enableTelemetry
    tags: {
      layer: 'Main Resources'
      id: rg_unique_id
      purpose: 'minimal-osdu'
    }
    
    sku: 'standard'
    enablePurgeProtection: false
    enableSoftDelete: false
    enableRbacAuthorization: true
    
    roleAssignments: [
      {
        principalId: applicationClientPrincipalOid
        roleDefinitionIdOrName: 'Key Vault Administrator'
        principalType: 'ServicePrincipal'
      }
      {
        principalId: stampIdentity.outputs.principalId
        roleDefinitionIdOrName: 'Key Vault Secrets User'
        principalType: 'ServicePrincipal'
      }
    ]

    diagnosticSettings: [
      {
        metricCategories: [
          {
            category: 'AllMetrics'
          }
        ]
        logCategoriesAndGroups: [
          {
            categoryGroup: 'allLogs'
          }
        ]
        name: 'customSetting'
        workspaceResourceId: logAnalytics.outputs.resourceId
      }
    ]
  }
}

/*
  ______   .___________.  ______   .______           ___       _______  _______ 
 /      |  |           | /  __  \  |   _  \         /   \     /  _____||   ____|
|  ,----'  `---|  |----`|  |  |  | |  |_)  |       /  ^  \   |  |  __  |  |__   
|  |           |  |     |  |  |  | |      /       /  /_\  \  |  | |_ | |   __|  
|  `----.      |  |     |  `--'  | |  |\  \----. /  _____  \ |  |__| | |  |____ 
 \______|      |__|      \______/  | _| `._____|/__/     \__\ \______| |_______|
*/
module storage 'br/public:avm/res/storage/storage-account:0.14.1' = {
  name: 'main-storage'
  params: {
    name: rg_unique_id
    location: location
    enableTelemetry: enableTelemetry
    tags: {
      layer: 'Main Resources'
      id: rg_unique_id
      purpose: 'minimal-osdu'
    }
    
    skuName: 'Standard_LRS'
    kind: 'StorageV2'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    
    blobServices: {
      containers: [
        {
          name: 'system'
          publicAccess: 'None'
        }
        {
          name: 'web-content'
          publicAccess: 'None'
        }
      ]
    }
    
    roleAssignments: [
      {
        principalId: stampIdentity.outputs.principalId
        roleDefinitionIdOrName: 'Storage Blob Data Contributor'
        principalType: 'ServicePrincipal'
      }
    ]

    diagnosticSettings: [
      {
        metricCategories: [
          {
            category: 'AllMetrics'
          }
        ]
        name: 'customSetting'
        workspaceResourceId: logAnalytics.outputs.resourceId
      }
    ]
  }
}

/*
 __   __   __   _______ .______      
|  | |  | |  | |   ____||   _  \     
|  | |  | |  | |  |__   |  |_)  |    
|  | |  | |  | |   __|  |   _  <     
|  | |  `--'  | |  |____ |  |_)  |    
|__| |______/  |_______||______/     
     _______.___________. ___   .___________. __    ______     
    /       |           |/   \  |           ||  |  /      |    
   |   (----`---|  |----`  ^  \ `---|  |----`|  | |  ,----'    
    \   \       |  |    /  /_\  \    |  |     |  | |  |         
.----)   |      |  |   /  _____  \   |  |     |  | |  `----.    
|_______/       |__|  /__/     \__\  |__|     |__|  \______|    
*/
module staticWebApp 'br/public:avm/res/web/static-site:0.6.2' = {
  name: 'main-static-web-app'
  params: {
    name: rg_unique_id
    location: location
    enableTelemetry: enableTelemetry
    tags: {
      layer: 'Main Resources'
      id: rg_unique_id
      purpose: 'minimal-osdu'
    }
    
    sku: 'Free'
    allowConfigFileUpdates: true
    
    roleAssignments: [
      {
        principalId: stampIdentity.outputs.principalId
        roleDefinitionIdOrName: 'Website Contributor'
        principalType: 'ServicePrincipal'
      }
    ]
  }
}

// Key Vault Secrets - Deploy only compile-time values
// Note: Commented out to deploy infrastructure first, then add secrets
// resource secretTenantId 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
//   name: '${rg_unique_id}/tenant-id'
//   properties: {
//     value: tenant().tenantId
//   }
//   dependsOn: [
//     keyvault
//   ]
// }

// resource secretSubscriptionId 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
//   name: '${rg_unique_id}/subscription-id'
//   properties: {
//     value: subscription().subscriptionId
//   }
//   dependsOn: [
//     keyvault
//   ]
// }

// resource secretClientId 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
//   name: '${rg_unique_id}/client-id'
//   properties: {
//     value: applicationClientId
//   }
//   dependsOn: [
//     keyvault
//   ]
// }

// Note: Runtime secrets (identity-id, storage info, insights key) will need to be added post-deployment

// Outputs
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_CLIENT_ID string = applicationClientId
output AZURE_STORAGE_ACCOUNT string = storage.outputs.name
output INSTRUMENTATION_KEY string = insights.outputs.instrumentationKey
output KEYVAULT_URI string = keyvault.outputs.uri
output STATIC_WEB_APP_URL string = staticWebApp.outputs.defaultHostname
// Note: Static Web App deployment token is available via CLI: az staticwebapp secrets list
output RESOURCE_GROUP_NAME string = resourceGroup().name
