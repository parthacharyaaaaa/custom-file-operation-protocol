# Server Package
This package holds the logic for the server side of the protocol.

## Sub-Packages
* **authz**: User management (authorization, authentication, session management)
* **file_ops**: CRUD operations on files, as well as caching
* **info_ops**: Info operations (file metadata, storage metadata, permission metadata, etc.)
* **permission_ops**: Granting/Revoking of permissions on files
* **database**: Internal logic for persistant state management
* **config**: Holds constants used hy the server
* **comms_utils**: Helper methods for incoming and outgoing data streams
* **process**: Server lifecycle management
* **tls**: SSL functionality

## Global Singletons
* **UserManager**: Responsible for authentication and authorizing user requests, and managing user sessions. It is used ubiquitously throughout the package to validate any request that involves a priviliged operation, such as accessing a file or managing permissions. `UserManager` is also capable of banning and unbanning suspicious users, and handling registration and deletion of user accounts.
* **ConnectionPoolManager**: Handles 3 pools of varying priorities of Postgres connections, and serves as the sole authority for granting database access to server methods. It leases connections guarded through a `ConnectionProxy` instance which only allows a fixed set of operations to be performed, such as the cursor factory method and the commit method to persist changes. The leased connections are also timed and signed, making them temporary leases usable only by the method responsible for requesting the connection. Expired `ConnectionProxies` do not allow access to their underlying Postgres connection. The priority of each connection is defined in the `request_connection` method through the `ConnectionPriority` enum (defaults to `LOW`)
* **StorageCache**: Subclass of `OrderedDict` which acts as a cache layer on top of the database. `StorageCache` holds information about user storage and individual file data, which is updated in-memory through file operations. This allwos for quick lookups of storage limits per user on operations like file amendments and file creations. These changes are periodically persisted to disk, and flushed all at once if the server indicates that it is shutting down. This latter detail, in particular, helps in maintaing state even in the case of server failure (unless, of course, the failure involved the database itself).
* **Logger**: Acts as a consumer of an asyncio queue of log entries produced by different server methods and objects. These logs are encapsulated in the `ActivityLog` class, and periodically flushed into the database as low-priority writes. Similar to `StorageCache`, the `Logger` instance will also flush all of its queued logs at once when the server indicates a shutdown event.
* **ServerConfig**: Model to allow easier and safer access to server configurations and constants.
* **Caches**: For a file I/O oriented protocol, constant disk operations for a file are expensive. The server therefore uses `cachetools` to maintain read and amendment caches of files. These caches contain mappings of the user currently accessing a file and the in-memory buffer (`AsyncBufferedReader`, `AsyncBufferedIOBase`) through which file access is being done. This prevents constant `open` and `close` calls to files. Furthermore, a `deleted` cache is also maintained for early failures on operations involving a recently deleted file.

## Top level modules
* `bootup.py`: Utility methods for initialization of singletons such as `UserManager` and `ConnectionPoolManager`.
* `callback.py`: Callback function invoked upon client connection, runs in a loop until client times out and requests disconnection. This function is responsible for dispatching requests to their handlers, dispatching responses, and catching and handling any `ProtocolException` raised by the server.
* `dependencies.py`: Defines a `ServerSingletonsRegistry` to allow for dependency injection into different request handler methods based on their signatures. Greatly helps in avoiding circular dependencies and partial imports caused by globally defined singleton instances.
* `dispatch.py`: Defines immutable mappings to map each request category to it's top-level handler function, as well as subcategory flags to their dedicated subhandler methods.
* `errors.py`: Defines the different exceptions that the server can raise. Each exception is assosciated with a response code sourced from `models.response_codes`.
* `logging.py`: Defines a `Logger` singleton class for, well, logging.
* `typing.py`: Server-specific typing stubs and aliases