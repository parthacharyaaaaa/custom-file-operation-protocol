import os
import asyncio
import re
from secrets import token_bytes
from hmac import compare_digest
from hashlib import pbkdf2_hmac
from typing import Optional, Union
from cachetools import TTLCache
from aiofiles.threadpool.binary import AsyncBufferedIOBase, AsyncBufferedReader
from server.authz.singleton import MetaSessionMaster
from server.bootup import connection_master
from server.connectionpool import ConnectionProxy, ConnectionPoolManager
from server.config import ServerConfig
from server.errors import UserAuthenticationError

class SessionAuthenticationPair:
    __slots__ = '_token, _refresh_digest'
    _token: bytes
    _refresh_digest: bytes

    @property
    def token(self) -> bytes:
        return self._token
    @property
    def refresh_digest(self) -> bytes:
        return self._refresh_digest

    def __init__(self, token: bytes, refresh_digest: bytes):
        self._token = token
        self._refresh_digest = refresh_digest
    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.token}, {self.refresh_digest}) at location {id(self)}>'
    
    def update_digest(self, new_digest: bytes) -> None:
        self._refresh_digest = new_digest

class SessionMaster(metaclass=MetaSessionMaster):
    HASHING_ALGORITHM: str = 'sha256'
    PBKDF_ITERATIONS: int = 100_000
    SALT_LENGTH: int = 16
    USERNAME_REGEX: str = ServerConfig.USERNAME_REGEX.value
    TOKEN_LENGTH: int = 32
    REFRESH_DIGEST_LENGTH: int = 128

    '''Class for managing user sessions'''
    def __init__(self):
        self.connection_master: ConnectionPoolManager = connection_master
        self.session: dict[str, SessionAuthenticationPair] = {}

    @staticmethod
    def generate_password_hash(password: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes]:
        if not salt:
            salt: bytes = os.urandom(SessionMaster.SALT_LENGTH)
        return pbkdf2_hmac(SessionMaster.HASHING_ALGORITHM, password, salt, iterations=SessionMaster.PBKDF_ITERATIONS), salt
    
    @staticmethod
    def verify_password_hash(password: str, password_hash: bytes, salt: bytes) -> bool:
        try:
            return compare_digest(
                pbkdf2_hmac(SessionMaster.HASHING_ALGORITHM, password, salt, iterations=SessionMaster.PBKDF_ITERATIONS),
                password_hash)
        except: 
            #TODO: Add logging
            return False
    
    @staticmethod
    def check_username_validity(username: str) -> str:
        username = username.strip()
        if not re.match(SessionMaster.USERNAME_REGEX, username):
            return None
        return username

    # Token and refresh digest generation logic kept as static methods in case we ever need to add any more logic to it
    @staticmethod
    def generate_session_token() -> bytes:
        return token_bytes(SessionMaster.TOKEN_LENGTH)
    
    @staticmethod
    def generate_session_refresh_digest() -> bytes:
        return token_bytes(SessionMaster.REFRESH_DIGEST_LENGTH)

    def authenticate_session(self, username: str, token: bytes) -> None:
        try:
            auth_pair: SessionAuthenticationPair = self.session.get(username)
            if auth_pair and compare_digest(auth_pair.token, token): return
        except Exception: 
            #TODO: Add logging for errors raised by hmac.compare_digest
            ...
        raise UserAuthenticationError('Invalid authentication token. Please login again')

    async def authorize_session(self, username: str, password: str) -> SessionAuthenticationPair:
        if not (username:=SessionMaster.check_username_validity(username)):
            raise UserAuthenticationError('Invalid username')
        
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)
        try:
            async with proxy.cursor() as cursor:
                await cursor.execute('''SELECT pw_hash, pw_salt
                                     FROM users
                                     WHERE username = %s;''',
                                     (username,))
                pw_data: tuple[memoryview, memoryview] = await cursor.fetchone()
        finally:
            self.connection_master.reclaim_connection(proxy)

        if not pw_data:
            raise UserAuthenticationError(f'No username with {username} exists')
        if not SessionMaster.verify_password_hash(password, *pw_data):
            raise UserAuthenticationError(f'Invalid password for user {username}')
                
        # Set new session
        auth_pair: SessionAuthenticationPair = SessionAuthenticationPair(SessionMaster.generate_session_token(), SessionMaster.generate_session_refresh_digest())
        #NOTE+TODO: Important design decision here: Should a new login for an exisitng session be rejected, or the session be overwritten and the old user be logged out?
        self.session[username] = auth_pair

        return auth_pair
        
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

    async def delete_user(self, username: str, password: str, *caches) -> None:
        if not (username:=SessionMaster.check_username_validity(username)):
            raise UserAuthenticationError('Invalid username')

        proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)   # Action concerning account statuses have highest priority
        try:
            async with proxy.cursor() as cursor:
                await cursor.execute('''SELECT pw_hash, pw_salt
                                     FROM users
                                     WHERE users.username = %s
                                     FOR UPDATE NOWAIT READ;''',
                                     (username,))
                pw_data: tuple[memoryview, memoryview] = await cursor.fetchone()
                if not pw_data:
                    raise UserAuthenticationError(f'No username with {username} exists')
                
                if not SessionMaster.verify_password_hash(password, *pw_data):
                    raise UserAuthenticationError(f'Invalid password for user {username}')
                
                # All checks passed
                await cursor.execute('''DELETE FROM users
                                     WHERE username = %s;''',
                                     (username,))
        finally:
            await self.connection_master.reclaim_connection(proxy)

        # User deleted, perform relatively less important task of trimming the cache preemptive to usual expiry of this user's buffered readers/writers
        if caches:
            asyncio.create_task(self.terminate_user_cache(identifier=str, *caches))

    async def terminate_user_cache(self, identifier: str, *caches: TTLCache[str, dict[str, Union[AsyncBufferedReader, AsyncBufferedIOBase]]]) -> None:
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=3)
        try:
            async with proxy.cursor() as cursor:
                # Fetch all possible files where the user may have cached a file buffer. TODO: Segregate based on user roles (read, write+append) as well to separate cache scanning logic and save time
                await cursor.execute('''SELECT file_owner, filename
                                     FROM file_permissions
                                     WHERE grantee = %s
                                     UNION
                                     SELECT owner, filename
                                     FROM files
                                     WHERE public IS true;''',
                                     (identifier,))
                
                res: list[tuple[str, str]] = await cursor.fetchall()
                cache_identifers: list[str] = [os.path.join(*file_data) for file_data in res]   # Generate actual cache keys as string 'file_owner/filename'
        finally: 
            await self.connection_master.reclaim_connection(proxy)  # Allow master to reclaim leased connection
        
        for cache in caches:
            # Fetch all mappings for possible files
            buffered_obj_mappings: list[dict[str, Union[AsyncBufferedIOBase, AsyncBufferedReader]]] = [cache.get(cache_identifier) for cache_identifier in cache_identifers]
            for buffered_obj_mapping in buffered_obj_mappings:
                # Close cached buffer if found
                buffered_obj: Union[AsyncBufferedIOBase, AsyncBufferedReader] = buffered_obj_mapping.pop(identifier, None)
                if buffered_obj:
                    await buffered_obj.close()

    def terminate_session(self, username: str, token: bytes) -> None:
        auth_data: SessionAuthenticationPair = self.session.get(username)
        if not auth_data:
            raise UserAuthenticationError(f'No session for user {username} found')
        try:
            if compare_digest(auth_data.token, token):
                self.session.pop(username, None)
                return
            raise UserAuthenticationError('Invalid token')
        except Exception as e:
            #TODO: Add logging for hmac.compare_digest() exceptions
            raise UserAuthenticationError('Failed to log out (Possibly corrupted token)')

    def refresh_session():
        pass

    def ban():
        pass