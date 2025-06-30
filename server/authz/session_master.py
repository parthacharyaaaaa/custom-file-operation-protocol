import os
import re
from hashlib import pbkdf2_hmac
from typing import Optional
from server.authz.singleton import MetaSessionMaster
from server.bootup import connection_master
from server.connectionpool import ConnectionProxy
from server.config import ServerConfig
from server.errors import UserAuthenticationError

class SessionMaster(metaclass=MetaSessionMaster):
    HASHING_ALGORITHM: str = 'sha256'
    PBKDF_ITERATIONS: int = 100_000
    SALT_LENGTH: int = 16
    USERNAME_REGEX: str = ServerConfig.USERNAME_REGEX.value

    '''Class for managing user sessions'''
    def __init__(self):
        self.connection_master = connection_master

    @staticmethod
    def generate_password_hash(password: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes]:
        if not salt:
            salt: bytes = os.urandom(SessionMaster.SALT_LENGTH)
        return pbkdf2_hmac(SessionMaster.HASHING_ALGORITHM, password, salt, iterations=SessionMaster.PBKDF_ITERATIONS), salt
    
    @staticmethod
    def check_username_validity(username: str) -> str:
        username = username.strip()
        if not re.match(SessionMaster.USERNAME_REGEX, username):
            return None
        return username

    @staticmethod
    def verify_password_hash(password: str, password_hash: bytes, salt: bytes) -> bool:
        return pbkdf2_hmac(SessionMaster.HASHING_ALGORITHM, password, salt, iterations=SessionMaster.PBKDF_ITERATIONS) == password_hash

    def authorize_session():
        pass

    def authenticate_session():
        pass

    async def create_user(self, username: str, password: str, make_dir: bool = False) -> None:
        if not (username:=SessionMaster.check_username_validity(username)):
            raise UserAuthenticationError('Invalid username')
        
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)   # Account creation is high-priority
        try:
            async with proxy.cursor() as cursor:
                await cursor.execute('''SELECT username FROM users WHERE username = %s''', (username,))
                res: tuple[str] = await cursor.fetchone()
                if res:
                    raise UserAuthenticationError(f'Local user {res[0]} already exists')
                
                pw_hash, pw_salt = SessionMaster.generate_password_hash(password)
        
                await cursor.execute('''INSERT INTO users (username, password_hash, password_salt) VALUES (%s, %s, %s)''',
                                     (username, pw_hash, pw_salt,))
                await proxy.commit()
        finally:
            await self.connection_master.reclaim_connection(proxy._conn)    # Always return leased connection to connection master

        if make_dir:
            os.makedirs(os.path.join(ServerConfig.ROOT.value, username))

    def terminate_session():
        pass

    def refresh_session():
        pass

    def ban():
        pass