from flask import Flask, redirect, url_for, session  # <-- Make sure session is imported!
from .extensions import db

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///billing.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # REQUIRED FOR LOGIN SESSIONS
    app.config['SECRET_KEY'] = 'super-secret-developer-key-change-in-production'

    db.init_app(app)

    from .auth.routes import auth_bp
    from .inventory.routes import inventory_bp
    from .billing.routes import billing_bp
    from .admin.routes import admin_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(billing_bp, url_prefix='/billing')
    app.register_blueprint(admin_bp, url_prefix='/developer')

    # --- THE SECURE TRAFFIC COP ---
    @app.route('/')
    def home():
        # Check if a regular company is logged in
        if 'company_id' in session:
            return redirect(url_for('billing.index'))
        
        # Check if the developer is logged in
        elif 'is_developer' in session:
            return redirect(url_for('admin.dashboard'))
            
        # If nobody is logged in, force them to the Company login page!
        return redirect(url_for('auth.login'))

    with app.app_context():
        db.create_all()

    return app