# Protocol Models
The `models` package acts as a flat, top-level package for defining common enums, classes, stubs, and constants used at both client and server sides.

## Usage
---
Accessing the model definitions in the package is quite straightforward. The `__init__.py` file loads the constant values from the `constants.toml` config file upon package initialization, hence any module/package can import and use the contents of `models` without any manual loading of settings or constant values.

## Modules
---

#### Constants
* `constants.py`: Defines the different constants agreed upon between client and server. These constants are divided into separate `pydantic.BaseModel` child classes based on which component and which side of the communication they relate to (example: `FileRequestConstants`, `HeaderResponseConstants`). Two classes, namely `RequestConstants` and `ResponseConstants` are defined which group different components together to provide a complete semantic view of the different constants present in reqeuests and responses. These classes are instantiated once with the package (using `constants.toml`) and treated as immutable global singletons.

#### Enums
* `cursor_flag.py`: Holds a single enum to show different bits that the `cursor_bitfield` of `BaseFileComponent` can hold, along with a mask to include all cursor bits

* `flags.py`: Holds the int flag values to signal different types of operations (`CategoryFlags`) and sub-operations (`AuthFlags`, `InfoFlags`, `PermissionFlags`, `FileFlags`), used in request headers.

* `permissions.py`: Includes enums for different roles a user can assume for a file (such as `OWNER`, `MANAGER`, and `READER`), the permissions that each respective role can enjoy (`WRITE`, `READ`, `MANAGE_RW`), and a mapping to relate each role to its permissions.

* `response_codes.py`: Defines the different categories of responses a server can emit (Success, Client Failure, Server Failure)

#### Models
* `request_model.py`: Defines the schema for request components, namely `BaseAuthComponent`, `BaseFileComponent`, `BasePermissionComponent`, `BaseInfoComponent`, and `BaseHeaderComponent`. Each component defines the different fields it contains, and their constraints (mandatory, ranged, restricted to an enum, etc.)

* `response_model.py`: Defines the schema for server response components, namely `ResponseHeader` and `ResponseBody`, Similar to `request_models`, each component defines the different fields it contains, and their constraints (mandatory, ranged, restricted to an enum, etc.)

#### Auth
* `session_metadata.py`: Defines a plain `SessionMetadata` class which holds data and methods relevant to a user session, such as refresh digest, current token, and chronological and usage metadata.

#### Classes
* `singletons.py`: Defines a `SingletonMetaclass` to enforce singleton classes

#### Stubs
* `typing.py`: General typing stubs and aliases