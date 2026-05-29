from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from core.two_factor import TwoFactorAuth


def _mock_pyotp():
    """Erzeugt ein mock-pyotp-Modul."""
    mod = MagicMock()
    mod.random_base32.return_value = "GENERATEDSECRET123"
    mock_totp = MagicMock()
    mock_totp.verify.return_value = True
    mock_totp.provisioning_uri.return_value = (
        "otpauth://totp/AI4Trade%20Bot:admin?secret=SECRET&issuer=AI4Trade%20Bot"
    )
    mod.TOTP.return_value = mock_totp
    return mod


class TestTwoFactorAuth:
    """Tests fuer TOTP-basierte 2FA."""

    def test_verify_no_secret_returns_true(self):
        tfa = TwoFactorAuth(totp_secret="")
        assert tfa.verify("123456") is True

    def test_verify_valid_code(self):
        mock_pyotp = _mock_pyotp()
        mock_pyotp.TOTP.return_value.verify.return_value = True

        with patch.dict(sys.modules, {"pyotp": mock_pyotp}):
            tfa = TwoFactorAuth(totp_secret="JBSWY3DPEHPK3PXP")
            result = tfa.verify("123456")

        assert result is True
        mock_pyotp.TOTP.assert_called_once_with("JBSWY3DPEHPK3PXP")
        mock_pyotp.TOTP.return_value.verify.assert_called_once_with(
            "123456", valid_window=1
        )

    def test_verify_invalid_code(self):
        mock_pyotp = _mock_pyotp()
        mock_pyotp.TOTP.return_value.verify.return_value = False

        with patch.dict(sys.modules, {"pyotp": mock_pyotp}):
            tfa = TwoFactorAuth(totp_secret="JBSWY3DPEHPK3PXP")
            result = tfa.verify("000000")

        assert result is False
        mock_pyotp.TOTP.return_value.verify.assert_called_once_with(
            "000000", valid_window=1
        )

    def test_generate_secret(self):
        mock_pyotp = _mock_pyotp()

        with patch.dict(sys.modules, {"pyotp": mock_pyotp}):
            result = TwoFactorAuth.generate_secret()

        assert result == "GENERATEDSECRET123"
        mock_pyotp.random_base32.assert_called_once()

    def test_get_provisioning_url(self):
        mock_pyotp = _mock_pyotp()

        with patch.dict(sys.modules, {"pyotp": mock_pyotp}):
            result = TwoFactorAuth.get_provisioning_url("SECRET")

        assert "otpauth://" in result
        mock_pyotp.TOTP.assert_called_once_with("SECRET")
        mock_pyotp.TOTP.return_value.provisioning_uri.assert_called_once_with(
            name="admin", issuer_name="AI4Trade Bot"
        )

    def test_verify_pyotp_not_installed(self):
        tfa = TwoFactorAuth(totp_secret="JBSWY3DPEHPK3PXP")
        with patch.dict(sys.modules, {"pyotp": None}):
            result = tfa.verify("123456")
        assert result is False

    def test_generate_secret_pyotp_not_installed(self):
        with patch.dict(sys.modules, {"pyotp": None}):
            with pytest.raises(RuntimeError, match="pyotp nicht installiert"):
                TwoFactorAuth.generate_secret()

    def test_get_provisioning_url_pyotp_not_installed(self):
        with patch.dict(sys.modules, {"pyotp": None}):
            with pytest.raises(RuntimeError, match="pyotp nicht installiert"):
                TwoFactorAuth.get_provisioning_url("SECRET")
