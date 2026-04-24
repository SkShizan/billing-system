import sqlite3

conn = sqlite3.connect('instance/billing.db')
c = conn.cursor()
try:
    print("Adding is_active column to products...")
    c.execute("ALTER TABLE products ADD COLUMN is_active BOOLEAN DEFAULT 1")
    c.execute("UPDATE products SET is_active = 1")
    conn.commit()
    print("✅ Ready for production!")
except Exception as e:
    print(f"Skipped/Error: {e}")
conn.close()