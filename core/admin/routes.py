import csv
import io, os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash,current_app
from werkzeug.security import check_password_hash, generate_password_hash
from core.extensions import db
from core.models import HSNDictionary
from core.models import SMTPSettings
from core.models import Company
from werkzeug.utils import secure_filename
import pandas as pd
from flask import request, flash, redirect, url_for

admin_bp = Blueprint('admin', __name__)

DEV_USERNAME = "developer"
DEV_PASSWORD_HASH = generate_password_hash("admin123") 

@admin_bp.route('/companies/edit/<int:id>', methods=['POST'])
def edit_company(id):
    if not is_logged_in(): return redirect(url_for('admin.login'))
    
    company = Company.query.get_or_404(id)
    
    # 1. Update Basic Info
    company.name = request.form.get('name', company.name).strip()
    company.email = request.form.get('email', company.email).strip()
    company.address = request.form.get('address', company.address).strip()
    company.gstin = request.form.get('gstin', company.gstin).strip()
    
    # 2. Update Password (Only if the superadmin typed a new one)
    new_password = request.form.get('password')
    if new_password and len(new_password.strip()) > 0:
        company.password_hash = generate_password_hash(new_password)
        
    # 3. Handle Logo Override
    logo_file = request.files.get('logo')
    if logo_file and logo_file.filename != '':
        filename = secure_filename(f"tenant_{company.id}_{logo_file.filename}")
        upload_dir = os.path.join(current_app.root_path, 'static', 'logos')
        os.makedirs(upload_dir, exist_ok=True)
        logo_file.save(os.path.join(upload_dir, filename))
        company.logo_path = f'logos/{filename}'
        
    db.session.commit()
    flash(f"Tenant '{company.name}' updated successfully.", "success")
    return redirect(url_for('admin.manage_companies'))


@admin_bp.route('/companies/delete/<int:id>', methods=['POST'])
def delete_company(id):
    if not is_logged_in(): return redirect(url_for('admin.login'))
    
    company = Company.query.get_or_404(id)
    company_name = company.name
    
    # Due to cascade rules on the database models, deleting the company 
    # will also automatically delete their products and invoices.
    db.session.delete(company)
    db.session.commit()
    
    flash(f"Tenant '{company_name}' and all associated data have been permanently deleted.", "danger")
    return redirect(url_for('admin.manage_companies'))

def is_logged_in():
    return session.get('is_developer') is True

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == DEV_USERNAME and check_password_hash(DEV_PASSWORD_HASH, password):
            session['is_developer'] = True
            return redirect(url_for('admin.dashboard'))
        else:
            flash("Invalid credentials.", "danger")
            
    return render_template('admin/login.html')

@admin_bp.route('/logout')
def logout():
    session.pop('is_developer', None)
    return redirect(url_for('admin.login'))

@admin_bp.route('/dashboard', methods=['GET'])
def dashboard():
    if not is_logged_in(): return redirect(url_for('admin.login'))

    # Advanced feature: Search and Pagination
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()
    
    query = HSNDictionary.query
    if search_query:
        # Search by HSN Code OR Description
        query = query.filter(
            (HSNDictionary.hsn_code.ilike(f'%{search_query}%')) | 
            (HSNDictionary.description.ilike(f'%{search_query}%'))
        )
    
    # Show 50 items per page to prevent browser freezing
    pagination = query.order_by(HSNDictionary.id.desc()).paginate(page=page, per_page=50)
    total_hsn = HSNDictionary.query.count()

    return render_template(
        'admin/dashboard.html', 
        pagination=pagination, 
        total_hsn=total_hsn, 
        search_query=search_query
    )

@admin_bp.route('/hsn/add', methods=['POST'])
def add_hsn():
    if not is_logged_in(): return redirect(url_for('admin.login'))
    
    code = request.form.get('hsn_code').strip()
    desc = request.form.get('description').strip()
    gst = request.form.get('gst_rate')
    
    existing = HSNDictionary.query.filter_by(hsn_code=code).first()
    if existing:
        flash(f"HSN Code {code} already exists!", "warning")
    else:
        new_entry = HSNDictionary(hsn_code=code, description=desc, gst_rate=float(gst))
        db.session.add(new_entry)
        db.session.commit()
        flash("New HSN code added successfully.", "success")
        
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/hsn/edit/<int:id>', methods=['POST'])
def edit_hsn(id):
    if not is_logged_in(): return redirect(url_for('admin.login'))
    
    entry = HSNDictionary.query.get_or_404(id)
    entry.hsn_code = request.form.get('hsn_code').strip()
    entry.description = request.form.get('description').strip()
    entry.gst_rate = float(request.form.get('gst_rate'))
    
    db.session.commit()
    flash("HSN code updated successfully.", "success")
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/hsn/delete/<int:id>', methods=['POST'])
def delete_hsn(id):
    if not is_logged_in(): return redirect(url_for('admin.login'))
    
    entry = HSNDictionary.query.get_or_404(id)
    db.session.delete(entry)
    db.session.commit()
    flash("HSN code deleted securely.", "info")
    return redirect(url_for('admin.dashboard'))

# I kept the bulk upload route separate just in case you ever need it again!
@admin_bp.route('/hsn/upload', methods=['POST'])
def upload_csv():
    if not is_logged_in(): return redirect(url_for('admin.login'))
    # ... (Your existing CSV logic can go here if you decide to keep it)
    flash("CSV Upload disabled. Please use manual entry.", "info")
    return redirect(url_for('admin.dashboard'))

# --- COMPANY MANAGEMENT ROUTES (DEVELOPER ONLY) ---

