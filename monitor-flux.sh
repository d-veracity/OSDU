#!/bin/bash

# OSDU Deployment Monitoring Script
echo "==================================================="
echo "OSDU Deployment Monitor"
echo "==================================================="

# Check if AKS cluster is accessible
echo "Checking AKS cluster status..."
AKS_STATUS=$(az aks show -n "clusterbladeh2zpmcamr5hgo" -g "rg-open_footprint-eastus2" --query "provisioningState" -o tsv 2>/dev/null)
echo "AKS Status: $AKS_STATUS"

if [ "$AKS_STATUS" = "Succeeded" ]; then
    echo -e "\n📊 Checking Flux Configuration..."
    
    # Check Flux compliance state
    FLUX_STATE=$(az k8s-configuration flux show -t managedClusters -g "rg-open_footprint-eastus2" --cluster-name "clusterbladeh2zpmcamr5hgo" --name flux-system --query 'complianceState' -o tsv 2>/dev/null)
    
    if [ ! -z "$FLUX_STATE" ]; then
        echo "Flux Compliance State: $FLUX_STATE"
        
        if [ "$FLUX_STATE" = "Compliant" ]; then
            echo "✅ SUCCESS: Software installation is compliant!"
            echo "🔄 Checking for auth endpoint..."
            
            # Try to get ingress external URL
            INGRESS_URL=$(azd env get-values 2>/dev/null | grep INGRESS_EXTERNAL | cut -d'=' -f2 | tr -d '"')
            if [ ! -z "$INGRESS_URL" ]; then
                echo "🔑 Auth URL: $INGRESS_URL"
                echo ""
                echo "Next steps:"
                echo "1. Visit: $INGRESS_URL"
                echo "2. Login and get AUTH_CODE"
                echo "3. Run: azd env set AUTH_CODE \"your_code\""
                echo "4. Run: azd hooks run settings"
            fi
        elif [ "$FLUX_STATE" = "Non-Compliant" ]; then
            echo "⚠️ Still Non-Compliant. This might take a few more minutes..."
        else
            echo "🔄 Flux State: $FLUX_STATE (in progress)"
        fi
    else
        echo "🔄 Flux configuration not yet available (still deploying)"
    fi
else
    echo "🔄 AKS cluster not ready yet (Status: $AKS_STATUS)"
fi

echo -e "\n==================================================="
echo "Run this script again in a few minutes to check progress"
echo "==================================================="
