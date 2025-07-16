import os
from dotenv import load_dotenv

import psycopg as pg
import psycopg.conninfo
from psycopg import sql

# Imports for Postgres enums
from models.permissions import RoleTypes, FilePermissions
from server.database.models import Severity, LogAuthor, LogType, ROLE_PERMISSION_MAPPING

loaded: bool = load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
                           override=True, verbose=True)
if not loaded:
    raise FileNotFoundError

connection = pg.connect(conninfo=psycopg.conninfo.make_conninfo(
    user=os.environ['PG_USERNAME'], password=os.environ['PG_PASSWORD'],
    host=os.environ['PG_HOST'], port=os.environ['PG_PORT'], dbname=os.environ['PG_DBNAME'])
    )

# Before any tables are created, we need to create all enum types
ENUM_CREATION_TEMPLATE: sql.SQL = sql.SQL('''CREATE TYPE {enum_name} AS ENUM ({enum_literals});''')

connection.execute(ENUM_CREATION_TEMPLATE.format(enum_name=sql.Identifier('permission_type'),
                                                 enum_literals=sql.SQL(', ').join(sql.Literal(member.value) for member in FilePermissions)))

connection.execute(ENUM_CREATION_TEMPLATE.format(enum_name=sql.Identifier('role_type'),
                                                 enum_literals=sql.SQL(', ').join(sql.Literal(role.value) for role in RoleTypes)))

connection.execute(ENUM_CREATION_TEMPLATE.format(enum_name=sql.Identifier('log_type'),
                                                 enum_literals=sql.SQL(', ').join(sql.Literal(log_type.value) for log_type in LogType)))

connection.execute(ENUM_CREATION_TEMPLATE.format(enum_name=sql.Identifier('logger_type'),
                                                 enum_literals=sql.SQL(', ').join(sql.Literal(log_author.value) for log_author in LogAuthor)))

connection.execute(ENUM_CREATION_TEMPLATE.format(enum_name=sql.Identifier('severity'),
                                                 enum_literals=sql.SQL(', ').join(sql.Literal(severity.value) for severity in Severity)))

connection.commit()

# All enums created, proceed with tables
with open(os.path.join(os.path.dirname(__file__), 'genesis.sql'), 'r') as genesis_script:
    genesis_sql = genesis_script.read()

connection.execute(query=genesis_sql)
connection.commit()

with connection.cursor() as cursor:
    # Populate 'permissions' table with permissions
    cursor.executemany(query='''INSERT INTO permissions
                       VALUES (%s);''',
                       params_seq=((permission.value,) for permission in FilePermissions))

    # Populate 'roles' table with permission FKs
    roles_population_sql: sql.SQL = sql.SQL('''INSERT INTO roles
                                            VALUES (%s, %s);''')
    
    for role, permissions in ROLE_PERMISSION_MAPPING.items():
        cursor.executemany(query=roles_population_sql,
                           params_seq=((role.value, permission.value,) for permission in permissions))
    connection.commit()