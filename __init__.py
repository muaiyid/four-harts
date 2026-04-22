import os
from pathlib import Path
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash
from datetime import datetime


db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    base_dir = Path(__file__).resolve().parent.parent
    instance_dir = base_dir / 'instance'
    instance_dir.mkdir(exist_ok=True)
    db_path = os.getenv('DATABASE_PATH', str(instance_dir / 'four_harts.db'))

    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-this-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', f'sqlite:///{db_path}')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    from .models import User
    from .routes import main_bp
    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password_hash=generate_password_hash(os.getenv('ADMIN_PASSWORD', 'admin123')),
                full_name='Four Harts Owner',
                created_at=datetime.utcnow(),
            )
            db.session.add(admin)
            db.session.commit()

    return app
