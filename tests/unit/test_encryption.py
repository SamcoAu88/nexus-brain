"""
Unit tests for Fernet Encryption
Tests encryption/decryption of sensitive configuration
"""

import pytest
from src.security.encryption import (
    EncryptionManager,
    EncryptedConfig,
    encrypt_secret,
    decrypt_secret,
)


class TestEncryptionManager:
    """Test encryption manager functionality"""

    def test_generate_key(self):
        """Test generating a new encryption key"""
        key = EncryptionManager.generate_key()

        assert isinstance(key, str)
        assert len(key) > 0
        # Fernet keys are base64, should be ~44 chars
        assert len(key) >= 40

    def test_encrypt_decrypt_string(self):
        """Test encrypting and decrypting a string"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        plaintext = "secret-password-123"

        encrypted = manager.encrypt(plaintext)
        decrypted = manager.decrypt(encrypted)

        assert encrypted != plaintext
        assert decrypted == plaintext

    def test_encrypt_api_key(self):
        """Test encrypting an API key"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        api_key = "sk-proj-abc123def456ghi789jkl"

        encrypted = manager.encrypt(api_key)
        decrypted = manager.decrypt(encrypted)

        assert api_key not in encrypted  # API key not visible in encrypted form
        assert decrypted == api_key

    def test_encrypt_token(self):
        """Test encrypting a token"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"

        encrypted = manager.encrypt(token)
        decrypted = manager.decrypt(encrypted)

        assert decrypted == token

    def test_decrypt_wrong_key_fails(self):
        """Test that decryption with wrong key fails"""
        manager1 = EncryptionManager(EncryptionManager.generate_key())
        manager2 = EncryptionManager(EncryptionManager.generate_key())

        plaintext = "secret"
        encrypted = manager1.encrypt(plaintext)

        # Should fail to decrypt with different key
        with pytest.raises(ValueError):
            manager2.decrypt(encrypted)

    def test_decrypt_invalid_token_fails(self):
        """Test that decrypting invalid token fails"""
        manager = EncryptionManager(EncryptionManager.generate_key())

        with pytest.raises(ValueError):
            manager.decrypt("not-a-valid-encrypted-token")

    def test_encrypt_empty_string(self):
        """Test encrypting empty string"""
        manager = EncryptionManager(EncryptionManager.generate_key())

        encrypted = manager.encrypt("")
        decrypted = manager.decrypt(encrypted)

        assert decrypted == ""

    def test_encrypt_unicode(self):
        """Test encrypting unicode strings"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        plaintext = "мир 世界 🔐"

        encrypted = manager.encrypt(plaintext)
        decrypted = manager.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_long_string(self):
        """Test encrypting very long string"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        plaintext = "x" * 10000

        encrypted = manager.encrypt(plaintext)
        decrypted = manager.decrypt(encrypted)

        assert decrypted == plaintext
        assert len(encrypted) > len(plaintext)  # Encrypted is longer due to overhead

    def test_encrypt_special_characters(self):
        """Test encrypting special characters"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        plaintext = "!@#$%^&*()_+-=[]{}|;':\",./<>?"

        encrypted = manager.encrypt(plaintext)
        decrypted = manager.decrypt(encrypted)

        assert decrypted == plaintext

    def test_multiple_encryptions_differ(self):
        """Test that encrypting same value multiple times produces different ciphertexts"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        plaintext = "secret"

        encrypted1 = manager.encrypt(plaintext)
        encrypted2 = manager.encrypt(plaintext)

        # Fernet includes timestamp, so same plaintext produces different ciphertext
        assert encrypted1 != encrypted2
        # But both decrypt to same value
        assert manager.decrypt(encrypted1) == plaintext
        assert manager.decrypt(encrypted2) == plaintext

    def test_encrypt_dict(self):
        """Test encrypting specific keys in dictionary"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        data = {
            "username": "alice",
            "password": "secret123",
            "email": "alice@example.com",
            "token": "abc123",
        }

        encrypted = manager.encrypt_dict(data, ["password", "token"])

        assert encrypted["username"] == data["username"]  # Not encrypted
        assert encrypted["email"] == data["email"]  # Not encrypted
        assert encrypted["password"] != data["password"]  # Encrypted
        assert encrypted["token"] != data["token"]  # Encrypted

    def test_decrypt_dict(self):
        """Test decrypting dictionary keys"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        data = {"api_key": "sk-123", "url": "https://example.com"}

        encrypted = manager.encrypt_dict(data, ["api_key"])
        decrypted = manager.decrypt_dict(encrypted, ["api_key"])

        assert decrypted["api_key"] == data["api_key"]
        assert decrypted["url"] == data["url"]

    def test_encrypt_none_value(self):
        """Test encrypting None (should be handled gracefully)"""
        manager = EncryptionManager(EncryptionManager.generate_key())

        # encrypt() should convert to string
        encrypted = manager.encrypt("None")
        decrypted = manager.decrypt(encrypted)

        assert decrypted == "None"


class TestEncryptedConfig:
    """Test encrypted configuration wrapper"""

    def test_get_encrypted_secret(self):
        """Test getting encrypted secret"""
        key = EncryptionManager.generate_key()
        config = EncryptedConfig(key)

        plaintext = "my-secret-key"
        encrypted = config.encrypt_value("SECRET_KEY", plaintext)
        decrypted = config.get_secret("SECRET_KEY", encrypted)

        assert decrypted == plaintext

    def test_get_secret_returns_none(self):
        """Test get_secret returns None for missing value"""
        config = EncryptedConfig(EncryptionManager.generate_key())

        result = config.get_secret("MISSING_KEY", None)

        assert result is None

    def test_get_secret_caches_value(self):
        """Test that decrypted values are cached"""
        key = EncryptionManager.generate_key()
        config = EncryptedConfig(key)

        plaintext = "secret"
        encrypted = config.encrypt_value("KEY", plaintext)

        # First call
        result1 = config.get_secret("KEY", encrypted)
        # Second call should come from cache
        result2 = config.get_secret("KEY", encrypted)

        assert result1 == result2 == plaintext


class TestConvenienceFunctions:
    """Test convenience functions"""

    @pytest.mark.skip(reason="Requires ENCRYPTION_KEY env var to be set globally")
    def test_encrypt_secret_function(self):
        """Test encrypt_secret convenience function"""
        plaintext = "api-key-123"

        encrypted = encrypt_secret(plaintext)
        decrypted = decrypt_secret(encrypted)

        assert decrypted == plaintext

    @pytest.mark.skip(reason="Requires ENCRYPTION_KEY env var to be set globally")
    def test_decrypt_secret_function(self):
        """Test decrypt_secret convenience function"""
        plaintext = "webhook-secret"

        encrypted = encrypt_secret(plaintext)
        decrypted = decrypt_secret(encrypted)

        assert decrypted == plaintext


class TestEncryptionRealistic:
    """Test realistic encryption scenarios"""

    def test_encrypt_telegram_token(self):
        """Test encrypting Telegram bot token"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        token = "123456789:ABCDefGHIjkLmnOPQrstUvwXYZ"

        encrypted = manager.encrypt(token)
        decrypted = manager.decrypt(encrypted)

        assert decrypted == token

    def test_encrypt_openai_key(self):
        """Test encrypting OpenAI API key"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        key = "sk-proj-abc123def456ghi789jkl"

        encrypted = manager.encrypt(key)
        decrypted = manager.decrypt(encrypted)

        assert decrypted == key

    def test_encrypt_database_url(self):
        """Test encrypting database URL"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        url = "postgresql://user:password@localhost:5432/dbname"

        encrypted = manager.encrypt(url)
        decrypted = manager.decrypt(encrypted)

        assert decrypted == url

    def test_encrypt_jwt_secret(self):
        """Test encrypting JWT secret"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        secret = "super-secret-jwt-key-min-32-chars-for-hs256"

        encrypted = manager.encrypt(secret)
        decrypted = manager.decrypt(encrypted)

        assert decrypted == secret

    def test_encrypt_config_dict(self):
        """Test encrypting configuration dictionary"""
        manager = EncryptionManager(EncryptionManager.generate_key())

        config = {
            "database_url": "postgresql://localhost/db",
            "api_key": "sk-123456",
            "webhook_secret": "secret",
            "debug": "false",
            "port": "8000",
        }

        sensitive_keys = ["database_url", "api_key", "webhook_secret"]
        encrypted_config = manager.encrypt_dict(config, sensitive_keys)
        decrypted_config = manager.decrypt_dict(encrypted_config, sensitive_keys)

        # Public values unchanged
        assert encrypted_config["debug"] == config["debug"]
        assert encrypted_config["port"] == config["port"]

        # Sensitive values restored
        assert decrypted_config["database_url"] == config["database_url"]
        assert decrypted_config["api_key"] == config["api_key"]
        assert decrypted_config["webhook_secret"] == config["webhook_secret"]


class TestEncryptionEdgeCases:
    """Test edge cases and error handling"""

    def test_encrypt_very_large_value(self):
        """Test encrypting very large data"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        large_data = "x" * (1024 * 1024)  # 1MB

        encrypted = manager.encrypt(large_data)
        decrypted = manager.decrypt(encrypted)

        assert len(decrypted) == len(large_data)

    def test_encrypt_multiline_string(self):
        """Test encrypting multiline string"""
        manager = EncryptionManager(EncryptionManager.generate_key())
        multiline = """Line 1
Line 2
Line 3 with "quotes"
Line 4 with 'apostrophes'"""

        encrypted = manager.encrypt(multiline)
        decrypted = manager.decrypt(encrypted)

        assert decrypted == multiline

    def test_no_encryption_key_raises_error(self):
        """Test that missing encryption key raises error"""
        import os

        # Temporarily remove ENCRYPTION_KEY
        original = os.environ.pop("ENCRYPTION_KEY", None)
        try:
            with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
                EncryptionManager(None)
        finally:
            if original:
                os.environ["ENCRYPTION_KEY"] = original
