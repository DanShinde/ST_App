# config.py
DB_CONFIG = {
    'driver': 'ODBC Driver 17 for SQL Server',
    'server': 'ARM-30196\\SQLEXPRESS02',
    'database': 'ParReport',
    'trusted_connection': 'yes'
}

def get_connection_string():
    return (
        f"Driver={DB_CONFIG['driver']};"
        f"Server={DB_CONFIG['server']};"
        f"Database={DB_CONFIG['database']};"
        f"Trusted_Connection={DB_CONFIG['trusted_connection']};"
    )