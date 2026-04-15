from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from core.models import Company
from datetime import datetime, timedelta
from core.extensions import db
from core.utils import generate_otp, send_otp_email 

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_id = request.form.get('login_id')
        password = request.form.get('password')
        
        # Find the company by Login ID
        company = Company.query.filter_by(login_id=login_id).first()
        
        if company and check_password_hash(company.password_hash, password):
            # Log the company in by storing their ID in the secure session
            session['company_id'] = company.id
            session['company_name'] = company.name
            session['company_logo'] = company.logo_path # 🎯 ADD THIS LINE
            flash(f"Welcome back, {company.name}!", "success")
            return redirect(url_for('billing.dashboard'))
        else:
            flash("Invalid Login ID or Password.", "danger")
            
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    session.pop('company_id', None)
    session.pop('company_name', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('auth.login'))

# Import the email engine we built

# ... (keep your existing login/logout routes) ...

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email').strip()
        company = Company.query.filter_by(email=email).first()
        
        if company:
            # Generate a 6-digit OTP and set expiry to 10 minutes from now
            otp = generate_otp()
            company.reset_otp = otp
            company.reset_otp_expiry = datetime.utcnow() + timedelta(minutes=10)
            db.session.commit()
            
            # Send the email
            success, message = send_otp_email(company.email, company.name, otp)
            
            if success:
                # Store email in session briefly to carry over to the verify page
                session['reset_email'] = company.email 
                flash("An OTP has been sent to your email address.", "success")
                return redirect(url_for('auth.verify_otp'))
            else:
                flash(f"Failed to send email: {message}", "danger")
        else:
            # For security, we don't confirm if the email exists or not to prevent scraping
            flash("If that email exists in our system, an OTP has been sent.", "info")
            
    return render_template('auth/forgot_password.html')

@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = session.get('reset_email')
    if not email:
        return redirect(url_for('auth.forgot_password'))
        
    if request.method == 'POST':
        otp_entered = request.form.get('otp').strip()
        new_password = request.form.get('new_password')
        
        company = Company.query.filter_by(email=email).first()
        
        if not company or company.reset_otp != otp_entered:
            flash("Invalid OTP.", "danger")
            return redirect(url_for('auth.verify_otp'))
            
        if datetime.utcnow() > company.reset_otp_expiry:
            flash("OTP has expired. Please request a new one.", "warning")
            return redirect(url_for('auth.forgot_password'))
            
        # OTP is valid! Reset the password
        company.password_hash = generate_password_hash(new_password)
        company.reset_otp = None # Clear the OTP so it can't be reused
        company.reset_otp_expiry = None
        db.session.commit()
        
        # Clear the session email
        session.pop('reset_email', None)
        
        flash("Password reset successfully! You can now log in.", "success")
        return redirect(url_for('auth.login'))
        
    return render_template('auth/verify_otp.html', email=email)