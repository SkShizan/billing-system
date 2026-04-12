from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash
from core.models import db, Customer, Product, Invoice, InvoiceItem
import uuid

billing_bp = Blueprint('billing', __name__)

# --- SECURITY HELPER ---
def is_logged_in():
    return 'company_id' in session

@billing_bp.route('/')
def index():
    if not is_logged_in(): 
        flash("Please log in to use the Point of Sale system.", "warning")
        return redirect(url_for('auth.login'))
    return render_template('billing/index.html')

@billing_bp.route('/api/products')
def get_products():
    """Ajax API: Auto-suggest products isolated by logged-in company."""
    if not is_logged_in(): return jsonify([])
    
    company_id = session['company_id']
    query = request.args.get('q', '').lower().strip()
    
    if query:
        products = Product.query.filter(
            Product.company_id == company_id,
            Product.name.ilike(f'%{query}%')
        ).limit(15).all()
    else:
        return jsonify([])
    
    results = [{"id": p.id, "name": p.name, "hsn": p.hsn_code, "price": p.current_price, "gst": p.gst_percentage} for p in products]
    return jsonify(results)

@billing_bp.route('/api/generate_bill', methods=['POST'])
def generate_bill():
    """API: Processes the cart and saves the invoice to the database."""
    if not is_logged_in(): return jsonify({"success": False, "error": "Not logged in"})
    
    company_id = session['company_id']
    data = request.json
    
    # 1. Handle Customer
    customer = Customer.query.filter_by(phone_number=data['customer_phone'], company_id=company_id).first()
    if not customer:
        customer = Customer(
            company_id=company_id, 
            name=data['customer_name'], 
            phone_number=data['customer_phone']
        )
        db.session.add(customer)
        db.session.flush() 
    
    # 2. Create Invoice with Unguessable ID
    invoice = Invoice(
        company_id=company_id,
        invoice_number=f"INV-{str(uuid.uuid4())[:8].upper()}",
        customer_id=customer.id,
        subtotal=data['subtotal'],
        discount_type=data['discount_type'],
        discount_value=data['discount_value'],
        total_tax=data['total_tax'],
        grand_total=data['grand_total']
    )
    db.session.add(invoice)
    db.session.flush()

    # 3. Add Invoice Items
    for item in data['items']:
        product = Product.query.filter_by(id=item['product_id'], company_id=company_id).first()
        if product:
            inv_item = InvoiceItem(
                invoice_id=invoice.id,
                product_id=product.id,
                quantity=item['quantity'],
                price_at_purchase=product.current_price,
                gst_percentage_at_purchase=product.gst_percentage
            )
            db.session.add(inv_item)
    
    db.session.commit()
    return jsonify({"success": True, "invoice_id": invoice.id})

# --- INTERNAL VIEW (Requires Login) ---
@billing_bp.route('/invoice/<int:invoice_id>')
def view_invoice(invoice_id):
    if not is_logged_in(): return redirect(url_for('auth.login'))
    
    # Security: Ensure company only sees its own invoices
    invoice = Invoice.query.filter_by(id=invoice_id, company_id=session['company_id']).first_or_404()
    return render_template('billing/invoice_template.html', invoice=invoice, is_public=False)

# --- PUBLIC VIEW (For WhatsApp Links) ---
@billing_bp.route('/public/invoice/<invoice_number>')
def public_view_invoice(invoice_number):
    """Secure, read-only link for customers (No login required)."""
    # Look up by the random string (INV-XXXXX) so it cannot be guessed
    invoice = Invoice.query.filter_by(invoice_number=invoice_number).first_or_404()
    
    # Pass is_public=True so the template knows to hide internal buttons
    return render_template('billing/invoice_template.html', invoice=invoice, is_public=True)