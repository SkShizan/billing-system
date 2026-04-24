from .extensions import db
from datetime import datetime,timedelta

# --- NEW: THE TENANT (COMPANY) MODEL ---
class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    login_id = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    logo_path = db.Column(db.String(255), nullable=True)
    address = db.Column(db.Text, nullable=True)
    gstin = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reset_otp = db.Column(db.String(6), nullable=True)
    reset_otp_expiry = db.Column(db.DateTime, nullable=True)
    
    state_code = db.Column(db.String(5), default='WB')
    short_code = db.Column(db.String(10), default='CMP')
    invoice_seq = db.Column(db.Integer, default=0) # Tracks the 1234 number

    # Relationships to access a company's specific data easily
    products = db.relationship('Product', backref='company', lazy=True)
    customers = db.relationship('Customer', backref='company', lazy=True)
    invoices = db.relationship('Invoice', backref='company', lazy=True)
    
    smtp_server = db.Column(db.String(150), nullable=True)
    smtp_port = db.Column(db.Integer, default=587)
    smtp_username = db.Column(db.String(150), nullable=True)
    smtp_password = db.Column(db.String(150), nullable=True)

class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False) # ISOLATION
    name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(15), nullable=False) # Removed unique=True so diff companies can have same customer
    email = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    invoices = db.relationship('Invoice', backref='customer', lazy=True)

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False) # ISOLATION
    name = db.Column(db.String(200), nullable=False)
    current_price = db.Column(db.Float, nullable=False)
    base_price = db.Column(db.Float, nullable=True) # MRP
    discount_type = db.Column(db.String(10), nullable=True) # 'flat' or 'percentage'
    discount_value = db.Column(db.Float, default=0.0)
    hsn_code = db.Column(db.String(20), nullable=True)
    gst_percentage = db.Column(db.Float, default=0.0)
    image_path = db.Column(db.String(255), nullable=True) 

class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False) # ISOLATION
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    access_token = db.Column(db.String(64), unique=True, nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    
    subtotal = db.Column(db.Float, nullable=False)
    discount_type = db.Column(db.String(10))
    discount_value = db.Column(db.Float, default=0.0)
    total_tax = db.Column(db.Float, nullable=False)
    grand_total = db.Column(db.Float, nullable=False)
    # 🎯 Payment and Split States
    is_paid = db.Column(db.Boolean, default=False)
    payment_method = db.Column(db.String(20), default='Cash')
    split_gst = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True)

class InvoiceItem(db.Model):
    __tablename__ = 'invoice_items'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    
    quantity = db.Column(db.Integer, nullable=False)
    price_at_purchase = db.Column(db.Float, nullable=False) 
    base_price_at_purchase = db.Column(db.Float, nullable=True) # MRP at time of sale
    discount_type = db.Column(db.String(10), nullable=True)
    discount_value = db.Column(db.Float, default=0.0)
    gst_percentage_at_purchase = db.Column(db.Float, nullable=False)
    hsn_at_purchase = db.Column(db.String(20), nullable=True)
    # 🎯 Custom CGST/SGST overrides
    cgst_percentage = db.Column(db.Float, default=0.0)
    sgst_percentage = db.Column(db.Float, default=0.0)
    
    product = db.relationship('Product')

# HSN Dictionary stays universal (No company_id) so all companies share the dev's uploaded rules
class HSNDictionary(db.Model):
    __tablename__ = 'hsn_dictionary'
    id = db.Column(db.Integer, primary_key=True)
    hsn_code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    gst_rate = db.Column(db.Float, nullable=False)

class SMTPSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    server = db.Column(db.String(150), nullable=False)
    port = db.Column(db.Integer, nullable=False, default=587)
    username = db.Column(db.String(150), nullable=False)
    password = db.Column(db.String(150), nullable=False)
    sender_email = db.Column(db.String(150), nullable=False)
    use_tls = db.Column(db.Boolean, default=True)