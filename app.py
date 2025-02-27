import json, ast
from flask import Flask
from routes import bp as routes_bp
from database import init_db
from projects import projects_bp

def create_app():
    app = Flask(__name__)
    
    # Register blueprints
    app.register_blueprint(routes_bp)
    app.register_blueprint(projects_bp)
    
    # Initialize main database
    init_db()
    
    # Register a custom filter 'fromjson'
    def fromjson_filter(s):
        try:
            return json.loads(s)
        except Exception:
            try:
                return ast.literal_eval(s)
            except Exception:
                return {}
    app.jinja_env.filters['fromjson'] = fromjson_filter
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
