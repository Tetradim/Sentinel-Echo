"""
C4: Credential encryption at rest.

Broker API keys, secrets, tokens and passwords are encrypted before being
written to the database and decrypted on read.  The encryption key is derived
from an environment variable (CREDENTIAL_KEY) so it never lives in the DB.

Key management:
  - Set CREDENTIAL_KEY to a random 32-byte hex string in your .env file.
  - If CREDENTIAL_KEY is missing or malformed, credentials may still be stored
    as-is for backward-compatible setup flows, but live readiness and live broker
    order submission must reject that configuration.
  - Use `python -c "import secrets; print(secrets.token_hex(32))"` to generate one.

The encrypted value is stored as a plain string prefixed with "enc:" so we can
detect and skip re-encryption on reads, and skip decryption on plaintext values
that were saved before encryption was enabled.
"""

import os
import base64
import logging
from typing import Any, Dict, Mapping

logger = logging.getLogger(__name__)

SENSITIVE_FIELDS = {
    'api_key', 'api_secret', 'refresh_token', 'access_token',
    'trade_token', 'password', 'mfa_code', 'ts_client_secret',
    'tos_refresh_token', 'ws_password',
}
MASKED_SECRET = '********'

_PREFIX = 'enc:'
_fernet = None


def credential_key_status(env: Mapping[str, str] | None = None) -> Dict[str, Any]:
    """Return non-secret CREDENTIAL_KEY readiness metadata."""
    source = env if env is not None else os.environ
    raw_key = str(source.get('CREDENTIAL_KEY', '') or '').strip()
    if not raw_key:
        return {
            'configured': False,
            'valid': False,
            'reason': 'missing',
            'summary': 'CREDENTIAL_KEY is required so broker secrets are encrypted.',
        }
    if len(raw_key) != 64:
        return {
            'configured': True,
            'valid': False,
            'reason': 'invalid_length',
            'summary': 'CREDENTIAL_KEY must be a 32-byte hex string.',
        }
    try:
        bytes.fromhex(raw_key)
    except ValueError:
        return {
            'configured': True,
            'valid': False,
            'reason': 'invalid_hex',
            'summary': 'CREDENTIAL_KEY must be a 32-byte hex string.',
        }
    return {
        'configured': True,
        'valid': True,
        'reason': '',
        'summary': 'CREDENTIAL_KEY is configured for broker credential encryption.',
    }


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    raw_key = os.environ.get('CREDENTIAL_KEY', '')
    key_status = credential_key_status()
    if not key_status['configured']:
        logger.warning(
            'CREDENTIAL_KEY env var not set -- broker credentials will be stored in plaintext. '
            'Set CREDENTIAL_KEY to a 32-byte hex string for encryption at rest.'
        )
        return None
    if not key_status['valid']:
        logger.error('CREDENTIAL_KEY is invalid -- broker credentials will not be encrypted until it is a 32-byte hex string.')
        return None
    try:
        from cryptography.fernet import Fernet
        # Derive a valid Fernet key from the configured 32-byte hex string.
        key_bytes = bytes.fromhex(raw_key)
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        _fernet = Fernet(fernet_key)
        return _fernet
    except Exception as e:
        logger.error('Failed to initialise credential encryption: %s', e)
        return None


def encrypt_value(plaintext: str) -> str:
    """Encrypt a credential value. Returns 'enc:<base64>' or plaintext if no key."""
    if not plaintext:
        return plaintext
    fernet = _get_fernet()
    if fernet is None:
        return plaintext
    token = fernet.encrypt(plaintext.encode()).decode()
    return f'{_PREFIX}{token}'


def decrypt_value(value: str) -> str:
    """Decrypt a credential value. Returns plaintext whether or not it was encrypted."""
    if not value or not value.startswith(_PREFIX):
        return value
    fernet = _get_fernet()
    if fernet is None:
        logger.error('CREDENTIAL_KEY not set but encrypted credential found in DB -- cannot decrypt')
        return ''
    try:
        ciphertext = value[len(_PREFIX):]
        return fernet.decrypt(ciphertext.encode()).decode()
    except Exception as e:
        logger.error('Failed to decrypt credential: %s', e)
        return ''


def encrypt_broker_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a broker config dict with sensitive fields encrypted."""
    result = dict(config)
    for field in SENSITIVE_FIELDS:
        if field in result and isinstance(result[field], str) and result[field]:
            result[field] = encrypt_value(result[field])
    return result


def decrypt_broker_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a broker config dict with sensitive fields decrypted."""
    result = dict(config)
    for field in SENSITIVE_FIELDS:
        if field in result and isinstance(result[field], str):
            result[field] = decrypt_value(result[field])
    return result


def encrypt_broker_configs(configs: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Encrypt all broker configs in the broker_configs dict."""
    return {broker_id: encrypt_broker_config(cfg) for broker_id, cfg in configs.items()}


def decrypt_broker_configs(configs: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Decrypt all broker configs in the broker_configs dict."""
    return {broker_id: decrypt_broker_config(cfg) for broker_id, cfg in configs.items()}


def is_masked_secret(value: Any) -> bool:
    """Return True when a frontend payload is preserving an already configured secret."""
    return isinstance(value, str) and value.strip() == MASKED_SECRET


def mask_broker_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a broker config safe for API responses without plaintext credentials."""
    result = dict(config)
    configured_fields: Dict[str, bool] = {}
    for field in SENSITIVE_FIELDS:
        if field not in result:
            continue
        configured = bool(result[field])
        configured_fields[field] = configured
        result[field] = MASKED_SECRET if configured else ''
    if configured_fields:
        result['configured_fields'] = configured_fields
    return result


def mask_broker_configs(configs: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Mask all broker credentials for API responses."""
    return {broker_id: mask_broker_config(cfg) for broker_id, cfg in configs.items()}
