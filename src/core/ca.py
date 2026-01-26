"""Certificate Authority service for clone session TLS."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from src.config import settings


class CAService:
    """Manages the Certificate Authority for clone session certificates."""

    def __init__(self):
        self.cert_dir = settings.ca.cert_dir
        self.ca_cert_path = self.cert_dir / "ca.crt"
        self.ca_key_path = self.cert_dir / "ca.key"
        self._ca_cert = None
        self._ca_key = None

    def initialize(self) -> None:
        """Initialize CA, generating root cert if needed."""
        if not settings.ca.enabled:
            return

        self.cert_dir.mkdir(parents=True, exist_ok=True)

        if self.ca_cert_path.exists() and self.ca_key_path.exists():
            self._load_ca()
        else:
            self._generate_ca()

    def _generate_ca(self) -> None:
        """Generate new CA certificate and key."""
        # Generate private key
        private_key = ec.generate_private_key(ec.SECP256R1())

        # Build certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PureBoot"),
            x509.NameAttribute(NameOID.COMMON_NAME, "PureBoot CA"),
        ])

        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=365 * settings.ca.ca_validity_years))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    key_encipherment=False,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(private_key, hashes.SHA256())
        )

        # Save key with restricted permissions
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.ca_key_path.write_bytes(key_pem)
        os.chmod(self.ca_key_path, 0o600)

        # Save certificate
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        self.ca_cert_path.write_bytes(cert_pem)

        self._ca_key = private_key
        self._ca_cert = cert

    def _load_ca(self) -> None:
        """Load existing CA certificate and key."""
        key_pem = self.ca_key_path.read_bytes()
        self._ca_key = serialization.load_pem_private_key(key_pem, password=None)

        cert_pem = self.ca_cert_path.read_bytes()
        self._ca_cert = x509.load_pem_x509_certificate(cert_pem)

    def issue_session_cert(
        self,
        session_id: str,
        role: str,  # "source" or "target"
        san_ip: str | None = None,
    ) -> tuple[str, str]:
        """
        Issue a certificate for a clone session participant.

        Returns:
            Tuple of (cert_pem, key_pem) as strings
        """
        if not self._ca_cert or not self._ca_key:
            raise RuntimeError("CA not initialized")

        # Generate key for this cert
        private_key = ec.generate_private_key(ec.SECP256R1())

        # Build subject
        cn = f"clone-{session_id}-{role}"
        subject = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PureBoot"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ])

        now = datetime.now(timezone.utc)
        validity_hours = settings.ca.session_cert_validity_hours

        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self._ca_cert.subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(hours=validity_hours))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
        )

        # Add key usage for TLS
        if role == "source":
            # Source acts as server
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
        else:
            # Target acts as client
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )

        # Add SAN if IP provided
        if san_ip:
            from ipaddress import ip_address
            builder = builder.add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(cn),
                    x509.IPAddress(ip_address(san_ip)),
                ]),
                critical=False,
            )
        else:
            builder = builder.add_extension(
                x509.SubjectAlternativeName([x509.DNSName(cn)]),
                critical=False,
            )

        cert = builder.sign(self._ca_key, hashes.SHA256())

        # Serialize
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        return cert_pem, key_pem

    def get_ca_cert_pem(self) -> str:
        """Get CA certificate as PEM string."""
        if not self._ca_cert:
            raise RuntimeError("CA not initialized")
        return self._ca_cert.public_bytes(serialization.Encoding.PEM).decode()

    @property
    def is_initialized(self) -> bool:
        """Check if CA is initialized."""
        return self._ca_cert is not None and self._ca_key is not None


# Singleton instance
ca_service = CAService()
