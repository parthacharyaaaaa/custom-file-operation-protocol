import asyncio
import argparse
import ssl
import sys
from typing import Final

from client import tls_sentinel
from client.parsing import entrypoint_parser
from client.bootup import init_client_configurations, init_session_manager, create_server_connection, init_cmd_window
from client.cmd.client_window import ClientWindow
from client.config.constants import ClientConfig
from client.operations import auth_operations
from client.session_manager import SessionManager

from models.request_model import BaseAuthComponent

async def main() -> None:
    '''Entrypoint function for client shell'''
    args: argparse.Namespace = entrypoint_parser.parse_args()
    
    client_config: Final[ClientConfig] = init_client_configurations()
    ssl_context: Final[ssl.SSLContext] = tls_sentinel.make_client_ssl_context(ciphers=client_config.ciphers)
    reader, writer = await create_server_connection(host=args.host, port=args.port,
                                                    client_config=client_config,
                                                    fingerprints_path=client_config.server_fingerprints_filepath,
                                                    ssl_context=ssl_context,
                                                    ssl_handshake_timeout=client_config.ssl_handshake_timeout,
                                                    blind_trust=args.blind_trust)
    session_manager: Final[SessionManager] = init_session_manager(*writer.get_extra_info('peername'))

    if args.password:
        auth_component: BaseAuthComponent = BaseAuthComponent(identity=args.username, password=args.password)
        await auth_operations.authorize(reader, writer, auth_component, client_config, session_manager)

    client_cmd_window: Final[ClientWindow] = init_cmd_window(args.host, args.port, reader, writer, client_config, session_manager)


    try:
        await client_cmd_window.cmdloop()
    except KeyboardInterrupt:
        writer.close()
        await writer.wait_closed()

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

asyncio.run(main())