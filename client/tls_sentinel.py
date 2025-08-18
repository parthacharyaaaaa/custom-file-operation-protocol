import hashlib
import ssl

__all__ = ('make_client_ssl_context', 'generate_certificate_fingerprint')

def generate_certificate_fingerprint(certificate: bytes) -> str:
    return hashlib.sha256(certificate).hexdigest()

def make_client_ssl_context(ciphers: str) -> ssl.SSLContext:
    ssl_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.set_ciphers(ciphers)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

    return ssl_context
