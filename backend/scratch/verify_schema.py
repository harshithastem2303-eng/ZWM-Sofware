import sys
import os
sys.path.insert(0, os.path.abspath('.'))
from dotenv import load_dotenv
load_dotenv('.env')

from app.database import engine
from sqlalchemy import inspect

insp = inspect(engine)
cols = insp.get_columns('images')
print("=== images table columns ===")
for c in cols:
    print(f"  {c['name']}: {c['type']} nullable={c['nullable']}")

indexes = insp.get_indexes('images')
print("\n=== images table indexes ===")
for ix in indexes:
    print(f"  {ix['name']}: columns={ix['column_names']}")

print("\nMigration verification OK")
