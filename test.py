import pyodbc

conn_str = (
    'DRIVER={ODBC Driver 17 for SQL Server};'
    'SERVER=ARM-30196\\SQLEXPRESS02;'
    'DATABASE=FTAlarms;'
    'UID=sa;'
    'PWD=Admin999;'
)

try:
    conn = pyodbc.connect(conn_str)
    print("Connected via pyodbc!")
except Exception as e:
    print(f"Connection failed: {e}")