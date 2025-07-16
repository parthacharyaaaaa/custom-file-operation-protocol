CREATE TABLE IF NOT EXISTS users(
    username            VARCHAR(128) PRIMARY KEY,
    password_hash       BYTEA NOT NULL,
    password_salt       BYTEA NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS files(
    filename            VARCHAR(128) NOT NULL,
    owner               VARCHAR(128) NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PUBLIC              BOOLEAN NOT NULL DEFAULT false,

    PRIMARY KEY (owner, filename)
);
CREATE INDEX ix_files_public ON files(PUBLIC);


CREATE TABLE IF NOT EXISTS permissions(
    action              permission_type PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS ROLES(
    role                role_type,
    permission          permission_type REFERENCES permissions(action),

    PRIMARY KEY (role, permission)
);

CREATE TABLE IF NOT EXISTS file_permissions(
    file_owner          VARCHAR(128) NOT NULL,
    filename            VARCHAR(128) NOT NULL,
    grantee             VARCHAR(128) NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    role                role_type NOT NULL,
    granted_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    granted_by          VARCHAR(128) NOT NULL REFERENCES users(username) ON DELETE NO ACTION,
    granted_until       TIMESTAMP,

    PRIMARY KEY (file_owner, filename, grantee),
    FOREIGN KEY (file_owner, filename) REFERENCES files(owner, filename) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ban_logs(
    username            VARCHAR(128) NOT NULL REFERENCES users(username) ON DELETE NO ACTION,
    ban_reason          VARCHAR(32) NOT NULL,
    ban_description     VARCHAR(256),
    ban_time            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lifted_at           TIMESTAMP,

    PRIMARY KEY (username, ban_time),
    CONSTRAINT check_ban_time_validity CHECK (ban_time <= CURRENT_TIMESTAMP),
    CONSTRAINT check_unban_time_validity CHECK (lifted_at <= CURRENT_TIMESTAMP)
);

CREATE INDEX ix_ban_logs_lifted_at ON ban_logs(lifted_at);
CREATE INDEX ix_ban_logs_ban_time ON ban_logs(ban_time);

CREATE TABLE IF NOT EXISTS activity_logs(
    id              BIGSERIAL PRIMARY KEY,
    occurance_time  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    severity        SMALLINT NOT NULL DEFAULT 1,
    logged_by       logger_type NOT NULL DEFAULT 'exception_fallback',
    log_category    log_type NOT NULL DEFAULT 'unknown',
    log_details     VARCHAR(512),
    user_concerned  VARCHAR(128) REFERENCES users(username) ON DELETE NO ACTION,
    host_concerned  inet,

    CONSTRAINT check_activity_log_time_consistency CHECK(occurance_time <= CURRENT_TIMESTAMP),
    CONSTRAINT check_activity_log_severity CHECK(severity BETWEEN 1 AND 5)
);

CREATE INDEX ix_activity_logs_type ON activity_logs(log_category);
CREATE INDEX ix_activity_logs_logger ON activity_logs(logged_by);
CREATE INDEX ix_activity_logs_host ON activity_logs(host_concerned);
CREATE INDEX ix_activity_logs_severity ON activity_logs(severity);