import os
import asyncio
import re
import psycopg.errors as pg_errors
from datetime import datetime
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
from server.errors import UserAuthenticationError, DatabaseFailure, Banned

# TODO: Update SessionAuthenticationPair to include data like epoch to prevent frequent session refresh attempts
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

    def authenticate_session(self, username: str, token: bytes, raise_on_exc: bool = False) -> SessionAuthenticationPair:
        auth_pair: SessionAuthenticationPair = self.session.get(username)
        if not auth_pair:
            return
        try:
            if compare_digest(auth_pair.token, token):
                return auth_pair
        except Exception: 
            #TODO: Add logging for errors raised by hmac.compare_digest
            if raise_on_exc:
                raise UserAuthenticationError('Invalid authentication token. Please login again')

    async def authorize_session(self, username: str, password: str) -> SessionAuthenticationPair:
        if not (username:=SessionMaster.check_username_validity(username)):
            raise UserAuthenticationError('Invalid username')
        
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)
        try:
            # Check if user is banned
            if await self.check_banned(username, proxy):
                raise Banned(username)
            
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

    def refresh_session(self, username: str, token: bytes, digest: bytes) -> Optional[bytes]:
        auth_pair: SessionAuthenticationPair = self.authenticate_session(username, token)
        if not auth_pair:
            raise UserAuthenticationError('No such session exists')
        
        # session exists and token matches, proceed to check refresh digest
        try:
            if not compare_digest(auth_pair.refresh_digest, digest):
                raise UserAuthenticationError('Invalid refresh digest')
            
            new_digest: bytes = SessionMaster.generate_session_refresh_digest()
            # Optimistic check
            self.session.pop(username)
            set_pair: SessionAuthenticationPair = self.session.setdefault(username, SessionAuthenticationPair(token, new_digest))
            if not compare_digest(set_pair.refresh_digest, new_digest):
                raise UserAuthenticationError('Failed to reauthenticate session due to repeated request')
        except Exception as e:
            self.session.pop(username, None)    # Kill session on exceptions as well
            if isinstance(e, UserAuthenticationError):
                raise e
            # Generic handler for exceptions rising from hmac.compare_digest()
            raise UserAuthenticationError('Invalid session refresh digest. Please login again')
        
        return new_digest

    async def check_banned(self, username: str, proxy: Optional[ConnectionProxy] = None, reclaim_on_exc: bool = True, lock_row: bool = False) -> bool:
        new_proxy: bool = proxy is None
        if not proxy:
            proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)
        query: str = '''SELECT username
                        FROM ban_logs
                        WHERE username = %s AND lifted_at IS FALSE
                        LIMIT 1'''
        if lock_row:
            query += '\nFOR UPDATE NOWAIT'
        query += ';'
        
        try:
            async with proxy.cursor() as cursor:
                await cursor.execute(query, (username,))
                return bool(await cursor.fetchone())
        #TODO: Add exception logging
        except pg_errors.LockNotAvailable:
            return True
        except Exception as e:
            if reclaim_on_exc:
                self.connection_master.reclaim_connection(proxy)
            return True
        finally:
            if new_proxy:
                await self.connection_master.reclaim_connection(proxy)

    async def ban(self, username: str, ban_reason: str, ban_description: Optional[str] = None, *caches: TTLCache[str, dict[str, Union[AsyncBufferedIOBase, AsyncBufferedReader]]]) -> None:
        if not (username:=SessionMaster.check_username_validity(username)):
            raise UserAuthenticationError('Invalid username')
        
        proxy: ConnectionProxy = self.connection_master.request_connection(level=1)
        try:
            if await self.check_banned(username, proxy):
                #TODO: Add logging for duplicate ban attempts
                return
            
            async with proxy.cursor() as cursor:
                cursor.execute('''INSERT INTO ban_logs
                               VALUES (%s, %s, %s);''',
                               (username, ban_reason.strip(), ban_description.strip() if ban_description else None))
                proxy.commit()
        except pg_errors.Error:
            #TODO: Add logging here as well
            raise DatabaseFailure(f'Failed to ban user {username}')
        finally:
            await self.connection_master.reclaim_connection(proxy)

        # Once user is banned, terminate their session and any possible cache entries too
        self.session.pop(username, None)
        if caches:
            await self.terminate_user_cache(identifier=username, *caches)

    async def unban(self, username: str) -> None:
        if not (username:=SessionMaster.check_username_validity()):
            raise UserAuthenticationError('Invalid username')
        
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)
        try:
            if not await self.check_banned(username, proxy, lock_row=True):
                #TODO: Add logging for duplicate/invalid unban attempts
                return
            async with proxy.cursor() as cursor:
                await cursor.execute('''UPDATE ban_logs
                                     SET lifted_at = %s
                                     WHERE username = %s AND lifted_at is null;''',
                                     (datetime.now(), username,))
            await proxy.commit()
        finally:
            await self.connection_master.reclaim_connection(proxy)
