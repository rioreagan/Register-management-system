from flask import Flask
from jinja2 import select_autoescape

def create_app():
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_pyfile("config.py")
    app.secret_key = app.config["SECRET_KEY"]
    app.jinja_env.autoescape = select_autoescape(["html", "xml"])
    
    # Initialize Database on Startup
    from app.database import init_db, seed_demo_data
    with app.app_context():
        init_db()
        seed_demo_data()
        
    # before_request hook to auto-close expired sessions
    from app.database import close_expired_sessions
    @app.before_request
    def before_request():
        close_expired_sessions()
        
    # Context processor to inject global variables
    from app.auth import get_current_user
    @app.context_processor
    def inject_globals():
        return {
            "current_user": get_current_user(),
            "low_threshold": app.config["LOW_ATTENDANCE_THRESHOLD"],
        }
        
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.student import student_bp
    from app.routes.lecturer import lecturer_bp
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(lecturer_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    
    return app
