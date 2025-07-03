-- DDL
--- Basic enum types
CREATE TYPE permission_type AS ENUM ('write', 'read', 'delete', 'manage_super', 'manage_rw');
CREATE TYPE role_type as ENUM ('owner', 'manager', 'reader', 'editor');
CREATE TYPE log_type AS ENUM ('user', 'database', 'session', 'request', 'network', 'internal', 'permission', 'audit', 'unknown');
CREATE TYPE logger_type AS ENUM ('session_master', 'connection_master', 'file_handler', 'socket_handler', 'bootup_handler', 'permission_handler', 'stream_parser', 'admin', 'cronjob');

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

CREATE TABLE IF NOT EXISTS BAN_LOGS(
    username VARCHAR(128) REFERENCES USERS(username) NOT NULL,
    ban_reason VARCHAR(32) NOT NULL,
    ban_description VARCHAR(256),
    ban_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lifted_at TIMESTAMP,

    PRIMARY KEY (username, ban_time),
    CONSTRAINT check_ban_time_validity CHECK (ban_time <= CURRENT_TIMESTAMP),
    CONSTRAINT check_unban_time_validity CHECK (lifted_at <= CURRENT_TIMESTAMP)
);

CREATE INDEX ix_ban_logs_lifted_at ON BAN_LOGS(lifted_at);
CREATE INDEX ix_ban_logs_ban_time ON BAN_LOGS(ban_time);

CREATE TABLE IF NOT EXISTS ACTIVITY_LOGS(
    id BIGSERIAL PRIMARY KEY,
    occurance_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    severity SMALLINT NOT NULL DEFAULT 1,
    logged_by logger_type NOT NULL,
    log_data log_type NOT NULL DEFAULT 'unknown',
    log_details VARCHAR(512),
    user_concerned VARCHAR(128) REFERENCES USERS(username),
    host_concerned inet NOT NULL,

    CONSTRAINT check_activity_log_time_consistency CHECK(occurance_time <= CURRENT_TIMESTAMP),
    CONSTRAINT check_activity_log_severity CHECK(severity BETWEEN 1 AND 5)
);

CREATE INDEX ix_activity_logs_type ON ACTIVITY_LOGS(log_data);
CREATE INDEX ix_activity_logs_logger ON ACTIVITY_LOGS(logged_by);
CREATE INDEX ix_activity_logs_host ON ACTIVITY_LOGS(host_concerned);
CREATE INDEX ix_activity_logs_severity ON ACTIVITY_LOGS(severity);

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