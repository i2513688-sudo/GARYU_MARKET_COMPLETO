import os
from dotenv import load_dotenv
load_dotenv()

DATABASES = {
    'identidad': 'garyu_identidad_db',
    'catalogo': 'garyu_catalogo_db',
    'inventario': 'garyu_inventario_db',
    'comercio': 'garyu_comercio_db',
    'pagos': 'garyu_pagos_db',
    'logistica': 'garyu_logistica_db',
}

def connection_string(database=None):
    driver = os.getenv('DB_DRIVER', 'ODBC Driver 18 for SQL Server')
    server = os.getenv('DB_SERVER', r'LAPTOP-TK9K3TUR\user')
    port = os.getenv('DB_PORT', '').strip()
    server = f'{server},{port}' if port else server
    parts = [f'DRIVER={{{driver}}}', f'SERVER={server}']
    if database:
        parts.append(f'DATABASE={database}')
    parts += [f"Encrypt={os.getenv('DB_ENCRYPT','no')}",
              f"TrustServerCertificate={os.getenv('DB_TRUST_SERVER_CERTIFICATE','yes')}",
              'Connection Timeout=12']
    auth = os.getenv('DB_AUTH', 'windows').lower()
    if auth in ('windows', 'integrated', 'trusted'):
        parts.append('Trusted_Connection=yes')
    else:
        parts.extend([f"UID={os.getenv('DB_USERNAME','')}", f"PWD={os.getenv('DB_PASSWORD','')}"])
    return ';'.join(parts) + ';'
