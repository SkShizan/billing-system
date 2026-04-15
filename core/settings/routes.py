import os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from core.models import Company
from core.extensions import db
from flask import jsonify
from datetime import datetime, timedelta
from core.utils import generate_otp, send_otp_email

# Create the new blueprint with a clean URL prefix
settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/', methods=['GET', 'POST'])
def index():
    company_id = session.get('company_id')
    if not company_id:
        return redirect(url_for('auth.login'))

    company = Company.query.get_or_404(company_id)

    if request.method == 'POST':
        # 1. Update Basic Info
        company.name = request.form.get('name', company.name).strip()
        company.email = request.form.get('email', company.email).strip()
        company.address = request.form.get('address', company.address).strip()
        company.gstin = request.form.get('gstin', company.gstin).strip()

        # 2. Handle Logo Upload
        logo_file = request.files.get('logo')
        if logo_file and logo_file.filename != '':
            filename = secure_filename(f"tenant_{company.id}_{logo_file.filename}")
            upload_dir = os.path.join(current_app.root_path, 'static', 'logos')
            os.makedirs(upload_dir, exist_ok=True)
            logo_file.save(os.path.join(upload_dir, filename))
            company.logo_path = f'logos/{filename}'

        # 3. Handle Secure OTP Password Change
        otp_entered = request.form.get('otp')
        new_password = request.form.get('new_password')
        
        if otp_entered and new_password:
            if company.reset_otp == otp_entered.strip() and company.reset_otp_expiry > datetime.utcnow():
                company.password_hash = generate_password_hash(new_password)
                company.reset_otp = None # Clear OTP
                company.reset_otp_expiry = None
                flash("Profile and Password updated securely!", "success")
            else:
                flash("Profile updated, but Password change failed (Invalid or Expired OTP).", "danger")
        else:
            flash("Workspace settings updated successfully!", "success")

        db.session.commit()
        session['company_name'] = company.name 
        session['company_logo'] = company.logo_path # 🎯 ADD THIS LINE
        return redirect(url_for('settings.index'))

    return render_template('settings/index.html', company=company)

# 🎯 NEW: AJAX Route to trigger the OTP from the Settings page
@settings_bp.route('/request-otp', methods=['POST'])
def request_otp():
    company_id = session.get('company_id')
    if not company_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    company = Company.query.get(company_id)
    
    otp = generate_otp()
    company.reset_otp = otp
    company.reset_otp_expiry = datetime.utcnow() + timedelta(minutes=10)
    db.session.commit()
    
    success, message = send_otp_email(company.email, company.name, otp)
    return jsonify({'success': success, 'message': message})