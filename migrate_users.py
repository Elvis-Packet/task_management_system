import sqlite3
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

db_path = os.path.join(BASE_DIR, "instance", "database.db")

conn = sqlite3.connect(db_path)

cursor = conn.cursor()

columns = [

    ("manager_id", "INTEGER"),

    ("failed_login_attempts", "INTEGER DEFAULT 0"),

    ("password_changed_at", "DATETIME"),

    ("last_activity", "DATETIME"),

    ("last_ip_address", "VARCHAR(50)"),

    ("last_device", "VARCHAR(150)"),

    ("last_browser", "VARCHAR(150)"),

    ("is_first_login", "BOOLEAN DEFAULT 1")

]

for column, definition in columns:

    try:

        cursor.execute(
            f"ALTER TABLE users ADD COLUMN {column} {definition}"
        )

        print(f"✓ Added {column}")

    except Exception as e:

        print(f"✗ {column}: {e}")

conn.commit()

conn.close()

print("\nMigration completed successfully.")