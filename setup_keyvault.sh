#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="devteam-projectnour-rg"
LOCATION="centralus"
VAULT_NAME="viasmiles-emailapp-kv"   # must be globally unique across Azure, change if taken
FUNCTION_APP="iaSmiles-EmailApp"
MY_UPN="jvm@analyticsintellect.com"

echo "== 1. Creating Key Vault (RBAC permission model) =="
az keyvault create \
  --name "$VAULT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --enable-rbac-authorization true

echo "== 2. Storing the client secret =="
read -rsp "Paste the AAD client secret value (input hidden): " AAD_SECRET
echo
az keyvault secret set \
  --vault-name "$VAULT_NAME" \
  --name "aad-client-secret" \
  --value "$AAD_SECRET" \
  --output none
unset AAD_SECRET

VAULT_ID=$(az keyvault show --name "$VAULT_NAME" --query id -o tsv)

echo "== 3. Granting yourself access (for local development) =="
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee "$MY_UPN" \
  --scope "$VAULT_ID"

echo "== 4. Enabling managed identity on the Function App =="
PRINCIPAL_ID=$(az functionapp identity assign \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query principalId -o tsv)

echo "== 5. Granting the Function App's identity access =="
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee "$PRINCIPAL_ID" \
  --scope "$VAULT_ID"

echo "== 6. Pointing the deployed Function App at the vault =="
az functionapp config appsettings set \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --settings KEY_VAULT_URL="https://$VAULT_NAME.vault.azure.net/" \
  --output none

echo
echo "Done. Vault URL: https://$VAULT_NAME.vault.azure.net/"
echo "Now set the same KEY_VAULT_URL value in local.settings.json for local dev,"
echo "and run 'az login' locally before using insert_dummy_data.py or func start."
