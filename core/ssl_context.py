from __future__ import annotations

import ssl
import hashlib
import logging
from pathlib import Path

log = logging.getLogger(__name__)

KNOWN_FINGERPRINTS: dict[str, list[str]] = {}


class CertificatePinning:
    """Certificate Pinning fuer HTTPS-Verbindungen."""

    def __init__(self, fingerprints: dict[str, list[str]] | None = None):
        self._fingerprints = fingerprints if fingerprints is not None else KNOWN_FINGERPRINTS

    def create_ssl_context(self) -> ssl.SSLContext:
        """SSL-Context mit Certificate Pinning erstellen."""
        ctx = ssl.create_default_context()
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True
        return ctx

    def verify_fingerprint(self, hostname: str, cert_der: bytes) -> bool:
        """
        Zertifikat-Fingerprint gegen bekannte Pins pruefen.
        Returns True wenn gueltig oder kein Pin konfiguriert.
        """
        if hostname not in self._fingerprints:
            return True

        known_pins = self._fingerprints[hostname]
        if not known_pins:
            return False

        cert_hash = hashlib.sha256(cert_der).digest()
        fingerprint = "sha256/" + cert_hash.hex()

        if fingerprint in known_pins:
            return True

        log.warning("Certificate pin mismatch for %s: %s", hostname, fingerprint)
        return False

    @staticmethod
    def get_certificate_fingerprint(hostname: str, port: int = 443) -> str:
        """Fingerprint eines Zertifikats abrufen (fuer Setup)."""
        import socket
        conn = ssl.create_connection((hostname, port))
        try:
            cert = conn.getpeercert(binary_form=True)
            fingerprint = hashlib.sha256(cert).digest()
            return "sha256/" + fingerprint.hex()
        finally:
            conn.close()
