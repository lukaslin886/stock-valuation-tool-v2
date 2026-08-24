import sqlite3, pandas as pd, os
from dotenv import load_dotenv
load_dotenv()
db_path = os.getenv('DATABASE_PATH', 'app/data/market_scan.db')
conn = sqlite3.connect(db_path)
df = pd.read_sql("SELECT * FROM market_snapshot WHERE stock_code='2330'", conn)
print("--- 2330 CHECK ---")
print(df.to_string())
conn.close()
