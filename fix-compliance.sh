#!/bin/bash

# OSDU Compliance Resolution Script
# This script fixes the non-compliant software configuration

echo "🔧 OSDU Compliance Resolution Script"
echo "====================================="

# Check if we're in the right directory
if [ ! -f ".azure/open_footprint/.env" ]; then
    echo "❌ Error: Must be run from the OSDU project root directory"
    exit 1
fi

echo "📋 Current Configuration Issues:"
echo "  - SOFTWARE_REPOSITORY: Not set"
echo "  - SOFTWARE_BRANCH: Not set" 
echo "  - SOFTWARE_TAG: Not set"
echo "  - SOFTWARE_VERSION: Not set"
echo "  - ENABLE_OSDU_REFERENCE: false (should be true for compliance)"
echo "  - ENABLE_ADMIN_UI: false (recommended for monitoring)"
echo ""

echo "🔄 Applying Compliance Fixes..."

# Backup current environment file
cp .azure/open_footprint/.env .azure/open_footprint/.env.backup.$(date +%Y%m%d_%H%M%S)
echo "✅ Created backup of current .env file"

# Update the environment file with compliant settings
echo "📝 Updating environment configuration..."

# Set the official OSDU repository
azd env set SOFTWARE_REPOSITORY "https://github.com/Azure/osdu-developer"
echo "✅ Set SOFTWARE_REPOSITORY to official OSDU repository"

# Set a stable branch (use main instead of master)
azd env set SOFTWARE_BRANCH "main"
echo "✅ Set SOFTWARE_BRANCH to 'main'"

# Set a stable version tag (latest stable release)
azd env set SOFTWARE_VERSION "release-0-27"
echo "✅ Set SOFTWARE_VERSION to stable release"

# Enable OSDU Reference services for compliance
azd env set ENABLE_OSDU_REFERENCE "true"
echo "✅ Enabled OSDU Reference services"

# Enable Admin UI for better monitoring and compliance tracking
azd env set ENABLE_ADMIN_UI "true"
echo "✅ Enabled Admin UI"

echo ""
echo "✅ Compliance configuration updated successfully!"
echo ""
echo "📋 Updated Configuration:"
echo "  - SOFTWARE_REPOSITORY: https://github.com/Azure/osdu-developer"
echo "  - SOFTWARE_BRANCH: main"
echo "  - SOFTWARE_VERSION: release-0-27"
echo "  - ENABLE_OSDU_REFERENCE: true"
echo "  - ENABLE_ADMIN_UI: true"
echo ""
echo "🚀 Next Steps:"
echo "1. Review the updated configuration with: azd env get-values"
echo "2. Redeploy the application with: azd up"
echo "3. Verify compliance after deployment"
echo ""
echo "⚠️  Note: Redeployment will take 15-30 minutes to complete"
