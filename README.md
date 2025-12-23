# Overview

FIP (File Interaction Protocol) is an application-layer protocol designed for file I/O on a client-server architecture. I've developed this protocol as a way to practice sockets, asynchronous programming, and relatively lower-level Python in general. This protocol is in no way a new alternative to any existing protocol, but an attempt to increase my understanding of networking and asynchronous programming.

FIP is stateless, and segments its data using components, which act as the PDU throughout this protocol. These components follow different semantic and contain widely varying amounts of information, hence their sizes are specified in advance through fixed-length headers of 256 bytes (as of the current version). For serialization, I have resorted to using JSON.

The project is divided into 3 packages:
* **client**: Client-side logic for connecting to and interacting with a server running the protocol
* **server**: Server-side logic for creating a FIP listener on a port and allowing client interactions
* **models**: Common constants, enums, and classes used by both client and server packages

## Server:
The server is responsible for handling incoming TCP connections using `asyncio`'s TCP server functionality. The server is assosciated with a client connection callback coroutine, which is designed as an indefinite loop to allow for continuous 2-way communication until either the server shuts down, the connection times out, or, most commonly, the client terminates the connection.

Each connection is peer-to-peer, and encrypted using TLS through a TOFU (Trust On First Use) policy, similar to SSH. This policy is also capable of handling rotating certificates from the server, allowing clients to connect to a trusted server after a significantly long time as long as the server persists its previous certificates.

**Functionalities**:
* **User session management**: Through the `UserManager` class, the server is able to perform authorization and authenticate requests on privileged operations. By nature of being stateless, the authentication mechanism follows a policy mimicing JWTs, with tokens acting as access tokens and refresh digests acting as refresh tokens. Reauthentication is further protected by replay-attack detection, which does introduce state but allows for much higher robustness against malicious actors. The server is also capable of banning users entirely.
* **Access Control**: Through `PERMISSION` operations, users can manually handle privileges on their files, such as read-only, editable, and manageable (allowing other users read and edit access). Files can also be publicised to allow read access to all users on the server. 
* **Metadata**: Through `INFO` operations, users can essentially query metadata about their usage on the server, such as how much storage they have left, how many files they have created, as well as more granular queries such as the permissions granted on a specified file.
* **Asynchronous**: All server methods are written asynchronously, using standard `asyncio`, and `psycopg3` for low-level, async control over a Postgres database. Given the I/O driven nature of this project (Networking+Database+File I/O), Python's async model allows for a very high degree of concurrency among multiple clients
* **Event-Driven**: Database writes assosciated with logging and cache syncing are performed in batches to minimize DB round trips, with retry mechanisms in place. Furthermore, to increase reliability even further, periodic flushes are abandoned for urgent, complete flushes to DB in case the server indicates a shutdown
* **Coordination**: As mentioned earlier, different background tasks coordinate with each other and with the server itself, in case of a shutdown. In such a case, all background tasks shift to a 'cleanup' mode where necessary state data is flushed to disk before the Python process is actually closed
* **Caching**: The server extensively utilises caching to speed up user lookups, file metadata lookups (storage), as well as for avoiding redundant file opening and closing by storing file buffers in memory per user.
* **Logging**: Suspicious activities, failed operations, and traces are logged continuously for analysis and debugging through a central logging mechanism

## Client:
The client-side code exposes a shell with a vast set of commands and flags to interact with the server, perform file operations, manage permissions, and handle user accounts.

**Functionalities**

* **File I/O**: Clients can perform CRUD operations on a file, through commands such as `CREATE`, `READ`, `PATCH`, `PATCHFROM` ,`APPEND`, `WRITE`, `REPLACE`, `REPLACEFROM`, and `DELETE`. These operations allow the client to also upload local files to the server (given their storage is sufficient), as well as update existing files with data from local files. This makes FIP act as a distributed file system to an extent.
* **Permissions**: As mentioned earlier in server functionalities, clients can handle permissions on a file through their shells to allow collaboration and finer access control
* **Auth**: The client shell provides an easy way to register (`UNEW`), delete (`UDEL`), and login (`AUTH`) to their accounts.


## Usage
### Server
To run the server, run:
```bash
python -m server <port>
```

### Client
To run the client, run:
```bash
python -m client <host> <port> [--blind-trust | --username | --password]
```
Specifying username and password in the command line itself is not recommended, since the client shell itself provides a way for authorization through the `AUTH` command without leaving credentials in command history.

The `--blind-trust` flag makes the client TLS TOFU handshake logic ignore any mismatches in server credentials, and must only be used when there is absolute trust in the network and the process claiming to be the server.

Once the client shell has been activated, the server can be interacted with through the defined commands.

To exit, run:
```shell
BYE
```

To simply end the user session without terminating the connection, run:
```shell
STERM
```

Finally, to run a protocol command and exit immediately afterwards, run:
```shell
<COMMAND> -bye
```
Examples:
```shell
UNEW foobar_user foobar_password -bye
```
```shell
CREATE myfile.txt -bye
```
```shell
GRANT foobar_user myfile READ -bye
```
Note that command names and flags are caps insensitive, but data is treated as caps sensitive.

**Consult the command documentation for a full list of shell commands and their flags**