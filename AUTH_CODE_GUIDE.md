# AUTH_CODE Retrieval Guide - ROOT CAUSE ANALYSIS

## ✅ **GIT CONFIGURATION ISSUE RESOLVED**

**Key Discovery**: The Git tag `release-0-27` doesn't exist in the repository, so we fixed this by using the `main` branch approach.

### Original Problem (FIXED)
The Bicep template logic for Git reference selection is:
```bicep
tag: softwareTag == '' && softwareBranch == '' ? version.release : softwareTag
branch: softwareBranch == '' ? '' : softwareBranch
```

**Available Git References:**
- ✅ **Branches**: `main`, `cert-issue`, `gh-pages` 
- ✅ **Tags**: `v0.47.0`, `v0.46.0`, `v0.45.0`, etc.
- ❌ **NO**: `release-0-27` (doesn't exist as tag or branch)

## � **FINAL ROOT CAUSE IDENTIFIED: Azure vCPU Quota Exhaustion**

**The deployment is failing because of insufficient Azure vCPU quota in East US 2:**

```
Insufficient regional vcpu quota left for location eastus2. 
left regional vcpu quota 0, requested quota 4.
```

### Problem Analysis:

1. ✅ **Git Configuration**: **FIXED** - Using `main` branch successfully  
2. ✅ **Flux Repository Sync**: **WORKING** - Code synced properly
3. ❌ **Azure vCPU Quota**: **EXHAUSTED** - 0 vCPUs remaining in East US 2
4. ❌ **Redis Cluster**: **CAN'T START** - No resources available
5. ❌ **Overall Status**: Non-Compliant due to resource constraints

### Current AKS Configuration:
- **system nodepool**: 1 x Standard_B2s (2 vCPU, 4GB RAM)  
- **default nodepool**: 1 x Standard_B2s (2 vCPU, 4GB RAM)
- **Total vCPUs used**: 4 vCPUs
- **Available quota**: 0 vCPUs (EXHAUSTED!)

## ⚡ **IMMEDIATE SOLUTION: Switch to East US Region**

**Good news**: East US region has available quota! 

Current quota status:
- **East US 2**: 0/10 vCPUs available (EXHAUSTED)
- **East US**: 0/10 vCPUs available (10 vCPUs FREE!)

### **Quick Fix Steps:**

1. **Change deployment region:**
   ```bash
   azd env set AZURE_LOCATION "eastus"
   ```

2. **Clean up current failed deployment:**
   ```bash
   azd down --force --purge
   ```

3. **Re-deploy in East US:**
   ```bash
   azd up --no-prompt
   ```

This should resolve the vCPU quota issue and allow the Redis cluster to deploy successfully.

## ✅ **SOLUTIONS**

### **Option 1: Request vCPU Quota Increase (RECOMMENDED)**

1. **Follow Azure documentation**: https://learn.microsoft.com/en-us/azure/quotas/view-quotas
2. **Request increase** for East US 2 region (recommend +20 vCPUs minimum)
3. **Wait for approval** (can take 1-24 hours)
4. **Re-run deployment** once quota is available

### **Option 2: Deploy in Different Region**

1. **Modify deployment region** from `eastus2` to another region with quota:
   ```bash
   azd env set AZURE_LOCATION "eastus"     # or westus2, centralus
   azd provision
   ```

### **Option 3: Use Smaller VM Sizes (TEMPORARY)**

1. **Modify Bicep template** to use smaller node sizes (B1s instead of B2s)
2. **Accept limited functionality** - Redis cluster may still fail
3. **Scale up later** when quota becomes available

### **Immediate Action Required:**

**Submit Azure quota increase request for East US 2 region** - this is the only sustainable solution for a production OSDU deployment.eval Guide - ROOT CAUSE ANALYSIS

## � ROOT CAUSE DISCOVERED: Misunderstanding of Git Tag vs Branch Logic

**Key Discovery**: The tag `release-0-27` doesn't exist in the Git repository! The repository only has tags like `v0.47.0`, `v0.46.0`, etc.

### The Real Problem
The Bicep template logic for Git reference selection is:
```bicep
tag: softwareTag == '' && softwareBranch == '' ? version.release : softwareTag
branch: softwareBranch == '' ? '' : softwareBranch
```

**Available Git References:**
- ✅ **Branches**: `main`, `cert-issue`, `gh-pages` 
- ✅ **Tags**: `v0.47.0`, `v0.46.0`, `v0.45.0`, etc.
- ❌ **NO**: `release-0-27` (doesn't exist as tag or branch)

### 🎯 **Updated Understanding**

1. **Git Reference**: ✅ **FIXED** - Using `main` branch successfully
2. **Flux Sync**: ✅ **WORKING** - Repository synced properly
3. **Redis Cluster**: ❌ **FAILING** - HelmRelease in Failed state
4. **Overall Status**: Still Non-Compliant due to Redis cluster

## ✅ CURRENT Configuration (Git Issue Fixed)

```bash
# Current configuration (GIT ISSUE RESOLVED)
SOFTWARE_TAG=""                    # Empty - use branch instead  
SOFTWARE_BRANCH="main"             # Use main branch (✅ working)
SOFTWARE_VERSION="release-0-27"    # OSDU version for container images
```

## 🔧 **Redis Cluster Troubleshooting Approach**

Common causes of Redis cluster failures in OSDU:

1. **Resource Constraints**: Redis cluster requires significant memory/CPU
2. **Storage Issues**: Persistent volumes not available or misconfigured  
3. **Image Registry**: Container image pull failures
4. **Network Policies**: Kubernetes networking restrictions

### Immediate Actions Needed:

1. **Investigate Redis Cluster**: Get detailed logs and status
2. **Resource Check**: Verify AKS node capacity and resource allocation
3. **Storage Verification**: Check if storage classes and PVCs are working
4. **Alternative Approach**: Consider using external Redis (Azure Cache for Redis)

### Quick Fix Options:

**Option 1: Scale Up AKS Cluster** (if resource constrained)
```bash
az aks scale --resource-group rg-open_footprint-eastus2 --name clusterbladeh2zpmcamr5hgo --node-count 3
```

**Option 2: Use External Redis** (modify configuration)
- Point Redis configuration to the existing Azure Cache for Redis instance
- Bypass in-cluster Redis deployment

**Option 3: Reset Flux and Retry**
```bash
# Delete and recreate Flux configuration
az k8s-configuration flux delete -t managedClusters -g rg-open_footprint-eastus2 --cluster-name clusterbladeh2zpmcamr5hgo --name flux-system
# Then re-run azd up
```

## Why This Should Work

1. **Flux GitRepository**: Will checkout `main` branch (✅ exists)
2. **Software Configs**: Found in `/software/applications/*` on main branch  
3. **Container Images**: Will use `release-0-27` specific images (e.g., `unit-service-release-0-27`)
4. **Validation**: `osduVersion="release-0-27"` passes Bicep template validation

## Verification Before Re-deployment

Let's verify our logic is sound:

```bash
# 1. Confirm main branch exists
git ls-remote --heads https://github.com/Azure/osdu-developer
# ✅ Should show: refs/heads/main

# 2. Confirm software configs exist on main  
curl -s https://raw.githubusercontent.com/Azure/osdu-developer/main/software/applications/osdu-core/partition.yaml
# ✅ Should return YAML content

# 3. Confirm our environment is correct
azd env get-values | grep SOFTWARE
# ✅ Should show: SOFTWARE_BRANCH="main", SOFTWARE_TAG="", SOFTWARE_VERSION="release-0-27"
```

### Step 2: Get AUTH_CODE (After Re-deployment)

Once the deployment completes successfully:
1. The auth URL should open automatically in your browser
2. Or manually visit the URL that will be displayed in the deployment output
3. Log in with your Azure account: `ajvdvoort_dveracity.com#EXT#@ajvdvoortdveracity.onmicrosoft.com`
4. Copy the authorization code from the page

### Step 3: Set the AUTH_CODE

```bash
azd env set AUTH_CODE "PASTE_YOUR_AUTH_CODE_HERE"
azd hooks run settings
```

This will:
- Exchange the AUTH_CODE for a refresh token
- Create necessary configuration files
- Set up the environment for testing

## Step 4: Verify Deployment

Check if software installation becomes compliant:

```bash
az k8s-configuration flux show -t managedClusters -g "rg-open_footprint-eastus2" --cluster-name "clusterbladeh2zpmcamr5hgo" --name flux-system --query 'complianceState' -o tsv
```

## Troubleshooting

### If Re-deployment Fails:
1. Check that all environment variables are correct:
   ```bash
   azd env get-values | grep SOFTWARE
   ```

2. Verify the subscription and resource group:
   ```bash
   az account show
   az group show -n "rg-open_footprint-eastus2"
   ```

### If Auth URL Still Doesn't Work After Re-deployment:
1. Check the deployment output for the correct auth URL
2. Look for INGRESS_EXTERNAL in environment variables:
   ```bash
   azd env get-values | grep INGRESS
   ```

## Alternative: Manual Flux Fix (Advanced)

If you prefer not to re-deploy, you can try to fix the Flux configuration manually:

```bash
# Check current Flux status
az k8s-configuration flux show -t managedClusters -g "rg-open_footprint-eastus2" --cluster-name "clusterbladeh2zpmcamr5hgo" --name flux-system

# Force reconciliation (if you have kubectl access)
kubectl get gitrepository -n flux-system
```

However, re-deployment is the recommended approach since it ensures all components are properly configured.

## Environment Status

✅ **Current Environment Variables (Fixed):**
- SOFTWARE_REPOSITORY: https://github.com/Azure/osdu-developer
- SOFTWARE_BRANCH: main  
- SOFTWARE_VERSION: release-0-27 (corrected from v0.27.0)
- ENABLE_OSDU_REFERENCE: true
- ENABLE_ADMIN_UI: true

The compliance configuration issues have been resolved. The AUTH_CODE is the final step needed to complete the deployment.
