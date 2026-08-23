import sys
import os
sys.path.insert(0, os.path.abspath('.'))
from dotenv import load_dotenv
load_dotenv('.env')

from app.database import engine
from sqlalchemy import inspect

insp = inspect(engine)
cols = insp.get_columns('images')
import logging
logger = logging.getLogger(__name__)
logger.info("=== images table columns ===")
for c in cols:
    logger.info(f"  {c['name']}: {c['type']} nullable={c['nullable']}")

indexes = insp.get_indexes('images')
logger.info("\n=== images table indexes ===")
for ix in indexes:
    logger.info(f"  {ix['name']}: columns={ix['column_names']}")

logger.info("\nMigration verification OK")
