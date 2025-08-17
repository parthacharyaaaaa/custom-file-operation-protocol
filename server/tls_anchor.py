import certifi
import hashlib
import secrets
import ssl
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import json

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes

from server.config.server_config import ServerConfig

def generate_certificate_fingerprint(certificate: bytes) -> str:
    return hashlib.sha256(certificate).hexdigest()

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
    ssl_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_verify_locations(cafile or certifi.where())
    ssl_context.load_cert_chain(certfile, keyfile)
    ssl_context.set_ciphers(ciphers)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.VerifyMode.CERT_NONE
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

    return ssl_context

def generate_rollover_token(new_cert: x509.Certificate,
                            old_cert: x509.Certificate,
                            old_key: ec.EllipticCurvePrivateKey,
                            nonce_length: int,
                            output_path: Path,
                            host: str,
                            grace_period: float,
                            reason: str = 'rotation') -> None:
    issuance: float = time.time()
    old_pubkey_hash: bytes = hashlib.sha256(old_cert.public_key().public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfoz))
    new_pubkey_hash: bytes = hashlib.sha256(new_cert.public_key().public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfoz))
    json.dump(fp=output_path,
              indent=4,
              obj={
                  'server' : host,
                  'old_pubkey_hash' : old_pubkey_hash.hex(),
                  'new_pubkey_hash' : new_pubkey_hash.hex(),
                  'issued_at' : issuance,
                  'not_before' : issuance+grace_period,
                  'reason' : reason,
                  'signature' : old_key.sign(old_pubkey_hash).hex(),
                  'nonce' : secrets.token_hex(nonce_length)
                  })

def load_credentials(credentials_directory: Path,
                     cert_filename: Optional[str] = 'certfile.crt',
                     key_filename: Optional[str] = 'keyfile.pem') -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    certificate_filepath: Path = credentials_directory.joinpath(cert_filename)
    if not certificate_filepath.is_file():
        raise FileNotFoundError(f'File {certificate_filepath} not found')
    
    key_filepath: Path = credentials_directory.joinpath(key_filename)
    if not key_filepath.is_file():
        raise FileNotFoundError(f'File {key_filepath} not found')
    
    certificate_bytes: bytes = Path.read_bytes(certificate_filepath)
    private_key_bytes: bytes = Path.read_bytes(key_filepath)

    private_key: PrivateKeyTypes = serialization.load_pem_private_key(private_key_bytes)
    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise ValueError(f"Expected private key to be EC key, got instance of {private_key.__class__}")

    return x509.load_pem_x509_certificate(certificate_bytes), private_key
