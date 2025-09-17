'''Utility methods for server-side SSL/TLS logic'''

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
    '''Generate a self-signed x.509 certificate for the server
    Args:
        cert_filepath (Path): Filepath of the output file to write the generated certificate into (CRT extension).
        key_filepath (Path): Filepath of the output key file to write the generated private key into (PEM extension).
        dns_name (str): Domain name of the issuer, defaults to localhost

    Returns:
        tuple[x509.Certificate,ec.EllipticCurvePrivateKey]: Pair of x.509 certificate and corresponding ec private key
    '''
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
            Path.unlink(key_filepath, missing_ok=True)
        raise e
    
    return cert, private_key

def make_server_ssl_context(certfile: Path,
                            keyfile: Path,
                            ciphers: str,
                            cafile: Optional[Path] = None) -> ssl.SSLContext:
    '''Create an SSL context for a server

    Args:
        certfile (Path): Path to the certificate file (CRT/PEM) used by the server.
        keyfile (Path): Path to the private key file (PEM) used by the server.
        ciphers (str): String specifying the allowed ciphers (OpenSSL cipher list format).
        cafile (Optional[Path]): Path to a CA bundle file. If not provided, defaults to certifi's CA store.

    Returns:
        ssl.SSLContext: Configured SSL context for the server.
    '''

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
                            host: str, port: int,
                            grace_period: float,
                            reason: str = 'rotation') -> dict[str, dict[str, Union[str, float]]]:
    '''Generate a rollover token to transition from an old certificate to a new one

    Args:
        new_cert (x509.Certificate): The new x.509 certificate being rolled over to.
        old_cert (x509.Certificate): The existing x.509 certificate being replaced.
        old_key (ec.EllipticCurvePrivateKey): Private key corresponding to the old certificate, used to sign the token.
        nonce_length (int): Length (in bytes) of the randomly generated nonce.
        host (str): Hostname associated with the rollover.
        port (int): Port associated with the rollover.
        grace_period (float): Time in seconds for which the rollover token remains valid.
        reason (str): Reason for rollover, defaults to 'rotation'.

    Returns:
        dict[str,dict[str,Union[str,float]]]: Mapping of the old certificate's SHA256 fingerprint to rollover metadata,
            including host, port, certificate details, pubkey hashes, timestamps, reason, signature, and nonce.
    '''

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
                     cert_filename: str = 'certfile.crt',
                     key_filename: str = 'keyfile.pem') -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    
    '''Load an x.509 certificate and its corresponding EC private key from disk

    Args:
        credentials_directory (Path): Directory containing the certificate and private key files.
        cert_filename (Optional[str]): Filename of the certificate (CRT/PEM), defaults to 'certfile.crt'.
        key_filename (Optional[str]): Filename of the private key (PEM), defaults to 'keyfile.pem'.

    Raises:
        FileNotFoundError: If the certificate or key file does not exist at the given path.
        ValueError: If the loaded private key is not an EC key.

    Returns:
        tuple[x509.Certificate,ec.EllipticCurvePrivateKey]: The loaded x.509 certificate and its associated EC private key.
    '''

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
    '''Trim rollover data to keep only the most recent entries

    Args:
        rollover_data (dict[str,dict[str,Union[str,float]]]): Mapping of certificate fingerprints to rollover metadata.
        size (int): Maximum number of entries to retain.
        reference_key (str): Metadata field used for sorting, defaults to 'issued_at'.

    Returns:
        dict[str,dict[str,Union[str,float]]]: Filtered rollover data containing only the most recent entries.
    '''

    return {k:v
            for k,v in rollover_data.items()
            if v[reference_key]
            in sorted((v[reference_key]
                       for v in rollover_data.values()),
                       reverse=True)[:size]}

def rotate_server_certificates(server_config: ServerConfig,
                               reason: str = 'periodic rotation') -> ssl.SSLContext:
    '''Rotate the server's SSL certificates and update rollover metadata

    Args:
        server_config (ServerConfig): Configuration object containing certificate paths, host/port, ciphers, and rollover settings.
        reason (str): Reason for rotation, defaults to 'periodic rotation'.

    Returns:
        ssl.SSLContext: New SSL context configured with the rotated certificate and key.
    '''

    old_certificate, old_key = load_credentials(credentials_directory=server_config.certificate_filepath.parent,
                                                cert_filename=str(server_config.certificate_filepath),
                                                key_filename=str(server_config.key_filepath))
    
    new_certificate, new_key = generate_self_signed_credentials(cert_filepath=server_config.certificate_filepath,
                                                                key_filepath=server_config.key_filepath,
                                                                dns_name=str(server_config.host))
    
    rollover_token: Final[dict[str, dict[str, Union[str, float]]]] = generate_rollover_token(new_cert=new_certificate,
                                                                                             old_cert=old_certificate, old_key=old_key,
                                                                                             nonce_length=server_config.rollover_token_nonce_length,
                                                                                             host=str(server_config.host), port=server_config.port,
                                                                                             grace_period=server_config.rollover_grace_window,
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