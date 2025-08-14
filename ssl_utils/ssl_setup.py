import certifi
import ssl
from typing import Optional
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from datetime import datetime, timedelta
from pathlib import Path

__all__ = ('generate_self_signed_credentials', 'make_server_ssl_context', 'make_client_ssl_context')

def generate_self_signed_credentials(credentials_directory: Path,
                                     dns_name: str = 'localhost',
                                     cert_filename: Optional[str] = 'certfile.crt',
                                     key_filename: Optional[str] = 'keyfile.pem') -> None:
    private_key: ec.EllipticCurvePrivateKey = ec.generate_private_key(ec.SECP256R1())
    
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, dns_name)
    ])
    
    cert: x509.Certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now())
        .not_valid_after(datetime.now() + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(dns_name)]),
            critical=False
        )
        .sign(private_key, hashes.SHA256())
    )

    Path.mkdir(credentials_directory, exist_ok=True)
    certpath: Path = Path.joinpath(credentials_directory, cert_filename)
    keypath: Path = Path.joinpath(credentials_directory, key_filename)

    try:
        with open(certpath, 'wb') as certfile:
            certfile.write(cert.public_bytes(encoding=serialization.Encoding.PEM))
        with open(keypath, 'wb') as keyfile:
            keyfile.write(private_key.private_bytes(encoding=serialization.Encoding.PEM,
                                                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                                                    encryption_algorithm=serialization.NoEncryption()))
    except Exception as e:
        Path.unlink(certpath, missing_ok=True)
        Path.unlink(keypath, missing_ok=True)
        raise e

def make_server_ssl_context(certfile: Path,
                            keyfile: Path,
                            ciphers: str,
                            cafile: Optional[Path] = None) -> ssl.SSLContext:
    ssl_context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH, cafile=cafile or certifi.where())
    ssl_context.load_cert_chain(certfile, keyfile)
    ssl_context.set_ciphers(ciphers)
    
    ssl_context.options |= ssl.OP_NO_TLSv1
    ssl_context.options |= ssl.OP_NO_TLSv1_1
    ssl_context.options |= ssl.OP_SINGLE_DH_USE
    ssl_context.options |= ssl.OP_SINGLE_ECDH_USE
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.VerifyMode.CERT_REQUIRED

    return ssl_context

def make_client_ssl_context(cafile: Optional[Path] = None) -> ssl.SSLContext:
    ssl_context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH,
                                             cafile=cafile or certifi.where())
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.VerifyMode.CERT_REQUIRED

    return ssl_context
