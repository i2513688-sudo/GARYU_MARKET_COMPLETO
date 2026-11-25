import pyodbc
from config import DATABASES, connection_string

def connect(db_key='comercio', autocommit=False):
    db_name = DATABASES.get(db_key, db_key)
    return pyodbc.connect(connection_string(db_name), autocommit=autocommit)

def rows(cursor):
    names = [c[0] for c in cursor.description] if cursor.description else []
    return [dict(zip(names, row)) for row in cursor.fetchall()] if names else []

def query_all(db_key, sql, params=()):
    with connect(db_key) as cn:
        cur = cn.cursor(); cur.execute(sql, params)
        return rows(cur)

def query_one(db_key, sql, params=()):
    result = query_all(db_key, sql, params)
    return result[0] if result else None
