import sqlite3

# Connect to the database
conn = sqlite3.connect('instance/billing.db')
c = conn.cursor()

try:
    print("Adding hsn_at_purchase column to invoice_items table...")
    c.execute("ALTER TABLE invoice_items ADD COLUMN hsn_at_purchase VARCHAR(20)")
    conn.commit()
    print("✅ Database upgraded successfully!")
except Exception as e:
    print(f"⚠️ Skipped or Error: {e}")

conn.close()