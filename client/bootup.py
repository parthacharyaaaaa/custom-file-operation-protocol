'''Methods invoked during client bootup'''

import asyncio
import json
import ssl
from pathlib import Path
from typing import Any, Final, Optional

from client import tls_sentinel
from client.config.constants import ClientConfig
from client.cmd.window import ClientWindow
from client.session_manager import SessionManager
from client.communication import incoming, outgoing
from client.operations import info_operations

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.types import CertificatePublicKeyTypes
from cryptography.hazmat.primitives import hashes

from models.response_codes import SuccessFlags

import pytomlpp


__all__ = ('init_session_manager',
           'init_client_configurations',
           'init_cmd_window',
           'create_server_connection',
           'heartbeat_monitor')

def init_session_manager(host: str, port: int) -> SessionManager:
    return SessionManager(host, port)

def init_client_configurations() -> ClientConfig:
    constants_mapping: dict[str, Any] = pytomlpp.load(Path.joinpath(Path(__file__).parent, 'config', 'constants.toml'))
    client_config = ClientConfig.model_validate(constants_mapping)
    client_config.server_fingerprints_filepath = Path.joinpath(Path(__file__).parent, client_config.server_fingerprints_filepath)

    return client_config

def init_cmd_window(host: str, port: int,
                    reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                    client_config: ClientConfig, session_manager: SessionManager) -> ClientWindow:
    return ClientWindow(host, port, reader, writer, client_config, session_manager)

async def create_server_connection(host: str, port: int, fingerprints_path: Path, ssl_context: ssl.SSLContext, client_config: ClientConfig, ssl_handshake_timeout: Optional[float] = None, blind_trust: bool = False) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    fingerprints_mapping: dict[str, str] = {}
    if fingerprints_path.is_file() and (fingerprint_data := fingerprints_path.read_text(encoding='utf-8')):
        fingerprints_mapping = json.loads(fingerprint_data)
    
    reader, writer = await asyncio.open_connection(host=host, port=port,
                                                   ssl=ssl_context,
                                                   ssl_handshake_timeout=ssl_handshake_timeout)

    peer_certificate_bytes: Final[bytes] = writer.get_extra_info('ssl_object').getpeercert(binary_form=True)
    peer_certificate: Final[x509.Certificate] = x509.load_der_x509_certificate(peer_certificate_bytes)
    fingerprint: str = peer_certificate.fingerprint(hashes.SHA256()).hex()

    if (host not in fingerprints_mapping) or blind_trust:
        fingerprints_mapping[host] = fingerprint
        fingerprints_path.write_text(json.dumps(fingerprints_mapping, indent=4), encoding='utf-8')
        return reader, writer
    if fingerprint == fingerprints_mapping[host]:
        return reader, writer
    
    # Attempt to reconcile through server rollover data, if provided
    pubkey: Final[CertificatePublicKeyTypes] = peer_certificate.public_key()
    if not isinstance(pubkey, ec.EllipticCurvePublicKey):
        raise ConnectionError(f'Failed SSL reconciliation with server {host}:{port}, key type mismatch: expected {str(ec.EllipticCurvePublicKey)}, received {str(type(pubkey))}')
    
    try:
        rollover_data: Final[dict[str, Any]] = await tls_sentinel.get_rollover_data(reader, writer, client_config, host, port)
        if not rollover_data:
            raise Exception
        
        # Verify that older public key is indeed the one cached by the client
        old_certificate: Final[x509.Certificate] = x509.load_der_x509_certificate(bytes.fromhex(rollover_data['old_certificate']))
        if fingerprints_mapping[host] != old_certificate.fingerprint(hashes.SHA256()).hex():
            raise Exception

        old_pubkey: Final[CertificatePublicKeyTypes] = old_certificate.public_key()
        if not isinstance(old_pubkey, ec.EllipticCurvePublicKey):
            raise ConnectionError(f'Failed SSL reconciliation with server {host}:{port}, key type mismatch: expected {str(ec.EllipticCurvePublicKey)}, received {str(type(pubkey))}')
        
        data_buffer: Final[bytes] = (bytes.fromhex(rollover_data['old_pubkey_hash']) +
                                     bytes.fromhex(rollover_data['new_pubkey_hash']) +
                                     bytes.fromhex(rollover_data['nonce']))
        
        old_pubkey.verify(signature=bytes.fromhex(rollover_data['signature']),
                                            data=data_buffer,
                                            signature_algorithm=ec.ECDSA(hashes.SHA256()))
    except Exception as e:
        raise ssl.SSLError(f'[TOFU]: Certification mismatch for {host}. Expected {fingerprints_mapping[host]}, received {fingerprint}. If you are sure that you trust this server, start the shell with the "--blind-trust" flag')
    
    print(f'Certificate rotated for connection to known server {host}:{port} through TOFU reconciliation')
    fingerprints_mapping[host] = fingerprint
    fingerprints_path.write_text(json.dumps(fingerprints_mapping, indent=4), encoding='utf-8')
    
    return reader, writer

async def heartbeat_monitor(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                            client_config: ClientConfig, session_manager: SessionManager,
                            hb_interval: float, read_timeout: float = 3.0) -> None:
    '''Background task for monitoring heartbeat of the remote server'''
    conn_teardown: bool = False
    while True:
        await info_operations.send_heartbeat(reader, writer, client_config, session_manager, end_connection=False)
        try:
            heartbeat_header, _ = await incoming.process_response(reader, writer, read_timeout)
            if heartbeat_header.code != SuccessFlags.HEARTBEAT.value:
                conn_teardown = True
        except asyncio.TimeoutError:
            conn_teardown = True
        
        if conn_teardown:
            async with outgoing.STREAM_LOCK:
                writer.close()
                await writer.wait_closed()

            session_manager.clear_auth_data()
            asyncio.get_event_loop().call_exception_handler({
                'exception' : TimeoutError('Server heartbeat stopped'),
                'task' : asyncio.current_task(),
                'message' : 'Server timeout'
            })
            return
        
        await asyncio.sleep(hb_interval)