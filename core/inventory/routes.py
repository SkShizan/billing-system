import os
from flask import Blueprint, render_template, request, redirect, url_for, current_app, jsonify, flash, session
from werkzeug.utils import secure_filename
from core.models import Product, HSNDictionary
from core.extensions import db

inventory_bp = Blueprint('inventory', __name__)

# Helper function to check login
def is_logged_in():
    return 'company_id' in session

@inventory_bp.route('/add-product', methods=['GET', 'POST'])
def add_product():
    # SECURITY: Kick them out if they aren't logged in
    if not is_logged_in(): 
        flash("Please log in to access your inventory.", "warning")
        return redirect(url_for('auth.login'))
        
    company_id = session['company_id'] # Get the logged-in company's ID

    if request.method == 'POST':
        name = request.form.get('name')
        price = request.form.get('price')
        hsn = request.form.get('hsn_code')
        gst = request.form.get('gst_percentage')
        
        image_file = request.files.get('image')
        image_path = None
        if image_file and image_file.filename != '':
            filename = secure_filename(image_file.filename)
            upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, filename)
            image_file.save(file_path)
            image_path = f'uploads/{filename}'

        # FIX: Assign this product to the specific logged-in company!
        new_product = Product(
            company_id=company_id, 
            name=name, 
            current_price=float(price), 
            hsn_code=hsn, 
            gst_percentage=float(gst),
            image_path=image_path
        )
        db.session.add(new_product)
        db.session.commit()
        flash("Product added successfully!", "success")
        return redirect(url_for('inventory.add_product'))

    # --- NEW ADVANCED GET LOGIC (Search & Pagination) ---
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()

    # Base query: Only load products belonging to THIS company
    query = Product.query.filter_by(company_id=company_id)

    # Apply search filter if present
    if search_query:
        query = query.filter(
            (Product.name.ilike(f'%{search_query}%')) |
            (Product.hsn_code.ilike(f'%{search_query}%'))
        )

    # Paginate with a limit of 10 items per page
    pagination = query.order_by(Product.id.desc()).paginate(page=page, per_page=10)

    return render_template(
        'inventory/add_product.html', 
        pagination=pagination, 
        search_query=search_query
    )

@inventory_bp.route('/edit/<int:id>', methods=['POST'])
def edit_product(id):
    if not is_logged_in(): return redirect(url_for('auth.login'))
    
    # Security: Ensure the product actually belongs to the logged-in company
    product = Product.query.filter_by(id=id, company_id=session['company_id']).first_or_404()
    
    product.name = request.form.get('name')
    product.current_price = float(request.form.get('price'))
    product.hsn_code = request.form.get('hsn_code')
    product.gst_percentage = float(request.form.get('gst_percentage'))
    
    image_file = request.files.get('image')
    if image_file and image_file.filename != '':
        filename = secure_filename(image_file.filename)
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)
        image_file.save(file_path)
        product.image_path = f'uploads/{filename}'

    db.session.commit()
    flash("Product updated successfully!", "success")
    return redirect(url_for('inventory.add_product'))

@inventory_bp.route('/delete/<int:id>', methods=['POST'])
def delete_product(id):
    if not is_logged_in(): return redirect(url_for('auth.login'))
    
    # Security: Ensure the product belongs to the logged-in company
    product = Product.query.filter_by(id=id, company_id=session['company_id']).first_or_404()
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted.", "info")
    return redirect(url_for('inventory.add_product'))

@inventory_bp.route('/api/hsn-suggest')
def hsn_suggest():
    query = request.args.get('q', '').strip().lower()
    if len(query) < 2: return jsonify([])

    matches = HSNDictionary.query.filter(HSNDictionary.description.ilike(f'%{query}%')).limit(15).all()
    results = [{"keyword": m.description, "hsn": m.hsn_code, "gst": m.gst_rate} for m in matches]
    return jsonify(results)