@admin_bp.route('/companies', methods=['GET'])
def manage_companies():
    if not is_logged_in(): return redirect(url_for('admin.login'))
    
    # Get search and pagination parameters from the URL
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()
    
    query = Company.query

    # Apply search filter if a query exists
    if search_query:
        query = query.filter(
            (Company.name.ilike(f'%{search_query}%')) | 
            (Company.login_id.ilike(f'%{search_query}%')) |
            (Company.email.ilike(f'%{search_query}%')) |
            (Company.gstin.ilike(f'%{search_query}%'))
        )
    
    # Paginate with a strict limit of 10 companies per page
    pagination = query.order_by(Company.created_at.desc()).paginate(page=page, per_page=10)
    
    return render_template(
        'admin/companies.html', 
        pagination=pagination, 
        search_query=search_query
    )

@admin_bp.route('/companies/add', methods=['POST'])
def add_company():
    if not is_logged_in(): return redirect(url_for('admin.login'))
    
    name = request.form.get('name').strip()
    login_id = request.form.get('login_id').strip()
    password = request.form.get('password')
    
    # --- GRAB NEW FIELDS ---
    address = request.form.get('address').strip()
    gstin = request.form.get('gstin').strip()
    email = request.form.get('email').strip()
    
    if Company.query.filter_by(login_id=login_id).first():
        flash("That Login ID is already taken. Choose another.", "danger")
        return redirect(url_for('admin.manage_companies'))
        
    logo_file = request.files.get('logo')
    logo_path = None
    if logo_file and logo_file.filename != '':
        filename = secure_filename(f"{login_id}_{logo_file.filename}")
        upload_dir = os.path.join(current_app.root_path, 'static', 'logos')
        os.makedirs(upload_dir, exist_ok=True)
        logo_file.save(os.path.join(upload_dir, filename))
        logo_path = f'logos/{filename}'

    new_company = Company(
        name=name,
        login_id=login_id,
        password_hash=generate_password_hash(password),
        logo_path=logo_path,
        address=address, # Save Address
        gstin=gstin,     # Save GSTIN
        email=email      # Save Email
    )
    db.session.add(new_company)
    db.session.commit()
    flash(f"Company '{name}' registered successfully!", "success")
    
    return redirect(url_for('admin.manage_companies'))



@admin_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if not is_logged_in(): return redirect(url_for('admin.login'))
    
    # Get the existing settings, or create an empty object if none exists
    smtp = SMTPSettings.query.first()
    
    if request.method == 'POST':
        if not smtp:
            smtp = SMTPSettings()
            db.session.add(smtp)
            
        smtp.server = request.form.get('server').strip()
        smtp.port = int(request.form.get('port', 587))
        smtp.username = request.form.get('username').strip()
        smtp.password = request.form.get('password').strip()
        smtp.sender_email = request.form.get('sender_email').strip()
        smtp.use_tls = 'use_tls' in request.form
        
        db.session.commit()
        flash("System SMTP settings updated successfully!", "success")
        return redirect(url_for('admin.settings'))
        
    return render_template('admin/settings.html', smtp=smtp)

@admin_bp.route('/upload-master-excel', methods=['POST'])
def upload_master_excel():
    """
    Developer tool: Upload the official HSN/SAC .xlsx file.
    Reads the first two columns (Code and Description) and seeds the DB.
    """
    if 'file' not in request.files:
        flash("No file uploaded.", "danger")
        return redirect(url_for('admin.dashboard')) # Adjust to your settings page
        
    file = request.files['file']
    if file.filename == '':
        flash("No file selected.", "danger")
        return redirect(url_for('admin.dashboard'))

    # Check for Excel file extensions
    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        try:
            # Read the Excel file into a Pandas DataFrame
            # engine='openpyxl' is required for .xlsx files
            df = pd.read_excel(file, engine='openpyxl')
            
            count = 0
            
            # Iterate through the rows in the dataframe
            for index, row in df.iterrows():
                # We assume Column 1 (index 0) is Code, Column 2 (index 1) is Description
                if pd.notna(row.iloc[0]) and pd.notna(row.iloc[1]):
                    # Convert to string and strip whitespace
                    code = str(row.iloc[0]).strip()
                    desc = str(row.iloc[1]).strip()
                    
                    if not code or not desc:
                        continue

                    # Prevent duplicate crashes
                    existing = HSNDictionary.query.filter_by(hsn_code=code).first()
                    if not existing:
                        new_entry = HSNDictionary(
                            hsn_code=code,
                            description=desc,
                            gst_rate=0.0  # Default to 0, seller fills this manually
                        )
                        db.session.add(new_entry)
                        count += 1
                        
                        # Commit in batches of 1000 to keep memory stable
                        if count % 1000 == 0:
                            db.session.commit()

            # Final commit for the remaining rows
            db.session.commit()
            flash(f"Success! Imported {count} new codes from Excel.", "success")
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error processing Excel: {str(e)}", "danger")
            
    else:
        flash("Please upload a valid .xlsx or .xls file.", "warning")
        
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/delete-all-hsn', methods=['POST'])
def delete_all_hsn():
    """
    Developer tool: Wipes the entire HSNDictionary table clean.
    """
    try:
        # Bulk delete all rows in the table
        num_deleted = db.session.query(HSNDictionary).delete()
        db.session.commit()
        
        flash(f"Successfully deleted all {num_deleted} HSN/SAC codes from the database.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error wiping database: {str(e)}", "danger")
        
    # Adjust 'admin.dashboard' if your blueprint is named differently (e.g., 'developer.dashboard')
    return redirect(url_for('admin.dashboard'))