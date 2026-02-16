// Bicep template for AI-KYC Demo Infrastructure
// Deploys Azure OpenAI and Azure AI Search resources

targetScope = 'resourceGroup'

@description('Location for all resources')
param location string = resourceGroup().location

@description('Base name for all resources')
param baseName string = 'aikyc'

@description('Environment name (dev, staging, prod)')
param environment string = 'dev'

@description('Azure OpenAI model deployment name')
param openAiModelName string = 'gpt-5-mini'

@description('Azure OpenAI model version')
param openAiModelVersion string = '2024-02-15-preview'

// Variables
var uniqueSuffix = uniqueString(resourceGroup().id)
var openAiName = '${baseName}-openai-${uniqueSuffix}'
var searchName = '${baseName}-search-${uniqueSuffix}'
var appServicePlanName = '${baseName}-plan-${environment}'
var appServiceName = '${baseName}-api-${environment}'
var logAnalyticsName = '${baseName}-logs-${environment}'
var appInsightsName = '${baseName}-appi-${environment}'

// Azure OpenAI Account
resource openAi 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' = {
  name: openAiName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: openAiName
    publicNetworkAccess: 'Enabled'
  }
}

// Azure OpenAI Model Deployment
resource openAiDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-10-01-preview' = {
  parent: openAi
  name: openAiModelName
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: openAiModelName
      version: openAiModelVersion
    }
  }
}

// Azure AI Search
resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: searchName
  location: location
  sku: {
    name: 'basic'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
  }
}

// Log Analytics Workspace (for Application Insights)
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

// Application Insights (for agent tracing and monitoring)
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// App Service Plan (optional - for hosting the API)
resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: appServicePlanName
  location: location
  kind: 'linux'
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true
  }
}

// App Service (optional - for hosting the API)
resource appService 'Microsoft.Web/sites@2023-01-01' = {
  name: appServiceName
  location: location
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appSettings: [
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: openAi.properties.endpoint
        }
        {
          name: 'AZURE_OPENAI_DEPLOYMENT_NAME'
          value: openAiModelName
        }
        {
          name: 'AZURE_SEARCH_ENDPOINT'
          value: 'https://${search.name}.search.windows.net'
        }
        {
          name: 'AZURE_SEARCH_INDEX_NAME'
          value: 'kyc-documents'
        }
        {
          name: 'APP_ENV'
          value: environment
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
      ]
    }
  }
}

// Outputs
output openAiEndpoint string = openAi.properties.endpoint
output openAiName string = openAi.name
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output searchName string = search.name
output appServiceUrl string = 'https://${appService.properties.defaultHostName}'
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey
output logAnalyticsWorkspaceId string = logAnalytics.properties.customerId
