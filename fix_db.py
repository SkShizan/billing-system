import sqlite3
import uuid

conn = sqlite3.connect('instance/billing.db')
c = conn.cursor()

try:
    print("1. Adding access_token column...")
    c.execute("ALTER TABLE invoices ADD COLUMN access_token VARCHAR(64)")
except Exception as e:
    print(f"Column may already exist: {e}")

print("2. Generating secure tokens for existing invoices...")
c.execute("SELECT id FROM invoices WHERE access_token IS NULL")
rows = c.fetchall()

for row in rows:
    secure_token = uuid.uuid4().hex
    c.execute("UPDATE invoices SET access_token = ? WHERE id = ?", (secure_token, row[0]))

conn.commit()
conn.close()
print("✅ Security upgrade complete! Your invoices are now locked down.")