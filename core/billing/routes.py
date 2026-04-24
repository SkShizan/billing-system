from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash
from core.models import db, Customer, Product, Invoice, InvoiceItem, Company
import uuid
from sqlalchemy import or_
from datetime import datetime, timedelta
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
            Product.is_active == True,
            Product.name.ilike(f'%{query}%')
        ).limit(15).all()
    else:
        return jsonify([])
    
    results = [{
        "id": p.id, 
        "name": p.name, 
        "hsn": p.hsn_code, 
        "price": p.current_price, # Final selling price
        "base_price": p.base_price or p.current_price, # MRP
        "discount_type": p.discount_type or 'flat',
        "discount_value": p.discount_value or 0.0,
        "gst": p.gst_percentage
    } for p in products]
    return jsonify(results)



# 🎯 NEW: Edit Invoice Route
@billing_bp.route('/edit/<int:invoice_id>')
def edit_invoice(invoice_id):
    if not is_logged_in(): 
        return redirect(url_for('auth.login'))
    
    # Fetch the invoice securely
    invoice = Invoice.query.filter_by(id=invoice_id, company_id=session['company_id']).first_or_404()
    
    # Render the main POS page, but pass the invoice data to it
    return render_template('billing/index.html', edit_invoice=invoice)


@billing_bp.route('/api/update_invoice_meta/<int:invoice_id>', methods=['POST'])
def update_invoice_meta(invoice_id):
    """API: Marks an invoice as paid/unpaid, updates payment method, and toggles GST splitting."""
    if not is_logged_in(): return jsonify({"success": False})
    
    invoice = Invoice.query.filter_by(id=invoice_id, company_id=session['company_id']).first()
    if invoice:
        data = request.json
        if 'is_paid' in data:
            invoice.is_paid = data['is_paid']
        if 'payment_method' in data:
            invoice.payment_method = data['payment_method']
        if 'split_gst' in data:
            invoice.split_gst = data['split_gst']
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False}), 404

@billing_bp.route('/delete/<int:invoice_id>', methods=['POST'])
def delete_invoice(invoice_id):
    if not is_logged_in(): 
        return redirect(url_for('auth.login'))
    
    invoice = Invoice.query.filter_by(id=invoice_id, company_id=session['company_id']).first_or_404()
    
    try:
        InvoiceItem.query.filter_by(invoice_id=invoice.id).delete()
        db.session.delete(invoice)
        db.session.commit()
        flash(f"Invoice {invoice.invoice_number} deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting invoice: {str(e)}", "danger")
        
    return redirect(url_for('billing.history'))

@billing_bp.route('/invoice/<int:invoice_id>')
def view_invoice(invoice_id):
    if not is_logged_in(): return redirect(url_for('auth.login'))
    invoice = Invoice.query.filter_by(id=invoice_id, company_id=session['company_id']).first_or_404()
    return render_template('billing/invoice_template.html', invoice=invoice, is_public=False)

@billing_bp.route('/public/invoice/<access_token>')
def public_view_invoice(access_token):
    invoice = Invoice.query.filter_by(access_token=access_token).first_or_404()
    return render_template('billing/invoice_template.html', invoice=invoice, is_public=True)

@billing_bp.route('/history')
def history():
    company_id = session.get('company_id')
    if not company_id:
        flash("Please log in to view history.", "warning")
        return redirect(url_for('auth.login'))

    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()

    query = Invoice.query.join(Customer).filter(Invoice.company_id == company_id)

    if search_query:
        query = query.filter(
            or_(
                Invoice.invoice_number.ilike(f"%{search_query}%"),
                Customer.name.ilike(f"%{search_query}%"),
                Customer.phone_number.ilike(f"%{search_query}%")
            )
        )

    pagination = query.order_by(Invoice.created_at.desc()).paginate(page=page, per_page=10)

    return render_template(
        'billing/history.html', 
        pagination=pagination, 
        search_query=search_query
    )

from datetime import datetime, timedelta
from sqlalchemy import func

