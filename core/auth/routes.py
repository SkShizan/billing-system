from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from core.models import Company

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
            flash(f"Welcome back, {company.name}!", "success")
            return redirect(url_for('billing.index'))
        else:
            flash("Invalid Login ID or Password.", "danger")
            
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    session.pop('company_id', None)
    session.pop('company_name', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('auth.login'))