from flask import render_template, session, redirect, url_for
from datetime import datetime
from sqlalchemy import func

# Assuming you have imported your db and models:
# from core.extensions import db
# from core.models import Invoice, Product, Customer

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

    # 6. Format Date for the UI (e.g., "Tuesday, Oct 24")
    current_date_str = now.strftime('%A, %b %d')

    return render_template(
        'dashboard/index.html', 
        metrics=metrics,
        recent_invoices=recent_invoices,
        current_date=current_date_str
    )