-- DDL
--- Basic enum types
CREATE TYPE permission_type AS ENUM ('write', 'read', 'delete', 'manage_super', 'manage_rw');
CREATE TYPE role_type as ENUM ('owner', 'manager', 'reader', 'editor');

--- Tables
CREATE TABLE IF NOT EXISTS USERS(
    username VARCHAR(128) PRIMARY KEY,
    password_hash BYTEA NOT NULL,
    password_salt BYTEA NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS FILE(
    filename VARCHAR(128) NOT NULL,
    owner VARCHAR(128) REFERENCES USERS(username) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PUBLIC BOOLEAN NOT NULL DEFAULT false,

    PRIMARY KEY (owner, filename)
);
CREATE INDEX ix_files_public ON FILE(PUBLIC);


CREATE TABLE IF NOT EXISTS PERMISSIONS(
    action permission_type PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS ROLES(
    role role_type,
    permission permission_type REFERENCES PERMISSIONS(action),

    PRIMARY KEY (role, permission)
);

CREATE TABLE IF NOT EXISTS FILE_PERMISSIONS(
    file_owner VARCHAR(128) NOT NULL,
    filename VARCHAR(128) NOT NULL,
    grantee VARCHAR(128) REFERENCES USERS(username) NOT NULL,
    role role_type NOT NULL,
    granted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    granted_by VARCHAR(128) REFERENCES USERS(username) NOT NULL,

    PRIMARY KEY (file_owner, filename, grantee),
    FOREIGN KEY (file_owner, filename) REFERENCES FILE(owner, filename),
    CONSTRAINT check_ownership_consistency CHECK (role <> 'owner'),
    CONSTRAINT check_granter_consistency CHECK (granted_by <> grantee)
);

-- DML

-- Populate ROLES and PERMISSIONS
INSERT INTO PERMISSIONS VALUES ('manage_rw');
INSERT INTO PERMISSIONS VALUES ('manage_super');
INSERT INTO PERMISSIONS VALUES ('delete');
INSERT INTO PERMISSIONS VALUES ('write');
INSERT INTO PERMISSIONS VALUES ('read');

-- Owner
INSERT INTO ROLES VALUES ('owner', 'read');
INSERT INTO ROLES VALUES ('owner', 'write');
INSERT INTO ROLES VALUES ('owner', 'manage_rw');
INSERT INTO ROLES VALUES ('owner', 'manage_super'); -- Allow granting manager roles
INSERT INTO ROLES VALUES ('owner', 'delete');   -- Sole holder of delete permission

-- Manager
INSERT INTO ROLES VALUES ('manager', 'read');
INSERT INTO ROLES VALUES ('manager', 'write');
INSERT INTO ROLES VALUES ('manager', 'manage_rw');  -- Allow granting editor and reader roles

-- Editor
INSERT INTO ROLES VALUES ('editor', 'read');
INSERT INTO ROLES VALUES ('editor', 'write');

-- Reader
INSERT INTO ROLES VALUES ('reader', 'read')