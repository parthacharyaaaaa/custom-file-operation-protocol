import os
from dotenv import load_dotenv
import psycopg as pg
import psycopg.conninfo

loaded: bool = load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
                           override=True, verbose=True)
if not loaded:
    raise FileNotFoundError

connection = pg.connect(conninfo=psycopg.conninfo.make_conninfo(
    user=os.environ['PG_USERNAME'], password=os.environ['PG_PASSWORD'],
    host=os.environ['PG_HOST'], port=os.environ['PG_PORT'], dbname=os.environ['PG_DBNAME'])
    )

sql: str = None
with open(os.path.join(os.path.dirname(__file__), 'genesis.sql'), 'r') as genesis_script:
    sql = genesis_script.read()

connection.execute(query=sql)
connection.commit()