# Import dependencies
import hvac


#____________________________________
def write_secret_to_vault(vault_url, wrapping_token, secret_path, key, value, secret_root='secrets'):
    """Writes the passhprase to HashiCorp Vault.

    :param vault_url: URL to Vault server
    :type vault_url: str
    :param wrapping_token: Wrapping token used to write the passphrase to Vault.
    :type wrapping_token: str
    :param secret_path: Vault path in which the passphrase is stored.
    :type secret_path: str
    :param key: Vault key associated to the passphrase
    :type key: str
    :param value: Passphrase to be stored in Vault
    :type value: str
    """
    # Instantiate the hvac.Client class
    vault_client = hvac.Client(vault_url, verify=False)

    # Login directly with the wrapped token
    vault_client.auth_cubbyhole(wrapping_token)
    assert vault_client.is_authenticated()

    # Post secret
    secret={key:value}
    vault_client.secrets.kv.v2.create_or_update_secret(path=secret_path, secret=secret, mount_point=secret_root, cas=0)

    # Logout and revoke current token
    vault_client.logout(revoke_token=True)


#____________________________________
def read_secret(vault_url, wrapping_token, secret_root, secret_path, secret_key):
    """Read the passphrase from HashiCorp Vault.

    :param vault_url: URL to Vault server
    :type vault_url: str
    :param wrapping_token: Wrapping token used to write the passphrase to Vault.
    :type wrapping_token: str
    :param secret_root: Vault root in which secrets are stored, e.g. 'secrets'
    :type secret_root: str
    :param secret_path: Vault path in which the passphrase is stored.
    :type secret_path: str
    :param secret_key: Vault key associated to the passphrase.
    :type user_key: str
    :return: Passphrase retrieved from Vault.
    :rtype: str
    """
    
    # Instantiate the hvac.Client class
    vault_client = hvac.Client(vault_url, verify=False)

    # Login directly with the wrapped token
    vault_client.auth_cubbyhole(wrapping_token)
    assert vault_client.is_authenticated()

    # Read secret
    read_response = vault_client.secrets.kv.read_secret_version(path=secret_path, mount_point=secret_root)
    secret = read_response['data']['data'][secret_key]

    # Logout and revoke current token
    vault_client.logout(revoke_token=True)

    return secret
