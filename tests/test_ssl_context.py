import hashlib
import ssl

from core.ssl_context import CertificatePinning


class TestCertificatePinning:
    """Tests fuer Certificate Pinning Funktionalitaet."""

    def test_create_ssl_context_valid(self):
        """create_ssl_context gibt einen gueltigen SSLContext zurueck."""
        pinning = CertificatePinning()
        ctx = pinning.create_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True

    def test_verify_fingerprint_no_pins_configured(self):
        """verify_fingerprint gibt True zurueck wenn keine Pins konfiguriert."""
        pinning = CertificatePinning(fingerprints={})
        cert_der = b"\x00\x01\x02\x03"
        assert pinning.verify_fingerprint("api.bitget.com", cert_der) is True

    def test_verify_fingerprint_match(self):
        """verify_fingerprint gibt True bei passendem Pin."""
        cert_der = b"\x00\x01\x02\x03"
        cert_hash = hashlib.sha256(cert_der).digest()
        fingerprint = "sha256/" + cert_hash.hex()
        pinning = CertificatePinning(
            fingerprints={
                "api.bitget.com": [fingerprint],
            }
        )
        assert pinning.verify_fingerprint("api.bitget.com", cert_der) is True

    def test_verify_fingerprint_mismatch(self):
        """verify_fingerprint gibt False bei nicht passendem Pin."""
        cert_der = b"\x00\x01\x02\x03"
        wrong_fingerprint = "sha256/" + ("aa" * 32)
        pinning = CertificatePinning(
            fingerprints={
                "api.bitget.com": [wrong_fingerprint],
            }
        )
        assert pinning.verify_fingerprint("api.bitget.com", cert_der) is False

    def test_verify_fingerprint_empty_pins_list(self):
        """verify_fingerprint gibt False bei leerer Pin-Liste."""
        cert_der = b"\x00\x01\x02\x03"
        pinning = CertificatePinning(
            fingerprints={
                "api.bitget.com": [],
            }
        )
        assert pinning.verify_fingerprint("api.bitget.com", cert_der) is False
