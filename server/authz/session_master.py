import os
import asyncio
import re
import psycopg.errors as pg_errors
from psycopg.rows import Row
import psycopg.sql as sql
import time
from datetime import datetime
from secrets import token_bytes
from hmac import compare_digest
from hashlib import pbkdf2_hmac
from typing import Optional, Union, Any
from cachetools import TTLCache
from aiofiles.threadpool.binary import AsyncBufferedIOBase, AsyncBufferedReader
from server.authz.singleton import MetaSessionMaster
from server.bootup import connection_master
from server.connectionpool import ConnectionProxy, ConnectionPoolManager
from server.database.models import ActivityLog
from server.config import ServerConfig
from server.errors import UserAuthenticationError, DatabaseFailure, Banned, InvalidAuthData, OperationContested

class SessionMetadata:
    __slots__ = '_token', '_refresh_digest', '_last_refresh', '_iteration', '_lifespan'
    # Cryptograhic metadata
    _token: bytes
    _refresh_digest: bytes

    # Chronologic metadata
    _last_refresh: float
    _lifespan: float

    # Additional
    _iteration: int

    @property
    def token(self) -> bytes:
        return self._token
    @property
    def refresh_digest(self) -> bytes:
        return self._refresh_digest
    @property
    def last_refresh(self) -> float:
        return self._last_refresh
    @property
    def iteration(self) -> int:
        return self._iteration
    @property
    def lifespan(self) -> float:
        return self._lifespan

    def __init__(self, token: bytes, refresh_digest: bytes, lifespan: float):
        self._token = token
        self._refresh_digest = refresh_digest
        self._last_refresh = time.time()
        self._lifespan = lifespan
        self._iteration = 1
    
    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.token}, {self.refresh_digest}, {self.lifespan}) at location {id(self)}>'
    
    def update_digest(self, new_digest: bytes) -> None:
        self._refresh_digest = new_digest
        self._last_refresh = time.time()
        self.valid_until = self._last_refresh + self.lifespan
        self._iteration+=1

    def get_validity(self) -> float:
        return self.last_refresh + self.lifespan

