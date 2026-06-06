#!/bin/bash

echo "🚀 OSDU Deployment Monitor - East US"
echo "======================================="
echo "Deployment started: $(date)"
echo ""

while true; do
    echo "⏰ Status check: $(date '+%H:%M:%S')"
    echo ""
    
    # Check resource group creation
    if az group show --name "rg-open_footprint-eastus" >/dev/null 2>&1; then
        echo "✅ Resource Group: Created"
        
        # Check AKS cluster if resource group exists
        if az aks show --resource-group "rg-open_footprint-eastus" --name "clusterbladeh2zpmcamr5hgo" >/dev/null 2>&1; then
            echo "✅ AKS Cluster: Created"
            
            # Check Flux configuration if AKS exists
            FLUX_STATUS=$(az k8s-configuration flux show -t managedClusters -g "rg-open_footprint-eastus" --cluster-name "clusterbladeh2zpmcamr5hgo" --name flux-system --query 'complianceState' -o tsv 2>/dev/null)
            if [ ! -z "$FLUX_STATUS" ]; then
                echo "🔄 Flux Status: $FLUX_STATUS"
            else
                echo "⏳ Flux: Not configured yet"
            fi
        else
            echo "⏳ AKS Cluster: Creating..."
        fi
    else
        echo "⏳ Resource Group: Creating..."
    fi
    
    echo ""
    echo "📊 East US vCPU Usage:"
    az vm list-usage --location eastus --query "[?name.value=='cores'].{Used:currentValue,Limit:limit}" -o table
    
    echo ""
    echo "Press Ctrl+C to stop monitoring"
    echo "================================="
    sleep 60
done
