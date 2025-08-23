import certifi
import hashlib
import secrets
import ssl
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, Optional, Union
import json

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes

from server.config.server_config import ServerConfig

__all__ = ('generate_self_signed_credentials', 'generate_rollover_token', 'make_server_ssl_context', 'load_credentials', 'rotate_server_certificates')

def generate_self_signed_credentials(cert_filepath: Path,
                                     key_filepath: Path,
                                     dns_name: str = 'localhost') -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
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

    certfile_exists, keyfile_exists = cert_filepath.exists(), key_filepath.exists()
    try:
        with open(cert_filepath, 'wb') as certfile:
            certfile.write(cert.public_bytes(encoding=serialization.Encoding.PEM))
        with open(key_filepath, 'wb') as keyfile:
            keyfile.write(private_key.private_bytes(encoding=serialization.Encoding.PEM,
                                                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                                                    encryption_algorithm=serialization.NoEncryption()))
    except Exception as e:
        if not certfile_exists:
            Path.unlink(cert_filepath, missing_ok=True)
        if not keyfile_exists:
            Path.unlink(keyfile_exists, missing_ok=True)
        raise e
    
    return cert, private_key

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
                            host: str, port: int,
                            grace_period: float,
                            reason: str = 'rotation') -> dict[str, dict[str, Union[str, float]]]:
    issuance: float = time.time()
    old_pubkey_hash: str = hashlib.sha256(old_cert.public_key().public_bytes(encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()
    new_pubkey_hash: str = hashlib.sha256(new_cert.public_key().public_bytes(encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()
    nonce: str = secrets.token_hex(nonce_length)
    signature: Final[str] = old_key.sign(data=bytes.fromhex(old_pubkey_hash)+bytes.fromhex(new_pubkey_hash)+bytes.fromhex(nonce),
                                         signature_algorithm=ec.ECDSA(hashes.SHA256())).hex()

    
    return {
        old_cert.fingerprint(hashes.SHA256()).hex() : 
            {'hostname' : host,
            'port' : port,
            'old_certificate' : old_cert.public_bytes(serialization.Encoding.DER).hex(),
            'old_pubkey_hash' : old_pubkey_hash,
            'new_pubkey_hash' : new_pubkey_hash,
            'issued_at' : issuance,
            'valid_until' : issuance+grace_period,
            'reason' : reason,
            'signature' : signature,
            'nonce' : nonce}
        }

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

    private_key: PrivateKeyTypes = serialization.load_pem_private_key(private_key_bytes, password=None)
    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise ValueError(f"Expected private key to be EC key, got instance of {private_key.__class__}")

    return x509.load_pem_x509_certificate(certificate_bytes), private_key

def trim_rollover_data(rollover_data: dict[str, dict[str, Union[str, float]]], size: int, reference_key: str = 'issued_at') -> dict[str, dict[str, Union[str, float]]]:
    return {k:v
            for k,v in rollover_data.items()
            if v[reference_key]
            in sorted((v[reference_key]
                       for v in rollover_data.values()),
                       reverse=True)[:size]}

def rotate_server_certificates(server_config: ServerConfig,
                               reason: str = 'periodic rotation') -> ssl.SSLContext:

    old_certificate, old_key = load_credentials(credentials_directory=server_config.certificate_filepath.parent,
                                                cert_filename=server_config.certificate_filepath,
                                                key_filename=server_config.key_filepath)
    
    new_certificate, new_key = generate_self_signed_credentials(cert_filepath=server_config.certificate_filepath,
                                                                key_filepath=server_config.key_filepath,
                                                                dns_name=str(server_config.host))
    
    rollover_token: Final[dict[str, dict[str, Union[str, float]]]] = generate_rollover_token(new_cert=new_certificate,
                                                                                             old_cert=old_certificate, old_key=old_key,
                                                                                             nonce_length=server_config.rollover_token_nonce_length,
                                                                                             host=str(server_config.host), port=server_config.port,
                                                                                             grace_period=server_config.rollover_grace_window,
                                                                                             output_path=server_config.rollover_data_filepath,
                                                                                             reason=reason)
    existing_tokens: dict[str, dict[str, Union[str, float]]] = {}
    with open(server_config.rollover_data_filepath, 'r+', encoding='utf-8') as rotation_metadata_file:
        if (token_data:=rotation_metadata_file.read()):
            existing_tokens = json.loads(token_data)
        
        rotation_metadata_file.seek(0)

        existing_tokens = trim_rollover_data(existing_tokens, server_config.rollover_history_length-1)
        existing_tokens.update(rollover_token)

        rotation_metadata_file.write(json.dumps(existing_tokens, indent=4))
        rotation_metadata_file.truncate()
    
    return make_server_ssl_context(certfile=server_config.certificate_filepath,
                                   keyfile=server_config.key_filepath,
                                   ciphers=server_config.ciphers)