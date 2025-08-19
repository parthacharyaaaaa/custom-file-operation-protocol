import asyncio
import hashlib
import ssl
import time
from typing import Any, Final

from client.communication.outgoing import send_request
from client.communication.incoming import process_response
from client.config.constants import ClientConfig

from models.request_model import BaseHeaderComponent
from models.flags import CategoryFlag, InfoFlags
from models.response_codes import SuccessFlags

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

async def get_rollover_data(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                         client_config: ClientConfig,
                         host: str, port: int) -> dict[str, Any]:
    header_component: Final[BaseHeaderComponent] = BaseHeaderComponent(version=client_config.version,
                                                                       auth_size=0, body_size=0,
                                                                       sender_hostname=host, sender_port=port, sender_timestamp=time.time(),
                                                                       category=CategoryFlag.INFO, subcategory=InfoFlags.SSL_CREDENTIALS)
    await send_request(writer, header_component=header_component)
    response_header, response_body = await process_response(reader, writer, client_config.read_timeout)
    if response_header.code != SuccessFlags.SUCCESSFUL_QUERY_ANSWER.value:
        raise ConnectionError(f'Failed to fetch SSL credentials from server running at {host}:{port}')
    
    return response_body.contents['rollover_data']

