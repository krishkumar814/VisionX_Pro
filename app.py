from flask import Flask, render_template
from config import Config
from models import db, User
from flask_login import LoginManager
from flask_bcrypt import Bcrypt

# Import all Blueprints
from routes.auth import auth as auth_blueprint
from routes.teacher import teacher as teacher_blueprint
from routes.student import student as student_blueprint
from routes.hod_director import hod_director as hod_blueprint # Renamed for clarity
from routes.analytics import analytics_bp

app = Flask(__name__)
app.config.from_object(Config)

# 1. Initialize extensions FIRST
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# 2. Register Blueprints ONCE
app.register_blueprint(auth_blueprint)
app.register_blueprint(teacher_blueprint)
app.register_blueprint(student_blueprint)
app.register_blueprint(hod_blueprint) # This is the key registration
app.register_blueprint(analytics_bp)

# Home Route
@app.route('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(role='Technical Head').first():
            admin = User(
                username="Admin",
                email="admin@visionx.com",
                password_hash=bcrypt.generate_password_hash("admin123").decode('utf-8'),
                role="Technical Head"
            )
            db.session.add(admin)
            db.session.commit()
            print("Default Technical Head created: admin@visionx.com / admin123")

    app.run(debug=True)