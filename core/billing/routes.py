from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash
from core.models import db, Customer, Product, Invoice, InvoiceItem
import uuid
from sqlalchemy import or_
from datetime import datetime
from sqlalchemy import func

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


@billing_bp.route('/history')
def history():
    # SECURITY: Check if logged in
    company_id = session.get('company_id')
    if not company_id:
        flash("Please log in to view history.", "warning")
        return redirect(url_for('auth.login'))

    # Get search and pagination parameters
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()

    # Base query: Invoices for THIS company, joining Customer so we can search by name/phone
    # Assuming you have models imported like: from core.models import Invoice, Customer
    query = Invoice.query.join(Customer).filter(Invoice.company_id == company_id)

    # Apply search filter if present
    if search_query:
        query = query.filter(
            or_(
                Invoice.invoice_number.ilike(f"%{search_query}%"),
                Customer.name.ilike(f"%{search_query}%"),
                Customer.phone_number.ilike(f"%{search_query}%")
            )
        )

    # Paginate with a limit of 10 invoices per page
    pagination = query.order_by(Invoice.created_at.desc()).paginate(page=page, per_page=10)

    return render_template(
        'billing/history.html', 
        pagination=pagination, 
        search_query=search_query
    )


@billing_bp.route('/dashboard')
def dashboard():
    # 1. Security Check
    company_id = session.get('company_id')
    if not company_id:
        return redirect('/auth/login')

    # 2. Time Calculations
    now = datetime.now()
    # Midnight today
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Midnight on the 1st of the current month
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # 3. Fast Database Aggregations using func (O(1) memory transfer)
    
    # Today's Metrics (Revenue & Count)
    today_stats = db.session.query(
        func.sum(Invoice.grand_total).label('revenue'),
        func.count(Invoice.id).label('count')
    ).filter(
        Invoice.company_id == company_id,
        Invoice.created_at >= start_of_today
    ).first()

    # Monthly Metrics (Revenue & Tax)
    month_stats = db.session.query(
        func.sum(Invoice.grand_total).label('revenue'),
        func.sum(Invoice.total_tax).label('tax')
    ).filter(
        Invoice.company_id == company_id,
        Invoice.created_at >= start_of_month
    ).first()

    # Inventory Metric (Active Products)
    total_products = Product.query.filter_by(company_id=company_id).count()

    # 4. Fetch Recent Transactions (Limit to 5 for speed)
    recent_invoices = Invoice.query.filter_by(company_id=company_id) \
        .order_by(Invoice.created_at.desc()) \
        .limit(5).all()

    # 5. Handle None values (If there are no sales yet, func.sum returns None)
    metrics = {
        'today_revenue': today_stats.revenue or 0.0,
        'today_invoices': today_stats.count or 0,
        'month_revenue': month_stats.revenue or 0.0,
        'month_tax': month_stats.tax or 0.0,
        'total_products': total_products
    }

    # 6. Format Date for the UI
    current_date_str = now.strftime('%A, %b %d')

    return render_template(
        'dashboard/index.html', 
        metrics=metrics,
        recent_invoices=recent_invoices,
        current_date=current_date_str
    )