from typing import Final

from server.tls.credentials import rotate_server_certificates
from server.bootup import create_server_config
from server.config.server_config import ServerConfig

def main() -> None:
    server_config: Final[ServerConfig] = create_server_config()
    rotate_server_certificates(server_config=server_config)

if __name__ == '__main__':
    main()