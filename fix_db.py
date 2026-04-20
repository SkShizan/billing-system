import sqlite3

try:
    conn = sqlite3.connect('instance/billing.db')
    cursor = conn.cursor()

    # Add new columns to products table
    cursor.execute("ALTER TABLE products ADD COLUMN base_price FLOAT;")
    cursor.execute("ALTER TABLE products ADD COLUMN discount_type VARCHAR(10);")
    cursor.execute("ALTER TABLE products ADD COLUMN discount_value FLOAT DEFAULT 0.0;")

    # Add new columns to invoice_items table
    cursor.execute("ALTER TABLE invoice_items ADD COLUMN base_price_at_purchase FLOAT;")
    cursor.execute("ALTER TABLE invoice_items ADD COLUMN discount_type VARCHAR(10);")
    cursor.execute("ALTER TABLE invoice_items ADD COLUMN discount_value FLOAT DEFAULT 0.0;")

    conn.commit()
    print("✅ Database updated successfully! The new columns are ready.")
except sqlite3.OperationalError as e:
    print(f"⚠️ Error: {e} (This usually means the column already exists, which is fine!)")
finally:
    conn.close()