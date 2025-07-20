import os
import re
import time
from datetime import datetime
from secrets import token_hex
from hmac import compare_digest
from hashlib import pbkdf2_hmac
from typing import Optional, Union

import asyncio
from aiofiles.threadpool.binary import AsyncBufferedIOBase, AsyncBufferedReader

from cachetools import TTLCache

from models.constants import REQUEST_CONSTANTS
from models.session_metadata import SessionMetadata
from models.singletons import SingletonMetaclass

import psycopg.errors as pg_errors
from psycopg.rows import Row

from server.connectionpool import ConnectionProxy, ConnectionPoolManager
from server.database.models import ActivityLog, LogAuthor, Severity, LogType
from server.errors import UserAuthenticationError, DatabaseFailure, Banned, InvalidAuthData, OperationContested

class UserManager(metaclass=SingletonMetaclass):
    '''Class for managing user sessions and user-related operations'''
    HASHING_ALGORITHM: str = 'sha256'
    PBKDF_ITERATIONS: int = 100_000
    SALT_LENGTH: int = 16
    USERNAME_REGEX: str = REQUEST_CONSTANTS.auth.username_regex
    TOKEN_LENGTH: int = REQUEST_CONSTANTS.auth.token_length
    DIGEST_LENGTH: int = REQUEST_CONSTANTS.auth.digest_length
    LOG_ALIAS: str = LogAuthor.USER_MASTER.value
    LOG_TIMEOUT: float = 2.0

    def __init__(self, connection_master: ConnectionPoolManager, log_queue: asyncio.PriorityQueue[ActivityLog], session_lifespan: float):
        self.connection_master: ConnectionPoolManager = connection_master
        self.session: dict[str, SessionMetadata] = {}
        self._log_queue: asyncio.PriorityQueue[ActivityLog] = log_queue
        self.session_lifespan = session_lifespan
        self.session_refresh_nbf = session_lifespan // 2
        self.previous_digests_mapping: TTLCache[str, list[bytes, bytes]] = TTLCache(0, self.session_lifespan)

        asyncio.create_task(self.expire_sessions(), name='Session Trimming Task')
    
    @staticmethod
    def generate_password_hash(password: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes]:
        password = password.strip()
        if not salt:
            salt: bytes = os.urandom(UserManager.SALT_LENGTH)
        return pbkdf2_hmac(UserManager.HASHING_ALGORITHM, password.encode('utf-8'), salt, iterations=UserManager.PBKDF_ITERATIONS), salt
    
    @staticmethod
    def verify_password_hash(password: str, password_hash: bytes, salt: bytes) -> bool:
        try:
            return compare_digest(
                pbkdf2_hmac(UserManager.HASHING_ALGORITHM, password.encode('utf-8'), salt, iterations=UserManager.PBKDF_ITERATIONS),
                password_hash)
        except:
            return False
    
    @staticmethod
    def check_username_validity(username: str) -> str:
        username = username.strip()
        if not re.match(UserManager.USERNAME_REGEX, username):
            return None
        return username

    # Token and refresh digest generation logic kept as static methods in case we ever need to add any more logic to it
    @staticmethod
    def generate_session_token() -> bytes:
        return token_hex(UserManager.TOKEN_LENGTH // 2).encode('utf-8')
    
    @staticmethod
    def generate_session_refresh_digest() -> bytes:
        return token_hex(UserManager.DIGEST_LENGTH // 2).encode('utf-8')

    async def authenticate_session(self, username: str, token: bytes, raise_on_exc: bool = False) -> Optional[SessionMetadata]:
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
            await self.enqueue_activity(ActivityLog(severity=Severity.ERROR,
                                                    log_details=f'Failed in digest comparison: {e.__class__.__name__}',
                                                    user_concerned=username,
                                                    log_category=LogType.USER.value))
            if raise_on_exc:
                raise UserAuthenticationError('Invalid authentication token. Please login again')

    async def authorize_session(self, username: str, password: str) -> SessionMetadata:
        if not (username:=UserManager.check_username_validity(username)):
            raise UserAuthenticationError('Invalid username')
        
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)
        try:
            # Check if user is banned
            if await self.check_banned(username, proxy):
                raise Banned(username)
            
            async with proxy.cursor() as cursor:
                await cursor.execute('''SELECT password_hash, password_salt
                                     FROM users
                                     WHERE username = %s;''',
                                     (username,))
                pw_data: tuple[memoryview, memoryview] = await cursor.fetchone()
        finally:
            await self.connection_master.reclaim_connection(proxy)

        if not pw_data:
            raise UserAuthenticationError(f'No username with {username} exists')
 
        if not UserManager.verify_password_hash(password, *pw_data):
            await self.enqueue_activity(ActivityLog(severity=Severity.ERROR,
                                                    log_details=f'Incorrect password: {UserAuthenticationError.__name__}',
                                                    user_concerned=username,
                                                    log_category=LogType.USER.value))
            
            raise UserAuthenticationError(f'Invalid password for user {username}')
                
        # Set new session
        auth_data: SessionMetadata = SessionMetadata(UserManager.generate_session_token(), UserManager.generate_session_refresh_digest(), lifespan=self.session_lifespan)
        self.session[username] = auth_data

        return auth_data
        
    async def create_user(self, username: str, password: str, root: str, make_dir: bool = False) -> None:
        if not (username:=UserManager.check_username_validity(username)):
            raise UserAuthenticationError('Invalid username')
        
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)   # Account creation is high-priority
        try:
            async with proxy.cursor() as cursor:
                await cursor.execute('''SELECT username FROM users WHERE username = %s''', (username,))
                res: tuple[str] = await cursor.fetchone()
                if res:
                    raise UserAuthenticationError(f'Local user {res[0]} already exists')
                
                pw_hash, pw_salt = UserManager.generate_password_hash(password)
        
                await cursor.execute('''INSERT INTO users (username, password_hash, password_salt) VALUES (%s, %s, %s)''',
                                     (username, pw_hash, pw_salt,))
                await proxy.commit()
        finally:
            await self.connection_master.reclaim_connection(proxy)    # Always return leased connection to connection master

        if make_dir:
            os.makedirs(os.path.join(root, username))

    async def delete_user(self, username: str, password: str, *caches) -> None:
        if not (username:=UserManager.check_username_validity(username)):
            raise UserAuthenticationError('Invalid username')

        proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)   # Action concerning account statuses have highest priority
        try:
            async with proxy.cursor() as cursor:
                await cursor.execute('''SELECT password_hash, password_salt
                                     FROM users
                                     WHERE users.username = %s
                                     FOR UPDATE NOWAIT READ;''',
                                     (username,))
                pw_data: tuple[memoryview, memoryview] = await cursor.fetchone()
                if not pw_data:
                    raise UserAuthenticationError(f'No username with {username} exists')
                
                if not UserManager.verify_password_hash(password, *pw_data):
                    raise UserAuthenticationError(f'Invalid password for user {username}')
                
                # All checks passed
                await cursor.execute('''DELETE FROM users
                                     WHERE username = %s;''',
                                     (username,))
        finally:
            await self.connection_master.reclaim_connection(proxy)

        # User deleted, delete session
        self.session.pop(username, None)
        self.previous_digests_mapping.pop(username, None)
        # Perform relatively less important task of trimming the cache preemptive to usual expiry of this user's buffered readers/writers
        if caches:
            asyncio.create_task(self.terminate_user_cache(identifier=str, *caches))

    async def change_password(self, username: str, new_password: str) -> None:
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=3)
        try:
            async with proxy.cursor() as cursor:
                await cursor.execute('''SELECT password_hash, password_salt
                                        FROM users
                                        WHERE username = %s
                                        FOR UPDATE NOWAIT;''',
                                        (username,))
                pw_data: Row[bytes, bytes] = await cursor.fetchone()    # record will always exist if authentication was passed

                if UserManager.verify_password_hash(new_password, *pw_data):  # Same password as before
                    raise InvalidAuthData('Password cannot be same as previous password')
                pw_hash, pw_salt = UserManager.generate_password_hash(new_password)
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

    def terminate_session(self, username: str, token: bytes) -> SessionMetadata:
        auth_data: SessionMetadata = self.session.get(username)
        if not auth_data:
            raise UserAuthenticationError(f'No session for user {username} found')
        try:
            if compare_digest(auth_data.token, token):
                self.session.pop(username, None)
                self.previous_digests.pop(username, None)
                return auth_data
            
            raise UserAuthenticationError('Invalid token')
        except Exception as e:
            self.enqueue_activity(ActivityLog(user_concerned=username,
                                              severity=Severity.ERROR,
                                              log_details=f'Failed in digest comparison: {e.__class__.__name__}',
                                              log_category=LogType.USER.value))
            raise UserAuthenticationError('Failed to log out (Possibly corrupted token)')

    async def refresh_session(self, username: str, token: bytes, digest: bytes) -> tuple[bytes, int]:
        auth_data: SessionMetadata = self.authenticate_session(username, token)
        if not auth_data:
            raise UserAuthenticationError('No such session exists')
        
        if time.time() < auth_data.last_refresh + self.session_refresh_nbf:    # Premature refresh attempt
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
            
            new_digest: bytes = UserManager.generate_session_refresh_digest()
            # Optimistic check
            self.session.pop(username, None)
            set_pair: SessionMetadata = self.session.setdefault(username, SessionMetadata(token, new_digest, lifespan=self.session_lifespan))
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
            await self.enqueue_activity(ActivityLog(user_concerned=username,
                                                    severity=Severity.ERROR,
                                                    log_details=f'Failed to refresh session: {e.__class__.__name__}',
                                                    log_category=LogType.USER.value if isinstance(e, UserAuthenticationError) else 'session'))
            if isinstance(e, UserAuthenticationError):
                raise e
            # Generic handler for exceptions rising from hmac.compare_digest()
            raise UserAuthenticationError('Invalid session refresh digest. Please login again')
        auth_data.update_digest(new_digest)
        self.session[username] = auth_data

        return new_digest, auth_data.iteration

    async def check_banned(self, username: str, proxy: Optional[ConnectionProxy] = None, reclaim_on_exc: bool = True, lock_row: bool = False) -> bool:
        new_proxy: bool = proxy is None
        if not proxy:
            proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)
        query: str = '''SELECT username
                        FROM ban_logs
                        WHERE username = %s AND lifted_at IS NOT NULL and lifted_at < %s
                        ORDER BY lifted_at DESC
                        LIMIT 1'''
        if lock_row:
            query += '\nFOR UPDATE NOWAIT'
        query += ';'
        
        try:
            async with proxy.cursor() as cursor:
                await cursor.execute(query, (username, datetime.now()))
                return bool(await cursor.fetchone())
        except pg_errors.LockNotAvailable:
            return True
        except Exception as e:
            await self.enqueue_activity(ActivityLog(user_concerned=username,
                                                    severity=Severity.NON_CRITICAL_FAILURE,
                                                    log_details=f'Failed in check ban status: {e.__class__.__name__}',
                                                    log_category=LogType.DATABASE.value))
            if reclaim_on_exc:
                self.connection_master.reclaim_connection(proxy)
            return True
        finally:
            if new_proxy:
                await self.connection_master.reclaim_connection(proxy)

    async def ban(self, username: str, ban_reason: str, ban_description: Optional[str] = None, *caches: TTLCache[str, dict[str, Union[AsyncBufferedIOBase, AsyncBufferedReader]]]) -> None:
        if not (username:=UserManager.check_username_validity(username)):
            raise UserAuthenticationError('Invalid username')
        
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)
        try:
            if await self.check_banned(username, proxy):
                await self.enqueue_activity(ActivityLog(user_concerned=username,
                                                        severity=Severity.NON_CRITICAL_FAILURE,
                                                        log_details=f'Duplicate ban attempt: {DatabaseFailure.__name__}',
                                                        log_category=LogType.USER.value))
                return
            
            async with proxy.cursor() as cursor:
                await cursor.execute('''INSERT INTO ban_logs
                               VALUES (%s, %s, %s);''',
                               (username, ban_reason.strip(), ban_description.strip() if ban_description else None))
                await proxy.commit()
        except pg_errors.Error as e:
            await self.enqueue_activity(ActivityLog(user_concerned=username,
                                                    severity=Severity.CRITICAL_FAILURE,
                                                    log_details=f'Failed to ban user: {e.__name__}',
                                                    log_category=LogType.DATABASE.value))
            
            raise DatabaseFailure(f'Failed to ban user {username}')
        finally:
            await self.connection_master.reclaim_connection(proxy)

        # Once user is banned, terminate their session and any possible cache entries too
        self.session.pop(username, None)
        self.previous_digests.pop(username, None)
        if caches:
            asyncio.create_task(self.terminate_user_cache(identifier=str, *caches))

    async def unban(self, username: str) -> None:
        if not (username:=UserManager.check_username_validity(username)):
            raise UserAuthenticationError('Invalid username')
        
        proxy: ConnectionProxy = await self.connection_master.request_connection(level=1)
        try:
            if not await self.check_banned(username, proxy, lock_row=True):
                await self.enqueue_activity(ActivityLog(user_concerned=username,
                                                        severity=Severity.NON_CRITICAL_FAILURE,
                                                        log_details=f'Duplicate unban attempt: {DatabaseFailure.__name__}',
                                                        log_category=LogType.USER.value))
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
        sleep_duration: float = self.session_lifespan // 3
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

    async def enqueue_activity(self, log: ActivityLog) -> None:
        log.logged_by = UserManager.LOG_ALIAS
        await asyncio.wait_for(self._log_queue.put(log), timeout=UserManager.LOG_TIMEOUT)