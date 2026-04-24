import os
from flask import Blueprint, render_template, request, redirect, url_for, current_app, jsonify, flash, session
from werkzeug.utils import secure_filename
from sqlalchemy import func, case
from core.models import Product, HSNDictionary
from core.extensions import db

inventory_bp = Blueprint('inventory', __name__)

def is_logged_in():
    return 'company_id' in session

@inventory_bp.route('/add-product', methods=['GET', 'POST'])
def add_product():
    if not is_logged_in(): 
        flash("Please log in to access your inventory.", "warning")
        return redirect(url_for('auth.login'))
        
    company_id = session['company_id']

    if request.method == 'POST':
        name = request.form.get('name')
        hsn = request.form.get('hsn_code')
        gst = request.form.get('gst_percentage', 0.0)
        
        # 1. Safely Capture Base Price
        raw_base = request.form.get('base_price', '').strip()
        raw_fallback_price = request.form.get('price', '0').strip()
        base_price_val = float(raw_base) if raw_base else float(raw_fallback_price)
        
        # 2. Safely Capture Discount
        discount_type = request.form.get('discount_type', 'flat')
        raw_discount = request.form.get('discount_value', '0').strip()
        discount_val = float(raw_discount) if raw_discount else 0.0

        # 3. 🎯 BULLETPROOF: Server-side calculation of Final Price
        if discount_type == 'flat':
            final_price = base_price_val - discount_val
        elif discount_type == 'percentage':
            final_price = base_price_val - (base_price_val * (discount_val / 100.0))
        else:
            final_price = base_price_val
            
        final_price = max(final_price, 0.0) # Prevent negative prices

        image_file = request.files.get('image')
        image_path = None
        if image_file and image_file.filename != '':
            filename = secure_filename(image_file.filename)
            upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, filename)
            image_file.save(file_path)
            image_path = f'uploads/{filename}'

        new_product = Product(
            company_id=company_id, 
            name=name, 
            current_price=final_price, # 🎯 Saved directly from our math
            base_price=base_price_val,
            discount_type=discount_type,
            discount_value=discount_val,
            hsn_code=hsn, 
            gst_percentage=float(gst),
            image_path=image_path,
            is_active=True # 🎯 Ensure new products are marked active
        )
        db.session.add(new_product)
        db.session.commit()
        flash("Product added successfully!", "success")
        return redirect(url_for('inventory.add_product'))

    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()

    # 🎯 SOFT DELETE FIX: Only fetch products that have not been deleted
    query = Product.query.filter_by(company_id=company_id, is_active=True)

    if search_query:
        query = query.filter(
            (Product.name.ilike(f'%{search_query}%')) |
            (Product.hsn_code.ilike(f'%{search_query}%'))
        )

    pagination = query.order_by(Product.id.desc()).paginate(page=page, per_page=10)

    return render_template(
        'inventory/add_product.html', 
        pagination=pagination, 
        search_query=search_query
    )

@inventory_bp.route('/edit/<int:id>', methods=['POST'])
def edit_product(id):
    if not is_logged_in(): return redirect(url_for('auth.login'))
    
    product = Product.query.filter_by(id=id, company_id=session['company_id']).first_or_404()
    
    product.name = request.form.get('name')
    
    # 1. Safely Capture Base Price
    raw_base = request.form.get('base_price', '').strip()
    product.base_price = float(raw_base) if raw_base else product.current_price
    
    # 2. Safely Capture Discount
    product.discount_type = request.form.get('discount_type', 'flat')
    raw_discount = request.form.get('discount_value', '0').strip()
    product.discount_value = float(raw_discount) if raw_discount else 0.0
    
    # 3. 🎯 BULLETPROOF: Recalculate Final Price directly on the backend
    if product.discount_type == 'flat':
        final_price = product.base_price - product.discount_value
    elif product.discount_type == 'percentage':
        final_price = product.base_price - (product.base_price * (product.discount_value / 100.0))
    else:
        final_price = product.base_price
        
    product.current_price = max(final_price, 0.0) # Prevent negative prices
    
    product.hsn_code = request.form.get('hsn_code')
    product.gst_percentage = float(request.form.get('gst_percentage', 0.0))
    
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
    
    product = Product.query.filter_by(id=id, company_id=session['company_id']).first_or_404()
    
    # 🎯 SOFT DELETE FIX: Hide the product instead of destroying it
    product.is_active = False
    
    db.session.commit()
    flash("Product deleted.", "info")
    return redirect(url_for('inventory.add_product'))

@inventory_bp.route('/api/hsn-suggest')
def hsn_suggest():
    query_string = request.args.get('q', '').strip().lower()
    
    if len(query_string) < 2: 
        return jsonify([])

    # 1. 🎯 NUMERIC SEARCH: If they type numbers, they want the exact HSN Code
    if query_string.isdigit():
        matches = HSNDictionary.query.filter(
            HSNDictionary.hsn_code.ilike(f'%{query_string}%')
        ).limit(15).all()
        results = [{"keyword": m.description, "hsn": m.hsn_code, "gst": m.gst_rate} for m in matches]
        return jsonify(results)

    # 2. 🎯 TEXT SEARCH: Split words and ignore useless "stop-words"
    words = query_string.split()
    stop_words = {'and', 'or', 'the', 'for', 'of', 'in', 'to', 'with', 'a', 'an'}

    search_filters = []
    score_cases = []

    for word in words:
        if word in stop_words:
            continue

        root_word = word
        # Strip common suffixes so "designing" perfectly matches "design"
        if len(root_word) > 4:
            if root_word.endswith('ing'): root_word = root_word[:-3]
            elif root_word.endswith('ies'): root_word = root_word[:-3] + 'y'
            elif root_word.endswith('es'): root_word = root_word[:-2]
            elif root_word.endswith('ed'): root_word = root_word[:-2]
            elif root_word.endswith('s') and not root_word.endswith('ss'): root_word = root_word[:-1]
        
        if len(root_word) >= 3:
            condition = HSNDictionary.description.ilike(f'%{root_word}%')
            search_filters.append(condition)
            
            # 🎯 ASSIGN POINTS: Give +1 point if this specific word is found
            score_cases.append(case((condition, 1), else_=0))

    if not search_filters:
        return jsonify([])

    # 3. 🎯 CALCULATE TOTAL RELEVANCE SCORE
    # Safely add the SQL case points together
    relevance_score = score_cases[0]
    for score in score_cases[1:]:
        relevance_score += score

    # 4. 🎯 EXECUTE THE SMART ALGORITHM
    # Priority 1: Highest Score wins (Matches the most words)
    # Priority 2: Tie-Breaker -> Shorter string wins (Fixes the Graphic Design issue)
    matches = HSNDictionary.query.filter(
        db.or_(*search_filters)
    ).order_by(
        relevance_score.desc(),
        func.length(HSNDictionary.description).asc()
    ).limit(15).all()

    # Format for the UI
    results = [
        {
            "keyword": m.description, 
            "hsn": m.hsn_code, 
            "gst": m.gst_rate
        } for m in matches
    ]
    
    return jsonify(results)