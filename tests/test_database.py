import sqlite3
import database as db_module


def test_settings_table_exists(db):
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='settings'"
    ).fetchone()
    assert row is not None, "settings table should exist"


def test_settings_default_keys_seeded(db):
    keys = {r['key'] for r in db.execute("SELECT key FROM settings").fetchall()}
    expected = {
        'base_url', 'header_image_url', 'footer_image_url',
        'default_font', 'tracking_pixel_enabled',
        'url_shortener_enabled', 'url_shortener_provider',
        'url_shortener_api_key', 'url_shortener_bitly_group',
    }
    assert expected.issubset(keys)


def test_settings_default_font_value(db):
    row = db.execute("SELECT value FROM settings WHERE key='default_font'").fetchone()
    assert row['value'] == 'Georgia, serif'


def test_contacts_has_unsubscribe_token_column(db):
    cols = [r['name'] for r in db.execute("PRAGMA table_info(contacts)").fetchall()]
    assert 'unsubscribe_token' in cols


def test_sends_has_open_count_column(db):
    cols = [r['name'] for r in db.execute("PRAGMA table_info(sends)").fetchall()]
    assert 'open_count' in cols


def test_new_contact_gets_unsubscribe_token(client):
    """New contacts added via the /contacts/add route must get a token."""
    resp = client.post('/contacts/add', data={
        'email': 'new@example.com', 'name': 'New', 'groups': ''
    }, follow_redirects=True)
    assert resp.status_code == 200

    import database as db_module
    conn = db_module.get_db()
    row = conn.execute(
        "SELECT unsubscribe_token FROM contacts WHERE email='new@example.com'"
    ).fetchone()
    conn.close()
    assert row['unsubscribe_token'] is not None
    assert len(row['unsubscribe_token']) == 32  # hex(randomblob(16))


def test_existing_contacts_backfilled(db):
    """All contacts inserted by init_db seed should have tokens."""
    rows = db.execute(
        "SELECT unsubscribe_token FROM contacts WHERE unsubscribe_token IS NULL"
    ).fetchall()
    assert len(rows) == 0


def test_init_db_idempotent(app, monkeypatch):
    """Running init_db() twice should not raise or duplicate settings rows."""
    import database as db_module
    db_module.init_db()  # second call
    conn = db_module.get_db()
    count = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
    conn.close()
    # Should still have exactly the 9 default keys
    assert count == 9
