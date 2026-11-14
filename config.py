import os

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

_client = None


def _get_client():
    global _client
    if _client is None:
        vault_url = os.environ["KEY_VAULT_URL"]
        _client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
    return _client


def get_secret(name):
    """Fetch a secret value.

    Checks for a same-named app setting override first (env var, uppercased
    with dashes as underscores) before hitting Key Vault. This lets the app
    run without the Function App's managed identity having Key Vault RBAC
    access yet - remove the override app setting once that access is granted
    to go back to pulling the live value straight from Key Vault.
    """
    override = os.environ.get(name.upper().replace("-", "_"))
    if override:
        return override
    return _get_client().get_secret(name).value