class SessionMaster(metaclass=MetaSessionMaster):
    '''Class for managing user sessions'''
    HASHING_ALGORITHM: str = 'sha256'
    PBKDF_ITERATIONS: int = 100_000
    SALT_LENGTH: int = 16
    USERNAME_REGEX: str = ServerConfig.USERNAME_REGEX.value
    TOKEN_LENGTH: int = 32
    REFRESH_DIGEST_LENGTH: int = 128
    SESSION_LIFESPAN: float = ServerConfig.SESSION_LIFESPAN.value
    SESSION_REFRESH_NBF: float = ServerConfig.SESSION_LIFESPAN.value * 0.5
    LOG_DUMP_INTERVAL: float = 180
    LOG_ALIAS: str = 'session_master'

    # Prepare query at runtime whenever this class is read
    LOG_INSERTION_SQL: sql.SQL = (sql.SQL('''INSEERT INTO {tablename} ({columns_template})
                                         VALUES ({placeholder_template});''')
                                         .format(tablename=sql.Identifier('activity_logs'),
                                                 columns_template=sql.SQL(', ').join([sql.Identifier(key) for key in list(ActivityLog.model_fields.keys())]),
                                                 placeholder_template=sql.SQL(', ').join(['%s' for _ in range(len(ActivityLog.model_fields))])))
    def __init__(self):
        self.connection_master: ConnectionPoolManager = connection_master
        self.session: dict[str, SessionMetadata] = {}
        self.previous_digests_mapping: TTLCache[str, list[bytes, bytes]] = TTLCache(0, SessionMaster.SESSION_LIFESPAN)
        self.activity_logs: list[dict[str, Any]] = []

        asyncio.create_task(self.expire_sessions(), name='Session Trimming Task')
        asyncio.create_task(self.log_activity(), name='Session Logging Task')

    @classmethod
    def construct_logging_map(cls, **kwargs) -> dict[str, Any]:
        try:
            activity_log: ActivityLog = ActivityLog(**(kwargs | {'logged_by' : cls.LOG_ALIAS})) # Inject/override logged_by field with alias
            return activity_log.model_dump()
        except Exception as e:
            # Log exception in a safe manner as an internal error
            activity_log: ActivityLog = ActivityLog(severity=3, logged_by=cls.LOG_ALIAS, log_type='internal', log_details=e.__class__.__name__)
            return activity_log.model_dump()

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

    def authenticate_session(self, username: str, token: bytes, raise_on_exc: bool = False) -> Optional[SessionMetadata]:
        auth_data: SessionMetadata = self.session.get(username)
        if not auth_data:
            return
        if (auth_data.get_validity() < time.time()):   # Expired session
            self.session.pop(username, None)
            raise UserAuthenticationError('Session expired, please authorize again')
        try:
            if compare_digest(auth_data.token, token):
                return auth_data
        except Exception as e:
            self.enqueue_activity(user_concerned=username, severity=3, log_details=f'Failed in digest comparison: {e.__class__.__name__}', log_type='user')
            if raise_on_exc:
                raise UserAuthenticationError('Invalid authentication token. Please login again')

    async def authorize_session(self, username: str, password: str) -> SessionMetadata:
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
            self.enqueue_activity(user_concerned=username, severity=4, log_details=f'Incorrect password: {UserAuthenticationError.__name__}', log_type='user')
            raise UserAuthenticationError(f'Invalid password for user {username}')
                
        # Set new session
        auth_data: SessionMetadata = SessionMetadata(SessionMaster.generate_session_token(), SessionMaster.generate_session_refresh_digest())
        #NOTE+TODO: Important design decision here: Should a new login for an exisitng session be rejected, or the session be overwritten and the old user be logged out?
        self.session[username] = auth_data

        return auth_data
        
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

        # User deleted, delete session
        self.session.pop(username, None)
        # Perform relatively less important task of trimming the cache preemptive to usual expiry of this user's buffered readers/writers
        if caches:
            asyncio.create_task(self.terminate_user_cache(identifier=str, *caches))

    async def change_password(self, username: str, new_password: str) -> None:
        proxy: ConnectionProxy = await connection_master.request_connection(level=3)
        try:
            async with proxy.cursor() as cursor:
                await cursor.execute('''SELECT pw_hash, pw_salt
                                        FROM users
                                        WHERE username = %s
                                        FOR UPDATE NOWAIT;''',
                                        (username,))
                pw_data: Row[bytes, bytes] = await cursor.fetchone()    # record will always exist if authentication was passed

                if SessionMaster.verify_password_hash(new_password, *pw_data):  # Same password as before
                    raise InvalidAuthData('Password cannot be same as previous password')
                pw_hash, pw_salt = SessionMaster.generate_password_hash(new_password)
                await cursor.execute('''UPDATE users
                                        SET pw_hash = %s, pw_salt = %s
                                        WHERE username = %s''',
                                        (pw_hash, pw_salt, username,))
                await proxy.commit()
        except pg_errors.Error as e:
            if isinstance(e, pg_errors.LockNotAvailable):
                raise OperationContested
            raise DatabaseFailure('Failed to perform password updation. Please try again')
        finally:
            await self.connection_master.reclaim_connection(proxy)

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
        auth_data: SessionMetadata = self.session.get(username)
        if not auth_data:
            raise UserAuthenticationError(f'No session for user {username} found')
        try:
            if compare_digest(auth_data.token, token):
                self.session.pop(username, None)
                self.previous_digests.pop(username, None)
                return
            raise UserAuthenticationError('Invalid token')
        except Exception as e:
            self.enqueue_activity(user_concerned=username, severity=3, log_details=f'Failed in digest comparison: {e.__class__.__name__}', log_type='user')
            raise UserAuthenticationError('Failed to log out (Possibly corrupted token)')

    def refresh_session(self, username: str, token: bytes, digest: bytes) -> Optional[bytes]:
        auth_data: SessionMetadata = self.authenticate_session(username, token)
        if not auth_data:
            raise UserAuthenticationError('No such session exists')
        
        if time.time() < auth_data.last_refresh + SessionMaster.SESSION_REFRESH_NBF:    # Premature refresh attempt
            raise UserAuthenticationError('Session not old enough to refresh yet')
        
        # session exists, token matches, and refresh attempt is mature. Proceed to check refresh digest
        try:
            # Check expired digests, if match then treat as replay attack
            previous_digests: list[bytes] = self.previous_digests_mapping.get(username, [])
            if any(compare_digest(previous_digest, digest) for previous_digest in previous_digests):
                self.session.pop(username, None)
                self.previous_digests_mapping.pop(username, None)
                asyncio.create_task(self.terminate_user_cache(username))
                raise UserAuthenticationError('Expired digest provided. Please authenticate again')
            
            if not compare_digest(auth_data.refresh_digest, digest):
                raise UserAuthenticationError('Invalid refresh digest')
            
            new_digest: bytes = SessionMaster.generate_session_refresh_digest()
            # Optimistic check
            self.session.pop(username, None)
            set_pair: SessionMetadata = self.session.setdefault(username, SessionMetadata(token, new_digest))
            if not compare_digest(set_pair.refresh_digest, new_digest):
                raise UserAuthenticationError('Failed to reauthenticate session due to repeated request')
            
            # New token set, update previous digests for this user
            previous_digests.append(auth_data.refresh_digest)
            # Remove oldest digest if list size over 2
            if len(previous_digests > 2):
                previous_digests.pop(0)
            
            self.previous_digests[username] = previous_digests

        except Exception as e:
            self.session.pop(username, None)
            self.previous_digests_mapping.pop(username, None)
            self.enqueue_activity(user_concerned=username, severity=3,
                                  log_details=f'Failed to refresh session: {e.__class__.__name__}',
                                  log_type='user' if isinstance(e, UserAuthenticationError) else 'session')
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
        except pg_errors.LockNotAvailable:
            return True
        except Exception as e:
            self.enqueue_activity(user_concerned=username, severity=2, log_details=f'Failed in check ban status: {e.__class__.__name__}', log_type='database')
            if reclaim_on_exc:
                self.connection_master.reclaim_connection(proxy)
            return True
        finally:
            if new_proxy:
                await self.connection_master.reclaim_connection(proxy)

    async def ban(self, username: str, ban_reason: str, ban_description: Optional[str] = None, *caches: TTLCache[str, dict[str, Union[AsyncBufferedIOBase, AsyncBufferedReader]]]) -> None:
        if not (username:=SessionMaster.check_username_validity(username)):
            raise UserAuthenticationError('Invalid username')
        
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)
        try:
            if await self.check_banned(username, proxy):
                self.enqueue_activity(user_concerned=username, severity=3, log_details=f'Duplicate ban attempt: {DatabaseFailure.__name__}', log_type='user')
                return
            
            async with proxy.cursor() as cursor:
                await cursor.execute('''INSERT INTO ban_logs
                               VALUES (%s, %s, %s);''',
                               (username, ban_reason.strip(), ban_description.strip() if ban_description else None))
                await proxy.commit()
        except pg_errors.Error as e:
            self.enqueue_activity(user_concerned=username, severity=5, log_details=f'Failed ban attempt: {e.__name__}', log_type='database')
            raise DatabaseFailure(f'Failed to ban user {username}')
        finally:
            await self.connection_master.reclaim_connection(proxy)

        # Once user is banned, terminate their session and any possible cache entries too
        self.session.pop(username, None)
        self.previous_digests.pop(username, None)
        if caches:
            asyncio.create_task(self.terminate_user_cache(identifier=str, *caches))

    async def unban(self, username: str) -> None:
        if not (username:=SessionMaster.check_username_validity(username)):
            raise UserAuthenticationError('Invalid username')
        
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)
        try:
            if not await self.check_banned(username, proxy, lock_row=True):
                self.enqueue_activity(user_concerned=username, log_type='user', log_details='Duplicate unban attempt', severity=1)
                return
            async with proxy.cursor() as cursor:
                await cursor.execute('''UPDATE ban_logs
                                     SET lifted_at = %s
                                     WHERE username = %s AND lifted_at is null;''',
                                     (datetime.now(), username,))
            await proxy.commit()
        finally:
            await self.connection_master.reclaim_connection(proxy)

    async def expire_sessions(self) -> None:
        sleep_duration: float = SessionMaster.SESSION_LIFESPAN // 3
        while True:
            reference_threshold: float = time.time()
            hitlist: list[str] = []
            for username, auth_data in self.session.items():
                if auth_data.get_validity() < reference_threshold:
                    hitlist.append(username)  
            for user in hitlist:
                self.session.pop(user, None)
                self.previous_digests_mapping.pop(user, None)
            await asyncio.sleep(sleep_duration)

    def enqueue_activity(self, **kwargs) -> None:
        self.activity_logs.append(SessionMaster.construct_logging_map(**kwargs))

    async def log_activity(self) -> None:
        # Atomically copy and clear activity logs
        pending_logs: list[dict[str, Any]] = self.activity_logs[:]
        self.activity_logs.clear()

        while True:
            proxy: ConnectionProxy = await self.connection_master.request_connection(level=2)
            try:
                async with proxy.cursor() as cursor:
                    # SQL would have the correctly ordered column names as log entries, since both come from ActivityLog.model_fields.keys()
                    await cursor.executemany(SessionMaster.LOG_INSERTION_SQL, params_seq=[list(pending_log.values()) for pending_log in pending_logs])
                await proxy.commit()
            finally:
                await self.connection_master.reclaim_connection(proxy)
            await asyncio.sleep(SessionMaster.LOG_DUMP_INTERVAL)
