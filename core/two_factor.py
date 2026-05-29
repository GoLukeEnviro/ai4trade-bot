from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class TwoFactorAuth:
    """TOTP-basierte 2FA fuer Live-Modus."""

    def __init__(self, totp_secret: str = ""):
        self._secret = totp_secret

    def verify(self, code: str) -> bool:
        if not self._secret:
            log.warning("Kein TOTP-Secret konfiguriert, 2FA uebersprungen")
            return True

        try:
            import pyotp

            totp = pyotp.TOTP(self._secret)
            return totp.verify(code, valid_window=1)
        except ImportError:
            log.error("pyotp nicht installiert. pip install pyotp")
            return False

    @staticmethod
    def generate_secret() -> str:
        try:
            import pyotp

            return pyotp.random_base32()
        except ImportError:
            raise RuntimeError("pyotp nicht installiert. pip install pyotp")

    @staticmethod
    def get_provisioning_url(
        secret: str, issuer: str = "AI4Trade Bot", account: str = "admin"
    ) -> str:
        try:
            import pyotp

            totp = pyotp.TOTP(secret)
            return totp.provisioning_uri(name=account, issuer_name=issuer)
        except ImportError:
            raise RuntimeError("pyotp nicht installiert. pip install pyotp")
