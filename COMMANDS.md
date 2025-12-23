# Client Shell Command Reference

This document provides a formal reference for all commands supported by the `ClientWindow` interactive client shell and reflects the authoritative CLI interface.

---

## Table of Contents

1. General Notes  
2. Connection and Session Commands  
3. User Management Commands  
4. File Operations  
5. Permission and Ownership Commands  
6. Information and Query Commands  
7. Utility Commands  

---

## 1. General Notes

- Commands are executed within an interactive client shell.
- Many commands accept optional **modifiers** (for example, `--bye`, `--chunk-size`, `--post-keepalive`).
- Certain commands require an authenticated session.
- When `--bye` is specified, the server terminates the remote connection after the command completes.
- If a directory is not explicitly provided, it defaults to the authenticated user’s identity.

---

## 2. Connection and Session Commands

### 2.1 `HEARTBEAT`

HEARTBEAT [modifiers]


Send a heartbeat signal to the connected remote process.

Purpose: Maintain connection liveness

---

### 2.2 `AUTH`

AUTH [username] [password] [modifiers]


Start an authenticated remote session on the host machine.

Notes:
- Recommended authentication mechanism
- Prevents credentials from being written to shell history
- Initializes user-scoped defaults

Authentication State:
- Must NOT be authenticated

---

### 2.3 `STERM`

STERM [modifiers]


Terminate an established remote session.

Behavior:
- Terminates only the session by default
- Terminates both the session and connection if `--bye` is specified

Authentication State:
- Requires authentication

---

### 2.4 `SREF`

SREF [modifiers]


Refresh an established remote session.

Constraints:
- Cannot be combined with `--bye`

Authentication State:
- Requires authentication

---

### 2.5 `BYE`

BYE


Disconnect from the remote server and purge any active session.

Constraints:
- Accepts no arguments
- Always terminates the connection

---

## 3. User Management Commands

### 3.1 `UNEW`

UNEW [username] [password] [modifiers]


Create a new remote user.

Notes:
- Does not initiate a remote session

---

### 3.2 `UDEL`

UDEL [username] [password] [modifiers]


Delete an existing remote user.

Behavior:
- Clears local session data if the deleted user is currently authenticated

---

## 4. File Operations

### 4.1 `CREATE`

CREATE [filename] [modifiers]


Create a new file in the remote directory.

Requirements:
- Filename must include a file extension

Authentication State:
- Requires authentication

---

### 4.2 `DELETE`

DELETE [filename] [modifiers]


Delete a file from a remote directory.

Requirements:
- Filename must include a file extension

Authentication State:
- Requires authentication

---

### 4.3 `READ`

READ [filename] [directory] [--limit] [--chunk-size] [--pos] [--chunked] [--post-keepalive] [modifiers]


Read a file from a remote directory.

Capabilities:
- Chunked reads
- Cursor-based reads
- Optional read limits

Authentication State:
- Requires authentication

---

### 4.4 `REPLACE`

REPLACE [filename] [directory] [data] [--chunk-size] [--post-keepalive] [modifiers]


Write data to a file, replacing all existing contents.

Constraints:
- Write data must be provided
- Entire file is overwritten

Authentication State:
- Requires authentication

---

### 4.5 `PATCH`

PATCH [filename] [directory] [data] [--chunk-size] [--position] [--post-keepalive] [modifiers]


Write data to a file starting at a specific position.

Behavior:
- Overwrites existing content from the specified cursor position

Authentication State:
- Requires authentication

---

### 4.6 `APPEND`

APPEND [filename] [directory] [data] [--chunk-size] [--post-keepalive] [modifiers]


Append data to the end of a remote file.

Authentication State:
- Requires authentication

---

### 4.7 `UPLOAD`

UPLOAD [local_fpath] [--remote-filename] [--chunk-size] [--remote-fpath] [modifiers]


Upload a local file to a remote directory.

Authentication State:
- Requires authentication

---

### 4.8 `PATCHFROM`

PATCHFROM [local_fpath] [remote_filename] [remote_directory] [--chunk-size] [--position] [--post-keepalive] [modifiers]


Patch a remote file using data read from a local file.

Implementation Notes:
- Uses memory-mapped I/O for efficient file transfer

Authentication State:
- Requires authentication

---

### 4.9 `REPLACEFROM`

REPLACEFROM [local_fpath] [remote_filename] [remote_directory] [--chunk-size] [--post-keepalive] [modifiers]


Replace the contents of a remote file using data from a local file.

Authentication State:
- Requires authentication

---

## 5. Permission and Ownership Commands

### 5.1 `GRANT`

GRANT [filename] [directory] [user] [role] [--duration] [modifiers]


Grant a role to a user for a specific file.

Authentication State:
- Requires authentication

---

### 5.2 `REVOKE`

REVOKE [filename] [directory] [user] [modifiers]


Revoke a previously granted role from a user.

Authentication State:
- Requires authentication

---

### 5.3 `TRANSFER`

TRANSFER [filename] [directory] [user] [modifiers]


Transfer ownership of a file to another user.

Constraints:
- Must be executed by the current owner

Authentication State:
- Requires authentication

---

### 5.4 `PUBLICISE`

PUBLICISE [filename] [modifiers]


Make a file publicly readable.

Notes:
- Grants read access to all users
- Does not override existing permissions
- Applies only to files owned by the authenticated user

Authentication State:
- Requires authentication

---

### 5.5 `HIDE`

HIDE [filename] [modifiers]


Revoke public visibility of a previously publicised file.

Authentication State:
- Requires authentication

---

## 6. Information and Query Commands

### 6.1 `QUERY`

QUERY [query type] [resource name] [--verbose] [modifiers]


Query system or resource information.

Behavior:
- Some query types require a resource name
- `--verbose` enables extended output

---

## 7. Utility Commands

### 7.1 `CLEAR`

CLEAR

Clear the terminal screen.