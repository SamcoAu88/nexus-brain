"""
Fernet Encryption for Sensitive Data
Encrypts API keys, tokens, and URLs at rest
"""

import os
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64
import logging

logger = logging.getLogger(__name__)


class EncryptionManager:
    """Manage encryption and decryption of sensitive data"""

    def __init__(self, master_key: Optional[str] = None, salt: Optional[bytes] = None):
        """
        Initialize encryption manager.

        Args:
            master_key: Fernet key (base64-encoded) or raw secret for key derivation
            salt: Salt for key derivation (8+ bytes). Defaults to fixed salt for consistency.
        """
        self.salt = salt or b"nexus-brain-salt"  # Fixed salt for deterministic key derivation

        if master_key is None:
            # Try to get from environment
            master_key = os.getenv("ENCRYPTION_KEY")
            if not master_key:
                raise ValueError(
                    "ENCRYPTION_KEY environment variable not set. "
                    "Generate with: python -c \"from cryptography.fernet import Fernet; "
                    "print(Fernet.generate_key().decode())\""
                )

        # Derive key if it's not already a valid Fernet key
        try:
            # Try to use directly as Fernet key
            self.cipher = Fernet(master_key.encode() if isinstance(master_key, str) else master_key)
        except (ValueError, TypeError):
            # Derive key from master key string
            self.cipher = self._derive_key(master_key)

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key"""
        return Fernet.generate_key().decode()

    def _derive_key(self, secret: str) -> Fernet:
        """
        Derive a Fernet key from a master secret using PBKDF2.

        Args:
            secret: Master secret string

        Returns:
            Fernet cipher instance
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
            backend=default_backend(),
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
        return Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a string.

        Args:
            plaintext: String to encrypt

        Returns:
            Encrypted string (base64-encoded)
        """
        if not isinstance(plaintext, str):
            plaintext = str(plaintext)

        try:
            encrypted = self.cipher.encrypt(plaintext.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a string.

        Args:
            ciphertext: Encrypted string (base64-encoded)

        Returns:
            Decrypted plaintext

        Raises:
            ValueError: If decryption fails (invalid token or wrong key)
        """
        if not isinstance(ciphertext, str):
            ciphertext = str(ciphertext)

        try:
            decrypted = self.cipher.decrypt(ciphertext.encode())
            return decrypted.decode()
        except InvalidToken:
            logger.error("Decryption failed: Invalid token or wrong key")
            raise ValueError("Failed to decrypt: Invalid token or wrong encryption key")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise

    def encrypt_dict(self, data: dict, keys_to_encrypt: list[str]) -> dict:
        """
        Encrypt specific keys in a dictionary.

        Args:
            data: Dictionary to encrypt
            keys_to_encrypt: List of keys to encrypt

        Returns:
            Dictionary with encrypted values for specified keys
        """
        encrypted = data.copy()
        for key in keys_to_encrypt:
            if key in encrypted and encrypted[key]:
                encrypted[key] = self.encrypt(str(encrypted[key]))
        return encrypted

    def decrypt_dict(self, data: dict, keys_to_decrypt: list[str]) -> dict:
        """
        Decrypt specific keys in a dictionary.

        Args:
            data: Dictionary to decrypt
            keys_to_decrypt: List of keys to decrypt

        Returns:
            Dictionary with decrypted values for specified keys

        Raises:
            ValueError: If any decryption fails
        """
        decrypted = data.copy()
        for key in keys_to_decrypt:
            if key in decrypted and decrypted[key]:
                decrypted[key] = self.decrypt(decrypted[key])
        return decrypted


class EncryptedConfig:
    """Wrapper for encrypted configuration values"""

    def __init__(self, encryption_key: Optional[str] = None):
        """Initialize encrypted config wrapper"""
        self.manager = EncryptionManager(encryption_key)
        self._decrypted_cache: dict = {}

    def encrypt_value(self, key: str, value: str) -> str:
        """Encrypt a configuration value"""
        encrypted = self.manager.encrypt(value)
        logger.debug(f"Encrypted config key: {key}")
        return encrypted

    def decrypt_value(self, key: str, encrypted_value: str) -> str:
        """Decrypt a configuration value with caching"""
        if key in self._decrypted_cache:
            return self._decrypted_cache[key]

        decrypted = self.manager.decrypt(encrypted_value)
        self._decrypted_cache[key] = decrypted
        return decrypted

    def get_secret(self, key: str, encrypted_value: Optional[str]) -> Optional[str]:
        """
        Get a secret configuration value.

        Args:
            key: Configuration key name
            encrypted_value: Encrypted value from config

        Returns:
            Decrypted value or None if not set
        """
        if encrypted_value is None:
            return None

        try:
            return self.decrypt_value(key, encrypted_value)
        except ValueError:
            logger.error(f"Failed to decrypt {key}: Invalid key or corrupted data")
            return None


# Global instance
_encryption_manager: Optional[EncryptionManager] = None


def get_encryption_manager(key: Optional[str] = None) -> EncryptionManager:
    """Get or create global encryption manager"""
    global _encryption_manager
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager(key)
    return _encryption_manager


def encrypt_secret(value: str) -> str:
    """Encrypt a secret - convenience function"""
    return get_encryption_manager().encrypt(value)


def decrypt_secret(value: str) -> str:
    """Decrypt a secret - convenience function"""
    return get_encryption_manager().decrypt(value)
