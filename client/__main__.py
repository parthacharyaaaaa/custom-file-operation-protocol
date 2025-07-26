import asyncio
import argparse

from client import cli_parser
from client.bootup import init_client_configurations, init_session_manager, create_server_connection, init_cmd_window
from client.cmd.window import ClientWindow
from client.config.constants import ClientConfig
from client.operations import auth_operations
from client.session_manager import SessionManager

from models.request_model import BaseAuthComponent

async def main() -> None:
    '''Entrypoint function for client shell'''
    args: argparse.Namespace = cli_parser.parse_args()
    
    client_config: ClientConfig = init_client_configurations()
    reader, writer = await create_server_connection(args.host, args.port, client_config.ssl_handshake_timeout)
    session_manager: SessionManager = init_session_manager()

    if args.password:
        auth_component: BaseAuthComponent = BaseAuthComponent(identity=args.username, password=args.password)
        await auth_operations.authorize(reader, writer, auth_component, client_config, session_manager)

    client_cmd_window: ClientWindow = init_cmd_window(args.host, args.port, reader, writer, client_config, session_manager)

    await client_cmd_window.cmdloop()

asyncio.run(main())