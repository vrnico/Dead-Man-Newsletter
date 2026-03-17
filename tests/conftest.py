import os
os.environ['TESTING'] = '1'  # Must be set before app import to suppress init_db() and scheduler.start()

import tempfile
import pytest
import database as db_module
from app import app as flask_app


@pytest.fixture
def app(monkeypatch):
    """Create a fresh app with a temp SQLite DB for each test."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    monkeypatch.setattr(db_module, 'DB_PATH', db_path)

    # Set required env vars so SMTP check passes
    monkeypatch.setenv('SMTP_USER', 'test@example.com')
    monkeypatch.setenv('SMTP_PASSWORD', 'testpass')

    flask_app.config.update({'TESTING': True, 'SECRET_KEY': 'test-secret-key', 'WTF_CSRF_ENABLED': False})

    db_module.init_db()

    yield flask_app

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    conn = db_module.get_db()
    yield conn
    conn.close()