@billing_bp.route('/dashboard')
def dashboard():
    if not is_logged_in():
        return redirect(url_for('auth.login'))
        
    company_id = session['company_id']
    today = datetime.utcnow().date()
    
    # 1. 🎯 Get Date Range from User (Default to last 7 days if none selected)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = today - timedelta(days=6)
            end_date = today
    else:
        start_date = today - timedelta(days=6)
        end_date = today

    # 2. 🎯 Filter Invoices by Selected Date Range
    range_invoices = Invoice.query.filter(
        Invoice.company_id == company_id,
        func.date(Invoice.created_at) >= start_date,
        func.date(Invoice.created_at) <= end_date
    ).all()
    
    # Keep today's revenue separate just for the live "Today" card
    today_invoices = Invoice.query.filter(
        Invoice.company_id == company_id,
        func.date(Invoice.created_at) == today
    ).all()

    # 3. Calculate Metrics for the Selected Range
    today_revenue = sum(inv.grand_total for inv in today_invoices)
    range_revenue = sum(inv.grand_total for inv in range_invoices)
    range_gross_sales = sum(inv.subtotal for inv in range_invoices)
    range_tax = sum(inv.total_tax for inv in range_invoices)
    
    aov = (range_revenue / len(range_invoices)) if range_invoices else 0.0
    total_products = Product.query.filter_by(company_id=company_id).count()

    metrics = {
        'today_revenue': today_revenue,
        'range_invoices': len(range_invoices),
        'range_revenue': range_revenue,
        'range_gross_sales': range_gross_sales,
        'range_tax': range_tax,
        'aov': aov,
        'total_products': total_products,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d')
    }

    # 4. Recent Transactions
    recent_invoices = Invoice.query.filter_by(company_id=company_id)\
        .order_by(Invoice.created_at.desc())\
        .limit(6).all()

    # 5. 🎯 Dynamic Chart 1: Revenue Pulse (Adjusts based on selected days)
    delta_days = (end_date - start_date).days
    chart_labels = []
    chart_data = []

    # Get grouped daily revenues from the DB for extreme speed
    daily_revenues = db.session.query(
        func.date(Invoice.created_at).label('date'),
        func.sum(Invoice.grand_total).label('revenue')
    ).filter(
        Invoice.company_id == company_id,
        func.date(Invoice.created_at) >= start_date,
        func.date(Invoice.created_at) <= end_date
    ).group_by(func.date(Invoice.created_at)).all()

    revenue_map = {str(d.date): float(d.revenue) for d in daily_revenues}

    # Loop through every day in the selected range to plot the chart
    for i in range(delta_days + 1):
        current_d = start_date + timedelta(days=i)
        label = current_d.strftime("%b %d")
        chart_labels.append(label)
        chart_data.append(revenue_map.get(str(current_d), 0.0))

    # 6. 🎯 Dynamic Chart 2: Payment Method Breakdown
    payment_counts = db.session.query(Invoice.payment_method, func.count(Invoice.id))\
        .filter(
            Invoice.company_id == company_id,
            func.date(Invoice.created_at) >= start_date,
            func.date(Invoice.created_at) <= end_date
        )\
        .group_by(Invoice.payment_method).all()
    
    pay_labels = [p[0] for p in payment_counts] if payment_counts else ['No Data']
    pay_data = [p[1] for p in payment_counts] if payment_counts else [1]

    return render_template(
        'dashboard/index.html', 
        metrics=metrics, 
        recent_invoices=recent_invoices, 
        chart_labels=chart_labels, 
        chart_data=chart_data,
        pay_labels=pay_labels,
        pay_data=pay_data
    )

@billing_bp.route('/customers')
def customers_directory():
    company_id = session.get('company_id')
    if not company_id:
        flash("Please log in to view your customers.", "warning")
        return redirect(url_for('auth.login'))

    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()

    query = db.session.query(
        Customer,
        func.count(Invoice.id).label('total_visits'),
        func.sum(Invoice.grand_total).label('lifetime_value'),
        func.max(Invoice.created_at).label('last_visit')
    ).join(Invoice, Customer.id == Invoice.customer_id) \
     .filter(Invoice.company_id == company_id) \
     .group_by(Customer.id)

    if search_query:
        query = query.filter(
            or_(
                Customer.name.ilike(f"%{search_query}%"),
                Customer.phone_number.ilike(f"%{search_query}%")
            )
        )

    pagination = query.order_by(func.max(Invoice.created_at).desc()).paginate(page=page, per_page=10)

    return render_template(
        'billing/customers.html', 
        pagination=pagination, 
        search_query=search_query
    )
    
    
