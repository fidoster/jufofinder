from flask import Flask
from routes import bp as routes_bp
from database import init_db

def create_app():
    app = Flask(__name__)
    
    # Register blueprints
    app.register_blueprint(routes_bp)
    
    # Initialize database
    init_db()
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)