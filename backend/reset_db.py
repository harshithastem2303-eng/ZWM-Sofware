import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")

print("Connecting to DB to drop schema...")
conn = psycopg2.connect(db_url)
conn.autocommit = True
cur = conn.cursor()

print("Dropping public schema...")
cur.execute("DROP SCHEMA public CASCADE;")
print("Recreating public schema...")
cur.execute("CREATE SCHEMA public;")
cur.execute("GRANT ALL ON SCHEMA public TO postgres;")
cur.execute("GRANT ALL ON SCHEMA public TO public;")

print("Schema reset successful!")
cur.close()
conn.close()
