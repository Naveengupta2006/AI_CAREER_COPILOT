import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import SessionLocal, engine
from sqlalchemy import text

db = SessionLocal()
try:
    # Get all tables
    with engine.connect() as conn:
        tables = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")).fetchall()
        print("Tables in database:")
        for t in tables:
            table_name = t[0]
            # Count rows
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            print(f"- {table_name}: {count} rows")
finally:
    db.close()
