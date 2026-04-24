import os
from flask import Flask, redirect, url_for, session
from .extensions import db

def create_app():
    app = Flask(__name__)
    
    # 🎯 PRODUCTION DATABASE SWITCH: 
    # If a production DB URL exists, use it. Otherwise, safely fall back to local SQLite.
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///billing.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # REQUIRED FOR LOGIN SESSIONS
    app.config['SECRET_KEY'] = 'super-secret-developer-key-change-in-production'

    db.init_app(app)

    # Import and register Blueprints
    from .auth.routes import auth_bp
    from .inventory.routes import inventory_bp
    from .billing.routes import billing_bp
    from .admin.routes import admin_bp
    
    # 🎯 FOOLPROOF IMPORT: Catches the blueprint whether it's named settings_bp or settings
    try:
        from .settings.routes import settings_bp
        app.register_blueprint(settings_bp)
    except ImportError:
        from .settings.routes import settings
        app.register_blueprint(settings)

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(billing_bp, url_prefix='/billing')
    app.register_blueprint(admin_bp, url_prefix='/developer')

    # --- THE SECURE TRAFFIC COP ---
    @app.route('/')
    def home():
        # 1. Check if a regular company is logged in
        if 'company_id' in session:
            return redirect(url_for('billing.dashboard')) 
        
        # 2. Check if the developer is logged in
        elif 'is_developer' in session:
            return redirect(url_for('admin.dashboard'))
            
        # 3. If nobody is logged in, force them to the Company login page!
        return redirect(url_for('auth.login'))

    # Create tables if they don't exist
    with app.app_context():
        db.create_all()

    return app