@billing_bp.route('/api/generate_bill', methods=['POST'])
def generate_bill():
    if not is_logged_in(): return jsonify({"success": False, "error": "Not logged in"})
    
    company_id = session['company_id']
    data = request.json
    
    # 🎯 1. RACE CONDITION FIX: Lock the row so 2 cashiers can't get the same Invoice Number
    company = Company.query.filter_by(id=company_id).with_for_update().first()
    
    # Handle Customer
    customer = Customer.query.filter_by(phone_number=data['customer_phone'], company_id=company_id).first()
    if not customer:
        customer = Customer(company_id=company_id, name=data['customer_name'], phone_number=data['customer_phone'], email=data.get('customer_email'))
        db.session.add(customer)
        db.session.flush()
    elif data.get('customer_email'):
        customer.email = data.get('customer_email')
        db.session.flush()

    # 🎯 2. BACKEND MATH RECALCULATION: Never trust the frontend math
    calc_subtotal = 0.0
    calc_tax = 0.0
    verified_items = []
    is_split = data.get('split_gst', True)
    
    for item in data['items']:
        product = Product.query.filter_by(id=item['product_id'], company_id=company_id).first()
        if not product: continue
        
        qty = int(item['quantity'])
        base_price = float(item.get('base_price', product.current_price))
        disc_type = item.get('discount_type', 'flat')
        disc_val = float(item.get('discount_value', 0.0))
        
        # Calculate Secure Rate
        rate = base_price
        if disc_type == 'flat': rate -= disc_val
        elif disc_type == 'percentage': rate -= (base_price * (disc_val / 100))
        if rate < 0: rate = 0
        
        row_base_total = rate * qty
        
        # Calculate Secure Tax
        gst_percent = float(item.get('gst', product.gst_percentage))
        cgst = float(item.get('cgst', 0.0)) if is_split else 0.0
        sgst = float(item.get('sgst', 0.0)) if is_split else 0.0
        total_gst_percent = (cgst + sgst) if is_split else gst_percent
        row_tax = row_base_total * (total_gst_percent / 100)
        
        calc_subtotal += row_base_total
        calc_tax += row_tax
        
        verified_items.append({
            'product_id': product.id, 'qty': qty, 'base_price': base_price,
            'disc_type': disc_type, 'disc_val': disc_val, 'final_price': rate,
            'gst': gst_percent, 'cgst': cgst, 'sgst': sgst, 
            'hsn': item.get('hsn', product.hsn_code)
        })
        
        if not product.hsn_code and item.get('hsn'):
            product.hsn_code = item.get('hsn')

    # Apply Global Discount Securely
    global_disc_type = data.get('discount_type', 'flat')
    global_disc_val = float(data.get('discount_value', 0.0))
    global_disc_amt = global_disc_val if global_disc_type == 'flat' else calc_subtotal * (global_disc_val / 100)
    
    calc_grand_total = (calc_subtotal - global_disc_amt) + calc_tax
    if calc_grand_total < 0: calc_grand_total = 0

    edit_invoice_id = data.get('edit_invoice_id')
    
    if edit_invoice_id:
        # UPDATE EXISTING
        invoice = Invoice.query.filter_by(id=edit_invoice_id, company_id=company_id).first()
        invoice.customer_id = customer.id
        invoice.subtotal = calc_subtotal
        invoice.discount_type = global_disc_type
        invoice.discount_value = global_disc_val
        invoice.total_tax = calc_tax
        invoice.grand_total = calc_grand_total
        invoice.is_paid = data.get('is_paid', invoice.is_paid)
        invoice.payment_method = data.get('payment_method', invoice.payment_method)
        invoice.split_gst = is_split
        if not invoice.access_token: invoice.access_token = uuid.uuid4().hex
            
        InvoiceItem.query.filter_by(invoice_id=invoice.id).delete()
        inv_num = invoice.invoice_number
    else:
        # CREATE NEW
        company.invoice_seq += 1
        st_code = (company.state_code or "ST").upper()
        sh_code = (company.short_code or "CMP").upper()
        inv_num = f"INV-{st_code}-{company.invoice_seq:04d}{sh_code}"
        
        invoice = Invoice(
            company_id=company_id, invoice_number=inv_num, customer_id=customer.id,
            subtotal=calc_subtotal, discount_type=global_disc_type, discount_value=global_disc_val,
            total_tax=calc_tax, grand_total=calc_grand_total, is_paid=data.get('is_paid', False), 
            payment_method=data.get('payment_method', 'Cash'), split_gst=is_split, 
            access_token=uuid.uuid4().hex
        )
        db.session.add(invoice)
        
    db.session.flush()

    for vi in verified_items:
        inv_item = InvoiceItem(
            invoice_id=invoice.id, product_id=vi['product_id'], quantity=vi['qty'],
            price_at_purchase=vi['final_price'], base_price_at_purchase=vi['base_price'], 
            discount_type=vi['disc_type'], discount_value=vi['disc_val'],
            gst_percentage_at_purchase=vi['gst'], hsn_at_purchase=vi['hsn'],
            cgst_percentage=vi['cgst'], sgst_percentage=vi['sgst']
        )
        db.session.add(inv_item)
    db.session.commit()
    
    return jsonify({"success": True, "invoice_id": invoice.id})

@billing_bp.route('/api/send_invoice_email/<int:invoice_id>', methods=['POST'])
def send_invoice_email(invoice_id):
    """API: Sends the invoice via email when the button is clicked."""
    if not is_logged_in(): return jsonify({"success": False, "error": "Not logged in"})
    
    company_id = session['company_id']
    company = Company.query.get(company_id)
    invoice = Invoice.query.filter_by(id=invoice_id, company_id=company_id).first()
    
    if not invoice:
        return jsonify({"success": False, "error": "Invoice not found"})
        
    customer = invoice.customer
    
    # Check if we have what we need
    if not customer.email:
        return jsonify({"success": False, "error": "No email address saved for this customer."})
    if not company.smtp_server or not company.smtp_username:
        return jsonify({"success": False, "error": "Seller SMTP settings are not configured in Settings."})

    domain = request.host_url.rstrip('/')
    # 🎯 Update this line inside send_invoice_email
    public_link = f"{domain}/billing/public/invoice/{invoice.access_token}"
    
    from core.utils import send_company_invoice_email
    success, msg = send_company_invoice_email(
        company=company, 
        customer_email=customer.email, 
        customer_name=customer.name,
        invoice_no=invoice.invoice_number, 
        amount=invoice.grand_total, 
        invoice_link=public_link
    )
    
    if success:
        return jsonify({"success": True, "message": "Email sent successfully!"})
    else:
        return jsonify({"success": False, "error": msg})