# Email Improvements Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tracking pixel, rich HTML templates, header/footer images, Quill rich text editing, font selection, unsubscribe, URL shortener (Bit.ly + TinyURL), settings page, Docker containerization, and deployment docs to Dead-Man-Newsletter.

**Architecture:** A new `email_builder.py` module composes every outgoing email (font wrapper, header/footer images, unsubscribe footer, tracking pixel). A new `shortener.py` module optionally rewrites hrefs using Bit.ly or TinyURL before the email is built. All user preferences live in a new `settings` DB table; SMTP secrets stay in `.env`.

**Tech Stack:** Python 3.12, Flask, SQLite (via `sqlite3`), Jinja2, smtplib, Quill.js v1.3.7 (CDN), gunicorn, Docker

**Spec:** `docs/superpowers/specs/2026-03-16-email-improvements-design.md`

---

## Chunk 1: Foundation

---

### Task 1: Test Infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`
- Modify: `requirements.txt`

- [ ] **Step 1.1: Add pytest to requirements.txt**

Open `requirements.txt` and append:
```
pytest==8.3.5
pytest-flask==1.3.0
```

- [ ] **Step 1.2: Create pytest.ini**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

- [ ] **Step 1.3: Create tests/__init__.py**

Empty file.

- [ ] **Step 1.4: Create tests/conftest.py**

```python
import os
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

    flask_app.config.update({'TESTING': True, 'SECRET_KEY': 'test-secret-key'})

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
```

- [ ] **Step 1.5: Install dependencies and verify pytest runs**

```bash
pip install pytest==8.3.5 pytest-flask==1.3.0
pytest --collect-only
```

Expected output: `no tests ran` with exit code 5 (no tests yet — that's fine).

- [ ] **Step 1.6: Commit**

```bash
git add requirements.txt pytest.ini tests/
git commit -m "chore: add pytest test infrastructure"
```

---

### Task 2: DB Migration

**Files:**
- Modify: `database.py`
- Create: `tests/test_database.py`

- [ ] **Step 2.1: Write failing tests**

Create `tests/test_database.py`:
```python
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
```

- [ ] **Step 2.2: Run tests to confirm they fail**

```bash
pytest tests/test_database.py -v
```

Expected: All 8 tests FAIL (columns and table don't exist yet).

- [ ] **Step 2.3: Add settings table to init_db() executescript**

In `database.py`, inside the `executescript` string in `init_db()`, add after the `deadman_switch` table:

```python
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL DEFAULT ''
        );
```

- [ ] **Step 2.4: Add migration guards for contacts.unsubscribe_token**

After `conn.executescript(...)` and before the existing seed checks, add:

```python
    # Migrate: add unsubscribe_token to contacts if missing
    existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(contacts)").fetchall()]
    if 'unsubscribe_token' not in existing_cols:
        conn.execute("ALTER TABLE contacts ADD COLUMN unsubscribe_token TEXT")
        conn.execute(
            "UPDATE contacts SET unsubscribe_token = lower(hex(randomblob(16))) "
            "WHERE unsubscribe_token IS NULL"
        )
        conn.commit()

    # Migrate: add open_count to sends if missing
    existing_send_cols = [r[1] for r in conn.execute("PRAGMA table_info(sends)").fetchall()]
    if 'open_count' not in existing_send_cols:
        conn.execute(
            "ALTER TABLE sends ADD COLUMN open_count INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()
```

- [ ] **Step 2.5: Seed default settings if table is empty**

After the existing deadman seed block, add:

```python
    # Seed default settings if empty
    if conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
        defaults = [
            ('base_url', ''),
            ('header_image_url', ''),
            ('footer_image_url', ''),
            ('default_font', 'Georgia, serif'),
            ('tracking_pixel_enabled', '0'),
            ('url_shortener_enabled', '0'),
            ('url_shortener_provider', 'bitly'),
            ('url_shortener_api_key', ''),
            ('url_shortener_bitly_group', ''),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", defaults
        )
        conn.commit()
```

- [ ] **Step 2.6: Generate unsubscribe_token on new contact insert**

In `add_contact()` in `app.py`, change the INSERT to include `unsubscribe_token`:

```python
    db.execute(
        "INSERT INTO contacts (email, name, groups, unsubscribe_token) VALUES (?, ?, ?, lower(hex(randomblob(16))))",
        (email, name, json.dumps(group_list))
    )
```

Do the same in `import_contacts()`:

```python
    db.execute(
        "INSERT INTO contacts (email, name, groups, unsubscribe_token) VALUES (?, ?, ?, lower(hex(randomblob(16))))",
        (email, name, json.dumps(groups))
    )
```

- [ ] **Step 2.7: Run tests to confirm they pass**

```bash
pytest tests/test_database.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 2.8: Commit**

```bash
git add database.py app.py tests/test_database.py
git commit -m "feat: add settings table and migrate contacts/sends schema"
```

---

### Task 3: Settings Route and Page

**Files:**
- Modify: `app.py`
- Create: `templates/settings.html`
- Modify: `templates/base.html`
- Create: `tests/test_settings_route.py`

- [ ] **Step 3.1: Write failing tests**

Create `tests/test_settings_route.py`:
```python
import json


def test_settings_get_returns_200(client):
    resp = client.get('/settings')
    assert resp.status_code == 200


def test_settings_page_contains_sections(client):
    resp = client.get('/settings')
    html = resp.data.decode()
    assert 'base_url' in html
    assert 'default_font' in html
    assert 'tracking_pixel_enabled' in html
    assert 'url_shortener_enabled' in html


def test_settings_post_saves_values(client, db):
    resp = client.post('/settings', data={
        'base_url': 'https://example.com',
        'default_font': 'Arial, sans-serif',
        'header_image_url': '',
        'footer_image_url': '',
        'tracking_pixel_enabled': '1',
        'url_shortener_enabled': '0',
        'url_shortener_provider': 'bitly',
        'url_shortener_api_key': 'abc123',
        'url_shortener_bitly_group': '',
    }, follow_redirects=True)
    assert resp.status_code == 200

    base_url = db.execute(
        "SELECT value FROM settings WHERE key='base_url'"
    ).fetchone()['value']
    assert base_url == 'https://example.com'

    font = db.execute(
        "SELECT value FROM settings WHERE key='default_font'"
    ).fetchone()['value']
    assert font == 'Arial, sans-serif'


def test_settings_post_saves_tracking_off_when_checkbox_missing(client, db):
    """Unchecked checkboxes are not sent in form data — value should be '0'."""
    client.post('/settings', data={
        'base_url': '',
        'default_font': 'Georgia, serif',
        'header_image_url': '',
        'footer_image_url': '',
        # tracking_pixel_enabled NOT in form data (unchecked)
        'url_shortener_enabled': '0',
        'url_shortener_provider': 'bitly',
        'url_shortener_api_key': '',
        'url_shortener_bitly_group': '',
    })
    row = db.execute(
        "SELECT value FROM settings WHERE key='tracking_pixel_enabled'"
    ).fetchone()
    assert row['value'] == '0'


def test_settings_warning_shown_when_tracking_enabled_no_base_url(client):
    client.post('/settings', data={
        'base_url': '',
        'default_font': 'Georgia, serif',
        'header_image_url': '',
        'footer_image_url': '',
        'tracking_pixel_enabled': '1',
        'url_shortener_enabled': '0',
        'url_shortener_provider': 'bitly',
        'url_shortener_api_key': '',
        'url_shortener_bitly_group': '',
    })
    resp = client.get('/settings')
    assert b'requires the app to be publicly accessible' in resp.data
```

- [ ] **Step 3.2: Run tests to confirm they fail**

```bash
pytest tests/test_settings_route.py -v
```

Expected: All 5 tests FAIL (route doesn't exist).

- [ ] **Step 3.3: Add get_settings helper to database.py**

At the bottom of `database.py`, add:

```python
def get_settings(conn):
    """Return all settings as a plain dict {key: value}."""
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r['key']: r['value'] for r in rows}
```

- [ ] **Step 3.4: Add /settings routes to app.py**

Add this import at the top of `app.py`:
```python
from database import get_db, init_db, get_settings
```

Add the routes (place near the bottom, before `if __name__ == '__main__'`):

```python
# ============================================================
# SETTINGS
# ============================================================

SETTINGS_KEYS = [
    'base_url', 'header_image_url', 'footer_image_url',
    'default_font', 'tracking_pixel_enabled',
    'url_shortener_enabled', 'url_shortener_provider',
    'url_shortener_api_key', 'url_shortener_bitly_group',
]

FONT_OPTIONS = [
    {'value': 'Georgia, serif',         'label': 'Georgia (serif)'},
    {'value': 'Arial, sans-serif',      'label': 'Arial (sans-serif)'},
    {'value': 'Helvetica, sans-serif',  'label': 'Helvetica (sans-serif)'},
    {'value': 'Verdana, sans-serif',    'label': 'Verdana (sans-serif)'},
    {'value': 'Times New Roman, serif', 'label': 'Times New Roman (serif)'},
    {'value': 'Trebuchet MS, sans-serif','label': 'Trebuchet MS (sans-serif)'},
    {'value': 'Courier New, monospace', 'label': 'Courier New (monospace)'},
]


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    db = get_db()
    if request.method == 'POST':
        for key in SETTINGS_KEYS:
            # Checkboxes: if not in form, value is '0'
            if key in ('tracking_pixel_enabled', 'url_shortener_enabled'):
                value = '1' if request.form.get(key) else '0'
            else:
                value = request.form.get(key, '').strip()
            db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )
        db.commit()
        flash('Settings saved.', 'success')
        db.close()
        return redirect(url_for('settings'))

    s = get_settings(db)
    db.close()

    base_url = s.get('base_url', '')
    tracking_enabled = s.get('tracking_pixel_enabled') == '1'
    show_tracking_warning = tracking_enabled and (
        not base_url or base_url.startswith('http://localhost') or
        base_url.startswith('http://127.')
    )

    return render_template('settings.html',
                           settings=s,
                           fonts=FONT_OPTIONS,
                           show_tracking_warning=show_tracking_warning)
```

- [ ] **Step 3.5: Create templates/settings.html**

```html
{% extends "base.html" %}
{% block content %}
<h2>Settings</h2>

<form method="post">

  <!-- Email Appearance -->
  <div class="card mb-4">
    <div class="card-header"><strong>📧 Email Appearance</strong></div>
    <div class="card-body">

      <div class="mb-3">
        <label class="form-label fw-bold">Base URL</label>
        <input type="text" name="base_url" class="form-control"
               value="{{ settings.base_url }}"
               placeholder="https://newsletter.example.com">
        <div class="form-text">Required for tracking pixel and unsubscribe links to work from inside email clients.</div>
      </div>

      <div class="mb-3">
        <label class="form-label fw-bold">Default Font</label>
        <select name="default_font" class="form-select">
          {% for f in fonts %}
          <option value="{{ f.value }}" {% if settings.default_font == f.value %}selected{% endif %}>{{ f.label }}</option>
          {% endfor %}
        </select>
        <div class="form-text">Can be overridden at send time for each email.</div>
      </div>

      <div class="mb-3">
        <label class="form-label fw-bold">Header Image URL</label>
        <input type="text" name="header_image_url" class="form-control"
               value="{{ settings.header_image_url }}"
               placeholder="https://example.com/header.png">
        <div class="form-text">Shown at the top of every email. Leave blank to disable.</div>
      </div>

      <div class="mb-3">
        <label class="form-label fw-bold">Footer Image URL</label>
        <input type="text" name="footer_image_url" class="form-control"
               value="{{ settings.footer_image_url }}"
               placeholder="https://example.com/footer.png">
        <div class="form-text">Shown above the unsubscribe link in every email.</div>
      </div>

    </div>
  </div>

  <!-- Open Tracking -->
  <div class="card mb-4">
    <div class="card-header"><strong>📊 Open Tracking</strong></div>
    <div class="card-body">

      {% if show_tracking_warning %}
      <div class="alert alert-warning">
        ⚠️ Tracking requires the app to be publicly accessible. Set a Base URL above, or leave tracking off for local use.
      </div>
      {% endif %}

      <div class="form-check form-switch mb-2">
        <input class="form-check-input" type="checkbox" name="tracking_pixel_enabled"
               id="tracking_pixel_enabled" value="1"
               {% if settings.tracking_pixel_enabled == '1' %}checked{% endif %}>
        <label class="form-check-label fw-bold" for="tracking_pixel_enabled">
          Track email opens (tracking pixel)
        </label>
      </div>
      <div class="form-text">Embeds a 1×1 invisible image. Open count shown in send history.</div>

    </div>
  </div>

  <!-- URL Shortener -->
  <div class="card mb-4">
    <div class="card-header"><strong>🔗 URL Shortener</strong></div>
    <div class="card-body">

      <div class="form-check form-switch mb-3">
        <input class="form-check-input" type="checkbox" name="url_shortener_enabled"
               id="url_shortener_enabled" value="1"
               {% if settings.url_shortener_enabled == '1' %}checked{% endif %}>
        <label class="form-check-label fw-bold" for="url_shortener_enabled">
          Auto-shorten links in emails
        </label>
      </div>

      <div class="mb-3">
        <label class="form-label fw-bold">Provider</label>
        <select name="url_shortener_provider" class="form-select" id="shortener_provider">
          <option value="bitly"   {% if settings.url_shortener_provider == 'bitly' %}selected{% endif %}>Bit.ly</option>
          <option value="tinyurl" {% if settings.url_shortener_provider == 'tinyurl' %}selected{% endif %}>TinyURL</option>
        </select>
      </div>

      <div class="mb-3">
        <label class="form-label fw-bold">API Key</label>
        <input type="password" name="url_shortener_api_key" class="form-control"
               value="{{ settings.url_shortener_api_key }}"
               placeholder="Your API key">
      </div>

      <div class="mb-3" id="bitly_group_row"
           style="{% if settings.url_shortener_provider != 'bitly' %}display:none{% endif %}">
        <label class="form-label fw-bold">Bit.ly Group GUID</label>
        <input type="text" name="url_shortener_bitly_group" class="form-control"
               value="{{ settings.url_shortener_bitly_group }}"
               placeholder="Bj1abc...">
        <div class="form-text">Found in your bit.ly account settings under Groups.</div>
      </div>

      <div class="alert alert-info py-2 mb-0">
        🔍 View click analytics at <a href="https://app.bitly.com" target="_blank">app.bitly.com → Links</a>
      </div>

    </div>
  </div>

  <button type="submit" class="btn btn-primary">Save Settings</button>

</form>

<script>
document.getElementById('shortener_provider').addEventListener('change', function() {
  document.getElementById('bitly_group_row').style.display =
    this.value === 'bitly' ? '' : 'none';
});
</script>
{% endblock %}
```

- [ ] **Step 3.6: Add Settings link to templates/base.html**

In `templates/base.html`, find the nav links section and add:
```html
<a href="{{ url_for('settings') }}">Settings</a>
```

alongside the existing nav links (Dashboard, Contacts, Templates, History, Dead Man's Switch).

- [ ] **Step 3.7: Run tests to confirm they pass**

```bash
pytest tests/test_settings_route.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 3.8: Commit**

```bash
git add database.py app.py templates/settings.html templates/base.html tests/test_settings_route.py
git commit -m "feat: add settings route and page with email appearance, tracking, and shortener config"
```

---

### Task 4: email_builder.py

**Files:**
- Create: `email_builder.py`
- Create: `tests/test_email_builder.py`

- [ ] **Step 4.1: Write failing tests**

Create `tests/test_email_builder.py`:
```python
import email_builder


BASE_SETTINGS = {
    'base_url': 'https://example.com',
    'header_image_url': '',
    'footer_image_url': '',
    'default_font': 'Georgia, serif',
    'tracking_pixel_enabled': '0',
}


def test_returns_complete_html_document():
    html = email_builder.build_email(
        body='<p>Hello</p>',
        settings=BASE_SETTINGS,
        unsubscribe_token='abc123',
        send_id=1,
        recipient_email='user@example.com',
        secret_key='secret',
    )
    assert html.startswith('<!DOCTYPE html>')
    assert '<p>Hello</p>' in html


def test_applies_font_to_wrapper():
    settings = {**BASE_SETTINGS, 'default_font': 'Arial, sans-serif'}
    html = email_builder.build_email(
        body='<p>Hi</p>', settings=settings,
        unsubscribe_token='tok', send_id=1,
        recipient_email='u@example.com', secret_key='s',
    )
    assert 'Arial, sans-serif' in html


def test_font_parameter_overrides_settings():
    html = email_builder.build_email(
        body='<p>Hi</p>', settings=BASE_SETTINGS,
        unsubscribe_token='tok', send_id=1,
        recipient_email='u@example.com', secret_key='s',
        font='Verdana, sans-serif',
    )
    assert 'Verdana, sans-serif' in html
    assert 'Georgia' not in html  # default should not appear


def test_header_image_included_when_set():
    settings = {**BASE_SETTINGS, 'header_image_url': 'https://img.example.com/h.png'}
    html = email_builder.build_email(
        body='<p>Hi</p>', settings=settings,
        unsubscribe_token='tok', send_id=1,
        recipient_email='u@example.com', secret_key='s',
    )
    assert 'https://img.example.com/h.png' in html


def test_header_image_omitted_when_blank():
    html = email_builder.build_email(
        body='<p>Hi</p>', settings=BASE_SETTINGS,
        unsubscribe_token='tok', send_id=1,
        recipient_email='u@example.com', secret_key='s',
    )
    # No img tags other than potentially the pixel
    assert 'header' not in html.lower() or 'img' not in html


def test_footer_image_included_when_set():
    settings = {**BASE_SETTINGS, 'footer_image_url': 'https://img.example.com/f.png'}
    html = email_builder.build_email(
        body='<p>Hi</p>', settings=settings,
        unsubscribe_token='tok', send_id=1,
        recipient_email='u@example.com', secret_key='s',
    )
    assert 'https://img.example.com/f.png' in html


def test_unsubscribe_link_always_present():
    html = email_builder.build_email(
        body='<p>Hi</p>', settings=BASE_SETTINGS,
        unsubscribe_token='mytoken123', send_id=1,
        recipient_email='u@example.com', secret_key='s',
    )
    assert '/unsubscribe/mytoken123' in html


def test_tracking_pixel_omitted_when_disabled():
    html = email_builder.build_email(
        body='<p>Hi</p>', settings=BASE_SETTINGS,
        unsubscribe_token='tok', send_id=1,
        recipient_email='u@example.com', secret_key='s',
    )
    assert '/track/' not in html


def test_tracking_pixel_omitted_when_no_base_url():
    settings = {**BASE_SETTINGS, 'tracking_pixel_enabled': '1', 'base_url': ''}
    html = email_builder.build_email(
        body='<p>Hi</p>', settings=settings,
        unsubscribe_token='tok', send_id=1,
        recipient_email='u@example.com', secret_key='s',
    )
    assert '/track/' not in html


def test_tracking_pixel_present_when_enabled_with_base_url():
    settings = {**BASE_SETTINGS, 'tracking_pixel_enabled': '1'}
    html = email_builder.build_email(
        body='<p>Hi</p>', settings=settings,
        unsubscribe_token='tok', send_id=42,
        recipient_email='u@example.com', secret_key='s',
    )
    assert '/track/42/' in html
    assert '.gif' in html


def test_pixel_token_is_16_hex_chars():
    settings = {**BASE_SETTINGS, 'tracking_pixel_enabled': '1'}
    html = email_builder.build_email(
        body='<p>Hi</p>', settings=settings,
        unsubscribe_token='tok', send_id=1,
        recipient_email='u@example.com', secret_key='s',
    )
    import re
    match = re.search(r'/track/1/([0-9a-f]+)\.gif', html)
    assert match, "pixel URL should be in html"
    assert len(match.group(1)) == 16


def test_different_recipients_get_different_pixel_tokens():
    settings = {**BASE_SETTINGS, 'tracking_pixel_enabled': '1'}
    html1 = email_builder.build_email(
        body='<p>Hi</p>', settings=settings,
        unsubscribe_token='tok', send_id=1,
        recipient_email='alice@example.com', secret_key='s',
    )
    html2 = email_builder.build_email(
        body='<p>Hi</p>', settings=settings,
        unsubscribe_token='tok', send_id=1,
        recipient_email='bob@example.com', secret_key='s',
    )
    import re
    t1 = re.search(r'/track/1/([0-9a-f]+)\.gif', html1).group(1)
    t2 = re.search(r'/track/1/([0-9a-f]+)\.gif', html2).group(1)
    assert t1 != t2
```

- [ ] **Step 4.2: Run tests to confirm they fail**

```bash
pytest tests/test_email_builder.py -v
```

Expected: All 12 tests FAIL (`ModuleNotFoundError: No module named 'email_builder'`).

- [ ] **Step 4.3: Create email_builder.py**

```python
import hmac
import hashlib


def _make_pixel_token(send_id, recipient_email, secret_key):
    """Generate a 16-char hex HMAC token for the tracking pixel URL."""
    key = secret_key.encode() if isinstance(secret_key, str) else secret_key
    msg = f"{send_id}:{recipient_email}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:16]


def build_email(body, settings, unsubscribe_token, send_id, recipient_email,
                secret_key, font=None):
    """
    Compose a complete HTML email document.

    Args:
        body: Rendered HTML body content from the template.
        settings: Dict of app settings (from get_settings()).
        unsubscribe_token: Contact's unsubscribe UUID.
        send_id: Row ID of the sends table entry.
        recipient_email: Recipient's email address (used for HMAC).
        secret_key: App secret key for HMAC generation.
        font: Optional font override. If None, uses settings['default_font'].

    Returns:
        Complete <!DOCTYPE html> string ready to send.
    """
    chosen_font = font or settings.get('default_font', 'Georgia, serif')
    header_url = settings.get('header_image_url', '').strip()
    footer_url = settings.get('footer_image_url', '').strip()
    base_url = settings.get('base_url', '').strip()
    tracking_enabled = settings.get('tracking_pixel_enabled') == '1'

    parts = []

    # Header image
    if header_url:
        parts.append(
            f'<img src="{header_url}" '
            f'style="width:100%;max-width:600px;display:block;" alt="">'
        )

    # Body content
    parts.append(body)

    # Footer image
    if footer_url:
        parts.append(
            f'<img src="{footer_url}" '
            f'style="width:100%;max-width:600px;display:block;" alt="">'
        )

    # Unsubscribe footer
    unsubscribe_url = f'{base_url}/unsubscribe/{unsubscribe_token}'
    parts.append(
        f'<div style="text-align:center;padding:20px;font-size:12px;color:#999;">'
        f'<a href="{unsubscribe_url}" style="color:#999;">Unsubscribe</a>'
        f'&nbsp;&middot;&nbsp; Sent by NewsLetterGo'
        f'</div>'
    )

    # Tracking pixel (only if enabled and base_url is set)
    if tracking_enabled and base_url:
        token = _make_pixel_token(send_id, recipient_email, secret_key)
        parts.append(
            f'<img src="{base_url}/track/{send_id}/{token}.gif" '
            f'width="1" height="1" style="display:none;" alt="">'
        )

    content = '\n'.join(parts)

    return f'''<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:20px;background:#f5f5f5;">
  <div style="max-width:600px;margin:0 auto;font-family:{chosen_font};">
    {content}
  </div>
</body>
</html>'''
```

- [ ] **Step 4.4: Run tests to confirm they pass**

```bash
pytest tests/test_email_builder.py -v
```

Expected: All 12 tests PASS.

- [ ] **Step 4.5: Commit**

```bash
git add email_builder.py tests/test_email_builder.py
git commit -m "feat: add email_builder module with font, header/footer images, unsubscribe, and tracking pixel"
```

---

## Chunk 2: Core Email Features

---

### Task 5: Tracking Pixel Route

**Files:**
- Modify: `app.py`
- Modify: `templates/history.html`
- Modify: `templates/history_detail.html`
- Create: `tests/test_tracking_route.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/test_tracking_route.py`:
```python
import json


def _seed_send(db):
    """Insert a template and a send row, return send_id."""
    db.execute(
        "INSERT INTO templates (slug, name, subject_template, body_template, fields) "
        "VALUES ('test', 'Test', 'subj', '<p>body</p>', '[]')"
    )
    db.execute(
        "INSERT INTO sends (template_id, subject, body, recipient_count, open_count) "
        "VALUES (1, 'subj', '<p>body</p>', 1, 0)"
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_pixel_returns_gif(client, db):
    send_id = _seed_send(db)
    resp = client.get(f'/track/{send_id}/abcd1234abcd1234.gif')
    assert resp.status_code == 200
    assert resp.content_type == 'image/gif'


def test_pixel_increments_open_count(client, db):
    send_id = _seed_send(db)
    client.get(f'/track/{send_id}/abcd1234abcd1234.gif')
    count = db.execute(
        "SELECT open_count FROM sends WHERE id=?", (send_id,)
    ).fetchone()['open_count']
    assert count == 1


def test_pixel_unknown_send_id_still_returns_gif(client):
    resp = client.get('/track/99999/abcd1234abcd1234.gif')
    assert resp.status_code == 200
    assert resp.content_type == 'image/gif'


def test_pixel_invalid_token_format_still_returns_gif(client, db):
    send_id = _seed_send(db)
    resp = client.get(f'/track/{send_id}/not-valid-token.gif')
    assert resp.status_code == 200
    assert resp.content_type == 'image/gif'


def test_history_page_shows_open_count(client, db):
    send_id = _seed_send(db)
    db.execute("UPDATE sends SET open_count=7 WHERE id=?", (send_id,))
    db.commit()
    resp = client.get('/history')
    assert b'7' in resp.data
```

- [ ] **Step 5.2: Run tests to confirm they fail**

```bash
pytest tests/test_tracking_route.py -v
```

Expected: All 5 tests FAIL.

- [ ] **Step 5.3: Add tracking pixel constants and route to app.py**

Add these module-level imports at the top of `app.py` (with the existing imports):
```python
import re
import hashlib
import email_builder  # add alongside other local imports
```

Add `Response` to the existing Flask import line:
```python
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
```

Add the GIF bytes constant near the top of `app.py` (after imports):

```python
# 1x1 transparent GIF
TRACKING_GIF = (
    b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00'
    b'\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00'
    b'\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02'
    b'\x44\x01\x00\x3b'
)
```

Add the route (in the HISTORY section or its own section):

```python
# ============================================================
# TRACKING PIXEL
# ============================================================

@app.route('/track/<int:send_id>/<token>.gif')
def track_open(send_id, token):
    """
    Serve a 1x1 transparent GIF and increment open_count for the send.

    Token is a 16-char hex string derived from HMAC(send_id:email).
    We accept any 16-char hex token — we can't reverse-verify without the
    recipient email. The token acts as a modest forgery deterrent.
    Always returns the GIF (never reveals whether the send_id is valid).
    """
    if re.fullmatch(r'[0-9a-f]{16}', token):
        db = get_db()
        db.execute(
            "UPDATE sends SET open_count = open_count + 1 WHERE id = ?",
            (send_id,)
        )
        db.commit()
        db.close()

    return Response(
        TRACKING_GIF,
        mimetype='image/gif',
        headers={'Cache-Control': 'no-store, no-cache, must-revalidate'}
    )
```

- [ ] **Step 5.4: Update history.html to show open_count**

In `templates/history.html`, find the table that lists sends and add an "Opens" column header and cell. The sends query already returns all columns including `open_count`. Add to the table:

```html
<!-- In the <thead> row, add: -->
<th>Opens</th>

<!-- In each send row, add: -->
<td>{{ send.open_count }}</td>
```

- [ ] **Step 5.5: Update history_detail.html to show open_count**

In `templates/history_detail.html`, add a line showing the open count, e.g.:
```html
<p><strong>Opens:</strong> {{ send.open_count }}</p>
```

- [ ] **Step 5.6: Run tests to confirm they pass**

```bash
pytest tests/test_tracking_route.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5.7: Commit**

```bash
git add app.py templates/history.html templates/history_detail.html tests/test_tracking_route.py
git commit -m "feat: add tracking pixel route and open count to send history"
```

---

### Task 6: Unsubscribe Route and Page

**Files:**
- Modify: `app.py`
- Create: `templates/unsubscribe.html`
- Create: `tests/test_unsubscribe_route.py`

- [ ] **Step 6.1: Write failing tests**

Create `tests/test_unsubscribe_route.py`:
```python
import json


def _add_contact(db, email, token):
    db.execute(
        "INSERT INTO contacts (email, name, groups, unsubscribe_token) "
        "VALUES (?, '', '[]', ?)",
        (email, token)
    )
    db.commit()


def test_valid_token_unsubscribes_contact(client, db):
    _add_contact(db, 'user@example.com', 'validtoken123abc')
    client.get('/unsubscribe/validtoken123abc')
    row = db.execute(
        "SELECT unsubscribed FROM contacts WHERE email='user@example.com'"
    ).fetchone()
    assert row['unsubscribed'] == 1


def test_valid_token_returns_200(client, db):
    _add_contact(db, 'user2@example.com', 'anothertoken456')
    resp = client.get('/unsubscribe/anothertoken456')
    assert resp.status_code == 200


def test_invalid_token_returns_200_no_error(client):
    resp = client.get('/unsubscribe/doesnotexist')
    assert resp.status_code == 200


def test_confirmation_page_contains_message(client, db):
    _add_contact(db, 'user3@example.com', 'confirmtoken789')
    resp = client.get('/unsubscribe/confirmtoken789')
    assert b"unsubscribed" in resp.data.lower()


def test_invalid_token_does_not_leak_info(client):
    resp = client.get('/unsubscribe/doesnotexist')
    # Should render the same confirmation page, not a 404 or error
    assert b"unsubscribed" in resp.data.lower()
```

- [ ] **Step 6.2: Run tests to confirm they fail**

```bash
pytest tests/test_unsubscribe_route.py -v
```

Expected: All 5 tests FAIL.

- [ ] **Step 6.3: Add unsubscribe route to app.py**

```python
# ============================================================
# UNSUBSCRIBE
# ============================================================

@app.route('/unsubscribe/<token>')
def unsubscribe(token):
    """
    One-click unsubscribe. Sets contacts.unsubscribed=1 for the matching token.
    Always renders the confirmation page — no information leaked for invalid tokens.

    KNOWN LIMITATION: Some email security scanners pre-fetch all links, which may
    trigger this route and unsubscribe the recipient before they read the email.
    This is an accepted tradeoff of one-click unsubscribe.
    """
    db = get_db()
    contact = db.execute(
        "SELECT id FROM contacts WHERE unsubscribe_token=?", (token,)
    ).fetchone()
    if contact:
        db.execute(
            "UPDATE contacts SET unsubscribed=1 WHERE id=?", (contact['id'],)
        )
        db.commit()
    db.close()
    return render_template('unsubscribe.html')
```

- [ ] **Step 6.4: Create templates/unsubscribe.html**

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Unsubscribed</title>
  <style>
    body {
      font-family: -apple-system, Helvetica, Arial, sans-serif;
      background: #f5f5f5;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
    }
    .card {
      background: white;
      border-radius: 12px;
      padding: 48px 40px;
      text-align: center;
      max-width: 440px;
      box-shadow: 0 2px 16px rgba(0,0,0,0.08);
    }
    .icon { font-size: 48px; margin-bottom: 16px; }
    h1 { color: #1a1a2e; margin: 0 0 12px; font-size: 24px; }
    p  { color: #666; font-size: 16px; line-height: 1.6; margin: 0; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h1>You've been unsubscribed</h1>
    <p>You won't receive any more emails from this newsletter.</p>
  </div>
  <!--
    NOTE: Some email security scanners pre-fetch all links in incoming emails,
    which may trigger this page before the recipient reads the email.
    This is a known tradeoff of one-click unsubscribe.
  -->
</body>
</html>
```

- [ ] **Step 6.5: Run tests to confirm they pass**

```bash
pytest tests/test_unsubscribe_route.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 6.6: Commit**

```bash
git add app.py templates/unsubscribe.html tests/test_unsubscribe_route.py
git commit -m "feat: add one-click unsubscribe route and confirmation page"
```

---

### Task 7: Update template_send()

**Files:**
- Modify: `app.py`
- Create: `tests/test_template_send.py`

- [ ] **Step 7.1: Write failing tests**

Create `tests/test_template_send.py`:
```python
import json
from unittest.mock import patch, call


def _seed_template_and_contact(db):
    db.execute(
        "INSERT INTO templates (slug, name, subject_template, body_template, fields) "
        "VALUES ('test-tpl', 'Test', '{{title}}', '<p>{{body}}</p>', ?)",
        (json.dumps([
            {'name': 'title', 'label': 'Title', 'type': 'text'},
            {'name': 'body',  'label': 'Body',  'type': 'textarea'},
        ]),)
    )
    db.execute(
        "INSERT INTO contacts (email, name, groups, unsubscribe_token) "
        "VALUES ('alice@example.com', 'Alice', '[]', 'alicetoken123456')"
    )
    db.commit()


def test_send_creates_sends_row(client, db):
    _seed_template_and_contact(db)
    with patch('mailer.send_email'):
        client.post('/templates/test-tpl/send', data={
            'title': 'Hello', 'body': 'World', 'target_group': 'all',
        })
    count = db.execute("SELECT COUNT(*) FROM sends").fetchone()[0]
    assert count == 1


def test_send_inserts_sends_row_before_sending(client, db):
    """send_id must exist before email is built (needed for pixel URL)."""
    _seed_template_and_contact(db)
    captured_send_ids = []

    def mock_send(email, name, subject, body):
        # At the time send_email is called, the sends row should exist
        import database as db_module
        conn = db_module.get_db()
        rows = conn.execute("SELECT id FROM sends").fetchall()
        captured_send_ids.extend([r['id'] for r in rows])
        conn.close()

    with patch('mailer.send_email', side_effect=mock_send):
        client.post('/templates/test-tpl/send', data={
            'title': 'Hello', 'body': 'World', 'target_group': 'all',
        })

    assert len(captured_send_ids) > 0, "sends row should exist when send_email is called"


def test_send_updates_recipient_count(client, db):
    _seed_template_and_contact(db)
    with patch('mailer.send_email'):
        client.post('/templates/test-tpl/send', data={
            'title': 'Hello', 'body': 'World', 'target_group': 'all',
        })
    row = db.execute("SELECT recipient_count FROM sends").fetchone()
    assert row['recipient_count'] == 1


def test_send_uses_email_builder_output(client, db):
    _seed_template_and_contact(db)
    sent_bodies = []

    def mock_send(email, name, subject, body):
        sent_bodies.append(body)

    with patch('mailer.send_email', side_effect=mock_send):
        client.post('/templates/test-tpl/send', data={
            'title': 'Hello', 'body': 'World', 'target_group': 'all',
        })

    assert len(sent_bodies) == 1
    assert '<!DOCTYPE html>' in sent_bodies[0]
    assert '/unsubscribe/alicetoken123456' in sent_bodies[0]


def test_test_send_to_single_address(client, db):
    _seed_template_and_contact(db)
    with patch('mailer.send_email') as mock_send:
        resp = client.post('/templates/test-tpl/send', data={
            'title': 'Hello', 'body': 'World',
            'test_email': 'test@example.com',
        }, follow_redirects=True)
    assert resp.status_code == 200
    mock_send.assert_called_once()
    args = mock_send.call_args[0]
    assert args[0] == 'test@example.com'
```

- [ ] **Step 7.2: Run tests to confirm they fail**

```bash
pytest tests/test_template_send.py -v
```

Expected: Most tests FAIL (template_send doesn't use email_builder yet).

- [ ] **Step 7.3: Refactor template_send() in app.py**

`email_builder` was added as a module-level import in Task 5 Step 5.3 — no additional import needed here.

Replace the existing `template_send()` function body with:

```python
@app.route('/templates/<slug>/send', methods=['POST'])
def template_send(slug):

    db = get_db()
    tpl = db.execute("SELECT * FROM templates WHERE slug=?", (slug,)).fetchone()
    if not tpl:
        flash('Template not found.', 'error')
        db.close()
        return redirect(url_for('templates_list'))

    fields = json.loads(tpl['fields'])
    values = {}
    for f in fields:
        values[f['name']] = request.form.get(f['name'], '')

    font = request.form.get('font', '').strip() or None
    target_group = request.form.get('target_group', 'all')
    test_email = request.form.get('test_email', '').strip()

    from jinja2 import Template
    subject = Template(tpl['subject_template']).render(**values)
    body = Template(tpl['body_template']).render(**values)

    s = get_settings(db)

    # Optionally shorten URLs (shortener module added in Task 12)
    if s.get('url_shortener_enabled') == '1':
        try:
            from shortener import shorten_all_urls
            body = shorten_all_urls(body, s)
        except ImportError:
            pass  # shortener not yet implemented

    if test_email:
        # Test send: use a placeholder token, no DB send row
        full_html = eb.build_email(
            body=body, settings=s,
            unsubscribe_token='test',
            send_id=0,
            recipient_email=test_email,
            secret_key=app.secret_key,
            font=font,
        )
        try:
            send_email(test_email, '', subject, full_html)
            flash(f'Test email sent to {test_email}!', 'success')
        except Exception as e:
            flash(f'Error sending test: {e}', 'error')
        db.close()
        return redirect(url_for('template_detail', slug=slug))

    # Resolve recipients
    if target_group == 'all':
        rows = db.execute(
            "SELECT * FROM contacts WHERE unsubscribed=0"
        ).fetchall()
    else:
        all_rows = db.execute(
            "SELECT * FROM contacts WHERE unsubscribed=0"
        ).fetchall()
        rows = [r for r in all_rows if target_group in json.loads(r['groups'])]

    if not rows:
        flash('No recipients found for that group.', 'error')
        db.close()
        return redirect(url_for('template_detail', slug=slug))

    # Insert sends row BEFORE sending (send_id needed for pixel URLs)
    db.execute(
        "INSERT INTO sends (template_id, subject, body, recipient_count) VALUES (?, ?, ?, 0)",
        (tpl['id'], subject, body)
    )
    db.commit()
    send_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    successes = 0
    errors = []
    for r in rows:
        # Ensure unsubscribe_token exists
        token = r['unsubscribe_token']
        if not token:
            token = __import__('secrets').token_hex(16)
            db.execute(
                "UPDATE contacts SET unsubscribe_token=? WHERE id=?",
                (token, r['id'])
            )
            db.commit()

        full_html = eb.build_email(
            body=body, settings=s,
            unsubscribe_token=token,
            send_id=send_id,
            recipient_email=r['email'],
            secret_key=app.secret_key,
            font=font,
        )
        try:
            send_email(r['email'], r['name'], subject, full_html)
            successes += 1
        except Exception as e:
            errors.append((r['email'], str(e)))

    db.execute(
        "UPDATE sends SET recipient_count=? WHERE id=?", (successes, send_id)
    )
    db.commit()
    db.close()

    if errors:
        flash(f'Sent to {successes} recipients. {len(errors)} errors.', 'warning')
    else:
        flash(f'Sent to {successes} recipients!', 'success')

    return redirect(url_for('template_detail', slug=slug))
```

- [ ] **Step 7.4: Run tests to confirm they pass**

```bash
pytest tests/test_template_send.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 7.5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 7.6: Commit**

```bash
git add app.py tests/test_template_send.py
git commit -m "feat: refactor template_send to per-recipient loop with email_builder"
```

---

### Task 8: Update check_deadman_switch()

**Files:**
- Modify: `app.py`
- Create: `tests/test_deadman_send.py`

- [ ] **Step 8.1: Write failing tests**

Create `tests/test_deadman_send.py`:
```python
import json
from datetime import datetime, timedelta
from unittest.mock import patch


def _setup_deadman(db, hours_overdue=1):
    db.execute(
        "INSERT INTO contacts (email, name, groups, unsubscribe_token) "
        "VALUES ('bob@example.com', 'Bob', '[\"emergency\"]', 'bobtoken123456')"
    )
    last_checkin = (datetime.utcnow() - timedelta(hours=hours_overdue + 1)).isoformat()
    db.execute(
        "UPDATE deadman_switch SET active=1, check_in_interval_hours=?, "
        "last_check_in=?, recipient_group='emergency', subject='Alert'",
        (hours_overdue, last_checkin)
    )
    db.commit()


def test_deadman_send_uses_email_builder(db, app):
    _setup_deadman(db)
    sent_bodies = []

    def mock_send(email, name, subject, body):
        sent_bodies.append(body)

    with patch('mailer.send_email', side_effect=mock_send):
        from app import check_deadman_switch
        result = check_deadman_switch()

    assert result == 'triggered'
    assert len(sent_bodies) == 1
    assert '<!DOCTYPE html>' in sent_bodies[0]
    assert '/unsubscribe/bobtoken123456' in sent_bodies[0]


def test_deadman_send_creates_sends_row(db, app):
    _setup_deadman(db)
    with patch('mailer.send_email'):
        from app import check_deadman_switch
        check_deadman_switch()

    count = db.execute("SELECT COUNT(*) FROM sends").fetchone()[0]
    assert count == 1
```

- [ ] **Step 8.2: Run tests to confirm they fail**

```bash
pytest tests/test_deadman_send.py -v
```

Expected: Both tests FAIL.

- [ ] **Step 8.3: Update check_deadman_switch() in app.py**

Preserve the existing function structure: early returns for `inactive` and `ok` states remain unchanged. Only the section after `recipients` is resolved (the email-building and sending section) is replaced. The `deadman_switch` table has a `body` column (see `database.py` schema).

Replace the email-sending portion of `check_deadman_switch()` (after recipients are resolved) with:

```python
    # Build body from template
    tpl = db.execute("SELECT * FROM templates WHERE slug='deadman-switch'").fetchone()
    if tpl and switch['trip_details']:
        from jinja2 import Template as J2Template
        try:
            values = json.loads(switch['trip_details'])
        except (json.JSONDecodeError, TypeError):
            values = {'trip_details': switch['trip_details']}
        body = J2Template(tpl['body_template']).render(**values)
    else:
        body = switch['body'] or f"<p>{switch['subject']}</p>"

    s = get_settings(db)

    # Insert sends row before sending
    db.execute(
        "INSERT INTO sends (template_id, subject, body, recipient_count) "
        "VALUES (?, ?, ?, 0)",
        (tpl['id'] if tpl else 1, switch['subject'] or 'Emergency', body)
    )
    db.commit()
    send_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    successes = 0
    for r in recipients:
        email_addr, name = r[0], r[1]
        # Look up unsubscribe token
        contact = db.execute(
            "SELECT unsubscribe_token FROM contacts WHERE email=?", (email_addr,)
        ).fetchone()
        token = contact['unsubscribe_token'] if contact and contact['unsubscribe_token'] else 'none'

        full_html = eb.build_email(
            body=body, settings=s,
            unsubscribe_token=token,
            send_id=send_id,
            recipient_email=email_addr,
            secret_key=app.secret_key,
            font=None,
        )
        try:
            send_email(email_addr, name, switch['subject'] or 'Emergency', full_html)
            successes += 1
        except Exception:
            pass

    db.execute("UPDATE sends SET recipient_count=? WHERE id=?", (successes, send_id))
    db.execute("UPDATE deadman_switch SET active=0")
    db.commit()
    db.close()
    return 'triggered'
```

Note: The existing `send_bulk` call and the old `full_body` construction are removed and replaced by the above.

- [ ] **Step 8.4: Run tests to confirm they pass**

```bash
pytest tests/test_deadman_send.py -v
```

Expected: Both tests PASS.

- [ ] **Step 8.5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 8.6: Commit**

```bash
git add app.py tests/test_deadman_send.py
git commit -m "feat: update check_deadman_switch to use email_builder per-recipient"
```

---

## Chunk 3: Content, Appearance & URL Shortener

---

### Task 9: Quill.js Rich Text Editor

**Files:**
- Modify: `templates/template_detail.html`

_Note: Quill.js is a frontend-only change. Tests are integration/manual — verify in browser._

- [ ] **Step 9.1: Read templates/template_detail.html to understand current structure**

Read the file before editing.

- [ ] **Step 9.2: Add Quill CSS and JS to the template head**

In `templates/template_detail.html`, inside `{% block head %}` (or add one if not present, extending base.html), add:

```html
<link href="https://cdn.quilljs.com/1.3.7/quill.snow.css" rel="stylesheet">
```

And before `</body>` or in `{% block scripts %}`:

```html
<script src="https://cdn.quilljs.com/1.3.7/quill.js"></script>
```

- [ ] **Step 9.3: Register custom fonts with Quill whitelist**

Add this script block after the Quill JS include:

```html
<script>
var Font = Quill.import('formats/font');
Font.whitelist = ['georgia','arial','helvetica','verdana','times-new-roman','trebuchet','courier'];
Quill.register(Font, true);
</script>
```

- [ ] **Step 9.4: Add font CSS mapping in a style block**

```html
<style>
.ql-font-georgia       { font-family: Georgia, serif; }
.ql-font-arial         { font-family: Arial, sans-serif; }
.ql-font-helvetica     { font-family: Helvetica, sans-serif; }
.ql-font-verdana       { font-family: Verdana, sans-serif; }
.ql-font-times-new-roman { font-family: 'Times New Roman', serif; }
.ql-font-trebuchet     { font-family: 'Trebuchet MS', sans-serif; }
.ql-font-courier       { font-family: 'Courier New', monospace; }
</style>
```

- [ ] **Step 9.5: Replace textarea fields with Quill editors**

In the template field loop (where `{% for f in fields %}`), change the rendering condition:

```html
{% if f.type == 'textarea' %}
  <div id="editor-{{ f.name }}" style="height:180px;background:white;"></div>
  <input type="hidden" name="{{ f.name }}" id="hidden-{{ f.name }}"
         value="{{ request.form.get(f.name, '') }}">
{% else %}
  <input type="text" class="form-control" name="{{ f.name }}"
         value="{{ request.form.get(f.name, '') }}">
{% endif %}
```

- [ ] **Step 9.6: Add Quill initialization and form submit script**

After the field loop, add:

```html
<script>
var quillToolbar = [
  [{ 'font': ['georgia','arial','helvetica','verdana','times-new-roman','trebuchet','courier'] }],
  [{ 'size': ['small', false, 'large', 'huge'] }],
  ['bold', 'italic', 'underline'],
  ['link'],
  [{ 'list': 'ordered' }, { 'list': 'bullet' }],
  [{ 'color': [] }],
  ['clean']
];

var editors = [];
{% for f in fields %}
{% if f.type == 'textarea' %}
var quill_{{ f.name }} = new Quill('#editor-{{ f.name }}', {
  theme: 'snow',
  modules: { toolbar: quillToolbar }
});
// Restore value if re-rendering (e.g. after preview)
var existing_{{ f.name }} = document.getElementById('hidden-{{ f.name }}').value;
if (existing_{{ f.name }}) {
  quill_{{ f.name }}.root.innerHTML = existing_{{ f.name }};
}
editors.push({ editor: quill_{{ f.name }}, fieldName: '{{ f.name }}' });
{% endif %}
{% endfor %}

document.querySelector('form').addEventListener('submit', function() {
  editors.forEach(function(q) {
    document.getElementById('hidden-' + q.fieldName).value = q.editor.root.innerHTML;
  });
});
</script>
```

- [ ] **Step 9.7: Verify manually**

Run the Flask app:
```bash
python app.py
```

Navigate to any template (e.g. `http://localhost:5000/templates/newsletter`). All textarea fields should show Quill editors with the toolbar. Type text, apply a font to selected words. Submit the form to preview — verify the HTML with inline font-family spans appears in the preview.

- [ ] **Step 9.8: Commit**

```bash
git add templates/template_detail.html
git commit -m "feat: replace textarea fields with Quill.js v1.3.7 rich text editor"
```

---

### Task 10: Font Picker (global default + per-send override)

**Files:**
- Modify: `templates/template_detail.html`
- Modify: `app.py` (template_detail route)
- Create: `tests/test_font_picker.py`

- [ ] **Step 10.1: Write failing test**

Create `tests/test_font_picker.py`:
```python
import json
from unittest.mock import patch


def _seed_template(db):
    db.execute(
        "INSERT INTO templates (slug, name, subject_template, body_template, fields) "
        "VALUES ('test-font', 'Test Font', 'Subj', '<p>{{body}}</p>', ?)",
        (json.dumps([{'name': 'body', 'label': 'Body', 'type': 'textarea'}]),)
    )
    db.execute(
        "INSERT INTO contacts (email, name, groups, unsubscribe_token) "
        "VALUES ('c@example.com', 'C', '[]', 'ctok')"
    )
    db.commit()


def test_template_detail_passes_fonts_to_template(client, db):
    _seed_template(db)
    resp = client.get('/templates/test-font')
    assert resp.status_code == 200
    # All 7 fonts should appear in the page
    assert b'Georgia' in resp.data
    assert b'Arial' in resp.data
    assert b'Verdana' in resp.data


def test_font_picker_preselects_default_font(client, db):
    _seed_template(db)
    db.execute(
        "UPDATE settings SET value='Arial, sans-serif' WHERE key='default_font'"
    )
    db.commit()
    resp = client.get('/templates/test-font')
    # The Arial option should be pre-selected
    assert b'Arial, sans-serif' in resp.data


def test_send_uses_chosen_font(client, db):
    _seed_template(db)
    sent_bodies = []

    def mock_send(email, name, subject, body):
        sent_bodies.append(body)

    with patch('mailer.send_email', side_effect=mock_send):
        client.post('/templates/test-font/send', data={
            'body': '<p>Hello</p>',
            'target_group': 'all',
            'font': 'Verdana, sans-serif',
        })

    assert len(sent_bodies) == 1
    assert 'Verdana, sans-serif' in sent_bodies[0]
```

- [ ] **Step 10.2: Run tests to confirm they fail**

```bash
pytest tests/test_font_picker.py -v
```

Expected: All 3 tests FAIL.

- [ ] **Step 10.3: Update template_detail route to pass fonts and settings**

`FONT_OPTIONS` was defined as a module-level constant in Task 3 Step 3.4 when the settings route was added. It contains the 7 font dicts `{'value': ..., 'label': ...}`. Confirm it exists at the top of `app.py` before proceeding.

In `app.py`, in the `template_detail()` route, add a call to `get_settings(db)` and pass both `fonts` and `settings` to the template:

```python
    s = get_settings(db)
    ...
    return render_template('template_detail.html',
                           template=tpl, fields=fields,
                           groups=sorted(all_groups),
                           fonts=FONT_OPTIONS,
                           settings=s)
```

- [ ] **Step 10.4: Add font picker to template_detail.html**

Below the Quill editors (from Task 9) and above the send/preview buttons, add:

```html
<div class="mb-3">
  <label class="form-label fw-bold">
    Font
    <small class="text-muted fw-normal">(default from Settings — change for this send only)</small>
  </label>
  <select name="font" class="form-select">
    {% for f in fonts %}
    <option value="{{ f.value }}"
      {% if f.value == settings.default_font %}selected{% endif %}>
      {{ f.label }}
    </option>
    {% endfor %}
  </select>
</div>
```

- [ ] **Step 10.5: Run tests to confirm they pass**

```bash
pytest tests/test_font_picker.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 10.6: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 10.7: Commit**

```bash
git add app.py templates/template_detail.html tests/test_font_picker.py
git commit -m "feat: add per-send font picker pre-populated from global default"
```

---

### Task 11: Improve 5 Email Templates

**Files:**
- Modify: `database.py`
- Create: `tests/test_template_migration.py`

- [ ] **Step 11.1: Write failing test**

Create `tests/test_template_migration.py`:
```python
import hashlib
import database as db_module


def test_templates_use_safe_filter_for_textarea_vars(db):
    """All textarea-sourced variables in template bodies must use | safe filter."""
    import json
    templates = db.execute("SELECT slug, body_template, fields FROM templates").fetchall()
    for tpl in templates:
        fields = json.loads(tpl['fields'])
        textarea_fields = [f['name'] for f in fields if f.get('type') == 'textarea']
        body = tpl['body_template']
        for fname in textarea_fields:
            # Variable should be rendered with | safe
            assert f'{{{{{fname} | safe}}}}' in body or f'{{{{{ fname }|safe}}}}' in body or \
                   f'{{{{{fname}|safe}}}}' in body, \
                f"Template '{tpl['slug']}': textarea field '{fname}' missing | safe filter"


def test_migration_does_not_overwrite_customised_templates(db):
    """If a template body has been changed, migration should not overwrite it."""
    db.execute(
        "UPDATE templates SET body_template='CUSTOMISED' WHERE slug='newsletter'"
    )
    db.commit()
    # Re-running init_db should NOT overwrite the customised template
    db_module.init_db()
    row = db.execute(
        "SELECT body_template FROM templates WHERE slug='newsletter'"
    ).fetchone()
    assert row['body_template'] == 'CUSTOMISED'
```

- [ ] **Step 11.2: Run tests to confirm they fail**

```bash
pytest tests/test_template_migration.py -v
```

Expected: Both tests FAIL (templates don't use `| safe` yet).

- [ ] **Step 11.3: Add template body hash constants to database.py**

At the top of `database.py`, after imports, add a helper and the original-body hashes:

```python
import hashlib

def _body_hash(body):
    return hashlib.sha256(body.encode()).hexdigest()
```

After `_seed_templates()` is defined, add a dict of original hashes (computed from the current bodies before you change them):

```python
# Run this once to get hashes: python -c "import database; database._print_hashes()"
_ORIGINAL_TEMPLATE_HASHES = {}  # populated in Step 11.4
```

- [ ] **Step 11.4: Compute current template body hashes**

```bash
cd /home/evan/projects/Dead-Man-Newsletter
python - <<'EOF'
import hashlib, json

# Read current template bodies from database.py _seed_templates
import database
import sqlite3, tempfile, os
fd, path = tempfile.mkstemp(suffix='.db')
database.DB_PATH = path
database.init_db()
conn = sqlite3.connect(path)
conn.row_factory = sqlite3.Row
for row in conn.execute("SELECT slug, body_template FROM templates"):
    h = hashlib.sha256(row['body_template'].encode()).hexdigest()
    print(f"'{row['slug']}': '{h}',")
conn.close()
os.close(fd)
os.unlink(path)
EOF
```

Copy the 5 hash values from the output into `_ORIGINAL_TEMPLATE_HASHES` in `database.py`. Each value is a 64-character hex string. Example of what the populated constant should look like (your actual values will differ):

```python
_ORIGINAL_TEMPLATE_HASHES = {
    'newsletter':     'a3f9c1d2e4b5f6a7...',  # 64 hex chars
    'job-seeking':    'b4e8d2c3f5a6b7c8...',
    'social-roundup': 'c5f9e3d4a6b7c8d9...',
    'new-videos':     'd6a0f4e5b7c8d9e0...',
    'deadman-switch': 'e7b1a5f6c8d9e0f1...',
}
```

**Verify:** After pasting, run:
```bash
python -c "from database import _ORIGINAL_TEMPLATE_HASHES; assert all(len(v)==64 for v in _ORIGINAL_TEMPLATE_HASHES.values()); print('OK — all 5 hashes look valid')"
```
Expected: `OK — all 5 hashes look valid`

- [ ] **Step 11.5: Write improved template bodies in _seed_templates()**

For each template, update `body_template` to:
1. Apply `| safe` to all textarea-sourced variables (e.g. `{{intro}}` → `{{intro | safe}}`)
2. Improve spacing, typography, and visual hierarchy

**newsletter** — key changes: add max-width wrapper, improve h1/h2 colors and spacing, apply `| safe` to `intro`, `section1_body`, `section2_body`, `closing`:

```python
'body_template': '''<div style="max-width:600px;margin:0 auto;padding:24px 0;">
  <h1 style="color:#1a1a2e;border-bottom:3px solid #e94560;padding-bottom:12px;font-size:28px;margin:0 0 20px;">{{title}}</h1>
  <p style="font-size:16px;line-height:1.7;color:#333;margin:0 0 24px;">{{intro | safe}}</p>
  {% if section1_title %}
  <h2 style="color:#1a1a2e;font-size:20px;margin:0 0 12px;">{{section1_title}}</h2>
  {% endif %}
  <div style="font-size:16px;line-height:1.7;color:#333;margin:0 0 24px;">{{section1_body | safe}}</div>
  {% if section2_title %}
  <h2 style="color:#1a1a2e;font-size:20px;margin:0 0 12px;">{{section2_title}}</h2>
  <div style="font-size:16px;line-height:1.7;color:#333;margin:0 0 24px;">{{section2_body | safe}}</div>
  {% endif %}
  <hr style="border:none;border-top:1px solid #ddd;margin:32px 0;">
  <div style="font-size:16px;line-height:1.7;color:#333;">{{closing | safe}}</div>
</div>''',
```

**job-seeking** — apply `| safe` to `looking_for`, `skills`, `personal_note`:

```python
'body_template': '''<div style="max-width:600px;margin:0 auto;padding:24px 0;font-family:-apple-system,Helvetica,Arial,sans-serif;">
  <h1 style="color:#2d3436;font-size:26px;margin:0 0 16px;">Hey, I\'m looking for work 👋</h1>
  <p style="font-size:16px;line-height:1.6;background:#f8f9fa;padding:16px;border-radius:8px;border-left:4px solid #0984e3;margin:0 0 24px;">
    <strong>Status:</strong> {{current_status}}
  </p>
  <h2 style="color:#2d3436;font-size:18px;margin:0 0 10px;">What I\'m Looking For</h2>
  <div style="font-size:16px;line-height:1.7;color:#333;margin:0 0 24px;">{{looking_for | safe}}</div>
  <h2 style="color:#2d3436;font-size:18px;margin:0 0 10px;">Skills &amp; Experience</h2>
  <div style="font-size:16px;line-height:1.7;color:#333;margin:0 0 24px;">{{skills | safe}}</div>
  {% if portfolio_url %}
  <p style="margin:0 0 24px;">
    <a href="{{portfolio_url}}" style="display:inline-block;background:#0984e3;color:#fff;padding:10px 22px;border-radius:6px;text-decoration:none;font-weight:bold;">View my work →</a>
  </p>
  {% endif %}
  {% if personal_note %}
  <hr style="border:none;border-top:1px solid #ddd;margin:24px 0;">
  <div style="font-size:16px;line-height:1.7;color:#555;font-style:italic;">{{personal_note | safe}}</div>
  {% endif %}
  <p style="font-size:14px;color:#636e72;margin:24px 0 0;">If you know of anything or can make an introduction, I\'d really appreciate it. Feel free to forward this along!</p>
</div>''',
```

**social-roundup** — apply `| safe` to `intro_note`, `highlights`, `stats`, `upcoming`:

```python
'body_template': '''<div style="max-width:600px;margin:0 auto;">
  <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:32px;border-radius:12px 12px 0 0;color:white;">
    <h1 style="margin:0;font-size:26px;">📱 Weekly Roundup</h1>
    <p style="margin:6px 0 0;opacity:0.9;font-size:15px;">{{creator_name}} — {{week_label}}</p>
  </div>
  <div style="padding:24px;background:#f8f9fa;border-radius:0 0 12px 12px;">
    <div style="font-size:16px;line-height:1.7;color:#333;margin:0 0 20px;">{{intro_note | safe}}</div>
    <h2 style="color:#667eea;font-size:18px;margin:0 0 12px;">🔥 Highlights</h2>
    <div style="font-size:16px;line-height:1.8;color:#333;margin:0 0 20px;">{{highlights | safe}}</div>
    {% if stats %}
    <h2 style="color:#667eea;font-size:18px;margin:0 0 12px;">📊 Stats &amp; Milestones</h2>
    <div style="font-size:16px;line-height:1.7;color:#333;margin:0 0 20px;">{{stats | safe}}</div>
    {% endif %}
    {% if upcoming %}
    <h2 style="color:#667eea;font-size:18px;margin:0 0 12px;">👀 Coming Up</h2>
    <div style="font-size:16px;line-height:1.7;color:#333;">{{upcoming | safe}}</div>
    {% endif %}
  </div>
</div>''',
```

**new-videos** — apply `| safe` to `intro`, `video1_description`, `video2_description`, `outro`:

```python
'body_template': '''<div style="max-width:600px;margin:0 auto;background:#0f0f0f;padding:32px;border-radius:12px;">
  <h1 style="color:#ff0000;font-size:26px;margin:0 0 12px;">🎬 {{channel_name}}</h1>
  <div style="color:#aaa;font-size:16px;line-height:1.7;margin:0 0 20px;">{{intro | safe}}</div>
  <div style="background:#1a1a1a;border-radius:8px;padding:22px;margin:0 0 16px;">
    <h2 style="color:#fff;font-size:18px;margin:0 0 10px;">{{video1_title}}</h2>
    <div style="color:#aaa;font-size:15px;line-height:1.6;margin:0 0 16px;">{{video1_description | safe}}</div>
    <a href="{{video1_url}}" style="display:inline-block;background:#ff0000;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">▶ Watch Now</a>
  </div>
  {% if video2_title %}
  <div style="background:#1a1a1a;border-radius:8px;padding:22px;margin:0 0 16px;">
    <h2 style="color:#fff;font-size:18px;margin:0 0 10px;">{{video2_title}}</h2>
    <div style="color:#aaa;font-size:15px;line-height:1.6;margin:0 0 16px;">{{video2_description | safe}}</div>
    <a href="{{video2_url}}" style="display:inline-block;background:#ff0000;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">▶ Watch Now</a>
  </div>
  {% endif %}
  {% if outro %}
  <hr style="border:none;border-top:1px solid #333;margin:24px 0;">
  <div style="color:#aaa;font-size:15px;line-height:1.6;">{{outro | safe}}</div>
  {% endif %}
</div>''',
```

**deadman-switch** — apply `| safe` to `itinerary`, `gear_description`, `emergency_contacts`, `instructions`:

```python
'body_template': '''<div style="max-width:600px;margin:0 auto;">
  <div style="background:#d63031;padding:24px;border-radius:8px 8px 0 0;color:white;text-align:center;">
    <h1 style="margin:0;font-size:26px;">🚨 SAFETY ALERT</h1>
    <p style="margin:8px 0 0;font-size:18px;">{{traveler_name}} has not checked in</p>
  </div>
  <div style="background:#fff3f3;padding:28px;border:2px solid #d63031;border-top:none;border-radius:0 0 8px 8px;">
    <p style="font-size:16px;line-height:1.7;margin:0 0 20px;">
      This is an automated safety message. <strong>{{traveler_name}}</strong> set up this alert
      before going on a trip and has not checked in within the expected timeframe.
      <strong>This may mean they need help.</strong>
    </p>
    <h2 style="color:#d63031;font-size:18px;margin:0 0 12px;">📍 Trip Details</h2>
    <table style="width:100%;font-size:15px;line-height:1.7;margin:0 0 20px;">
      <tr><td style="padding:4px 10px;font-weight:bold;white-space:nowrap;vertical-align:top;">Trip:</td><td style="padding:4px 10px;">{{trip_name}}</td></tr>
      <tr style="background:#fff;"><td style="padding:4px 10px;font-weight:bold;white-space:nowrap;vertical-align:top;">Dates:</td><td style="padding:4px 10px;">{{trip_dates}}</td></tr>
      <tr><td style="padding:4px 10px;font-weight:bold;white-space:nowrap;vertical-align:top;">Last Known Location:</td><td style="padding:4px 10px;">{{last_known_location}}</td></tr>
      {% if vehicle_info %}
      <tr style="background:#fff;"><td style="padding:4px 10px;font-weight:bold;white-space:nowrap;vertical-align:top;">Vehicle:</td><td style="padding:4px 10px;">{{vehicle_info}}</td></tr>
      {% endif %}
    </table>
    {% if itinerary %}
    <h2 style="color:#d63031;font-size:18px;margin:0 0 10px;">🗺️ Planned Route / Itinerary</h2>
    <div style="font-size:15px;line-height:1.7;background:#fff;padding:16px;border-radius:6px;border:1px solid #eee;margin:0 0 20px;">{{itinerary | safe}}</div>
    {% endif %}
    {% if gear_description %}
    <h2 style="color:#d63031;font-size:18px;margin:0 0 10px;">🎒 Gear / Appearance</h2>
    <div style="font-size:15px;line-height:1.7;margin:0 0 20px;">{{gear_description | safe}}</div>
    {% endif %}
    {% if emergency_contacts %}
    <h2 style="color:#d63031;font-size:18px;margin:0 0 10px;">📞 Emergency Contacts</h2>
    <div style="font-size:15px;line-height:1.7;margin:0 0 20px;">{{emergency_contacts | safe}}</div>
    {% endif %}
    {% if instructions %}
    <h2 style="color:#d63031;font-size:18px;margin:0 0 10px;">⚠️ What To Do</h2>
    <div style="font-size:16px;line-height:1.7;font-weight:bold;background:#fff;padding:16px;border-radius:6px;border:2px solid #d63031;margin:0 0 20px;">{{instructions | safe}}</div>
    {% endif %}
    <hr style="border:none;border-top:2px solid #d63031;margin:24px 0;">
    <p style="font-size:13px;color:#666;text-align:center;margin:0;">
      This message was sent automatically because {{traveler_name}} did not check in.
      If you have confirmed they are safe, no further action is needed.
    </p>
  </div>
</div>''',
```

- [ ] **Step 11.6: Refactor _seed_templates and add migration guard to init_db**

Restructure `database.py` so template body strings are defined once in a module-level constant, reused by both initial seeding and migration refresh.

**Step A:** Extract template definitions from `_seed_templates()` into a module-level constant `_TEMPLATE_DEFS` (a list of dicts, same structure as now). `_seed_templates()` then just iterates over `_TEMPLATE_DEFS` and inserts.

**Step B:** Add `_get_new_template_bodies()` — a simple one-liner:

```python
def _get_new_template_bodies():
    """Return {slug: new_body_template} for all default templates."""
    return {t['slug']: t['body_template'] for t in _TEMPLATE_DEFS}
```

**Step C:** Add `_refresh_templates()`:

```python
def _refresh_templates(conn):
    """Re-seed template bodies that still match their original defaults.
    Templates customised by the user are left untouched."""
    new_bodies = _get_new_template_bodies()
    for slug, new_body in new_bodies.items():
        row = conn.execute(
            "SELECT body_template FROM templates WHERE slug=?", (slug,)
        ).fetchone()
        if not row:
            continue
        current_hash = _body_hash(row['body_template'])
        original_hash = _ORIGINAL_TEMPLATE_HASHES.get(slug, '')
        if current_hash == original_hash:
            # Matches original default — safe to update
            conn.execute(
                "UPDATE templates SET body_template=? WHERE slug=?",
                (new_body, slug)
            )
    conn.commit()
```

**Step D:** In `init_db()`, replace the templates seed block:

```python
    if conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0] == 0:
        _seed_templates(conn)
    else:
        _refresh_templates(conn)
```

- [ ] **Step 11.7: Run tests to confirm they pass**

```bash
pytest tests/test_template_migration.py -v
```

Expected: Both tests PASS.

- [ ] **Step 11.8: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 11.9: Commit**

```bash
git add database.py tests/test_template_migration.py
git commit -m "feat: improve all 5 email template bodies with better HTML and | safe filters"
```

---

### Task 12: shortener.py module

**Files:**
- Create: `shortener.py`
- Create: `tests/test_shortener.py`

- [ ] **Step 12.1: Write failing tests**

Create `tests/test_shortener.py`:
```python
from unittest.mock import patch, MagicMock
import shortener


BASE_SETTINGS = {
    'url_shortener_provider': 'bitly',
    'url_shortener_api_key': 'testkey',
    'url_shortener_bitly_group': 'Bg123',
}


def test_shorten_url_bitly_returns_short_url():
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"link": "https://bit.ly/abc123"}'
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        result = shortener.shorten_url(
            'https://example.com/long-url',
            provider='bitly', api_key='key', group_guid='Bg123'
        )
    assert result == 'https://bit.ly/abc123'


def test_shorten_url_tinyurl_returns_short_url():
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"data": {"tiny_url": "https://tinyurl.com/xy9z"}}'
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        result = shortener.shorten_url(
            'https://example.com/long-url',
            provider='tinyurl', api_key='key'
        )
    assert result == 'https://tinyurl.com/xy9z'


def test_shorten_url_returns_original_on_network_error():
    with patch('urllib.request.urlopen', side_effect=Exception("network error")):
        result = shortener.shorten_url(
            'https://example.com/original',
            provider='bitly', api_key='key'
        )
    assert result == 'https://example.com/original'


def test_shorten_all_urls_replaces_hrefs():
    html = '<a href="https://example.com/page">Click</a>'
    with patch('shortener.shorten_url', return_value='https://bit.ly/xyz'):
        result = shortener.shorten_all_urls(html, BASE_SETTINGS)
    assert 'https://bit.ly/xyz' in result
    assert 'https://example.com/page' not in result


def test_shorten_all_urls_skips_mailto():
    html = '<a href="mailto:test@example.com">Email</a>'
    with patch('shortener.shorten_url') as mock_shorten:
        shortener.shorten_all_urls(html, BASE_SETTINGS)
    mock_shorten.assert_not_called()


def test_shorten_all_urls_skips_hash_links():
    html = '<a href="#section1">Jump</a>'
    with patch('shortener.shorten_url') as mock_shorten:
        shortener.shorten_all_urls(html, BASE_SETTINGS)
    mock_shorten.assert_not_called()


def test_shorten_all_urls_skips_unsubscribe_links():
    html = '<a href="/unsubscribe/abc123">Unsubscribe</a>'
    with patch('shortener.shorten_url') as mock_shorten:
        shortener.shorten_all_urls(html, BASE_SETTINGS)
    mock_shorten.assert_not_called()


def test_shorten_all_urls_deduplicates_same_url():
    html = (
        '<a href="https://example.com/page">A</a>'
        '<a href="https://example.com/page">B</a>'
    )
    call_count = []
    def mock_shorten(url, **kwargs):
        call_count.append(url)
        return 'https://bit.ly/xyz'

    with patch('shortener.shorten_url', side_effect=mock_shorten):
        shortener.shorten_all_urls(html, BASE_SETTINGS)

    assert len(call_count) == 1  # only called once for the duplicate URL
```

- [ ] **Step 12.2: Run tests to confirm they fail**

```bash
pytest tests/test_shortener.py -v
```

Expected: All 8 tests FAIL.

- [ ] **Step 12.3: Create shortener.py**

```python
import json
import urllib.request
import urllib.error
from html.parser import HTMLParser


def shorten_url(url, provider, api_key, group_guid=None):
    """
    Shorten a URL using the configured provider.
    Returns the shortened URL, or the original URL on any failure (fail-open).
    """
    try:
        if provider == 'bitly':
            return _shorten_bitly(url, api_key, group_guid)
        elif provider == 'tinyurl':
            return _shorten_tinyurl(url, api_key)
    except Exception:
        pass
    return url


def _shorten_bitly(url, api_key, group_guid=None):
    payload = {'long_url': url}
    if group_guid:
        payload['group_guid'] = group_guid

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        'https://api-ssl.bitly.com/v4/shorten',
        data=data,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    return result['link']


def _shorten_tinyurl(url, api_key):
    payload = {'url': url, 'domain': 'tinyurl.com'}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        'https://api.tinyurl.com/create',
        data=data,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    return result['data']['tiny_url']


class _HrefCollector(HTMLParser):
    """Collect all href attribute values from HTML."""
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name.lower() == 'href' and value:
                self.hrefs.append(value)


def _should_skip(url):
    """Return True if the URL should not be shortened."""
    if not url:
        return True
    lower = url.lower()
    return (
        lower.startswith('mailto:') or
        lower.startswith('#') or
        '/unsubscribe/' in lower or
        not lower.startswith('http')
    )


def shorten_all_urls(html, settings):
    """
    Parse all href values from HTML, shorten qualifying URLs, return updated HTML.

    Uses stdlib html.parser — no external dependencies.
    Deduplicates: each unique URL is shortened only once.
    """
    provider = settings.get('url_shortener_provider', 'bitly')
    api_key = settings.get('url_shortener_api_key', '')
    group_guid = settings.get('url_shortener_bitly_group', '') or None

    collector = _HrefCollector()
    collector.feed(html)

    replacements = {}
    for url in collector.hrefs:
        if _should_skip(url) or url in replacements:
            continue
        short = shorten_url(url, provider=provider, api_key=api_key, group_guid=group_guid)
        if short != url:
            replacements[url] = short

    result = html
    for original, shortened in replacements.items():
        result = result.replace(f'href="{original}"', f'href="{shortened}"')
        result = result.replace(f"href='{original}'", f"href='{shortened}'")

    return result
```

- [ ] **Step 12.4: Run tests to confirm they pass**

```bash
pytest tests/test_shortener.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 12.5: Commit**

```bash
git add shortener.py tests/test_shortener.py
git commit -m "feat: add shortener module with Bit.ly and TinyURL support"
```

---

### Task 13: Wire shortener into send flow

**Files:**
- Modify: `app.py`
- Create: `tests/test_shortener_integration.py`

- [ ] **Step 13.1: Write failing test**

Create `tests/test_shortener_integration.py`:
```python
import json
from unittest.mock import patch


def _seed(db):
    db.execute(
        "INSERT INTO templates (slug, name, subject_template, body_template, fields) "
        "VALUES ('link-tpl', 'Links', 'Subj', "
        "'<a href=\"https://example.com/long\">Click</a>', '[]')"
    )
    db.execute(
        "INSERT INTO contacts (email, name, groups, unsubscribe_token) "
        "VALUES ('d@example.com', 'D', '[]', 'dtok')"
    )
    db.execute(
        "UPDATE settings SET value='1' WHERE key='url_shortener_enabled'"
    )
    db.execute(
        "UPDATE settings SET value='bitly' WHERE key='url_shortener_provider'"
    )
    db.execute(
        "UPDATE settings SET value='fakekey' WHERE key='url_shortener_api_key'"
    )
    db.commit()


def test_shortener_called_when_enabled(client, db):
    _seed(db)
    sent_bodies = []

    def mock_send(email, name, subject, body):
        sent_bodies.append(body)

    with patch('mailer.send_email', side_effect=mock_send), \
         patch('shortener.shorten_url', return_value='https://bit.ly/short') as mock_shorten:
        client.post('/templates/link-tpl/send', data={'target_group': 'all'})

    mock_shorten.assert_called()
    assert 'https://bit.ly/short' in sent_bodies[0]


def test_shortener_not_called_when_disabled(client, db):
    _seed(db)
    db.execute("UPDATE settings SET value='0' WHERE key='url_shortener_enabled'")
    db.commit()

    with patch('mailer.send_email'), \
         patch('shortener.shorten_url') as mock_shorten:
        client.post('/templates/link-tpl/send', data={'target_group': 'all'})

    mock_shorten.assert_not_called()
```

- [ ] **Step 13.2: Run tests to confirm they fail**

```bash
pytest tests/test_shortener_integration.py -v
```

Expected: Both tests FAIL (shortener import guard in template_send skips it).

- [ ] **Step 13.3: Replace the import-guard placeholder in template_send()**

In `app.py`, in `template_send()`, find the shortener block:

```python
    if s.get('url_shortener_enabled') == '1':
        try:
            from shortener import shorten_all_urls
            body = shorten_all_urls(body, s)
        except ImportError:
            pass
```

Remove the `try/except ImportError` wrapper — shortener.py now exists:

```python
    if s.get('url_shortener_enabled') == '1':
        from shortener import shorten_all_urls
        body = shorten_all_urls(body, s)
```

Do the same in `check_deadman_switch()`.

- [ ] **Step 13.4: Run tests to confirm they pass**

```bash
pytest tests/test_shortener_integration.py -v
```

Expected: Both tests PASS.

- [ ] **Step 13.5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 13.6: Commit**

```bash
git add app.py tests/test_shortener_integration.py
git commit -m "feat: wire URL shortener into template_send and check_deadman_switch"
```

---

## Chunk 4: Containerization and Documentation

---

### Task 14: Dockerfile and docker-compose.yml

**Files:**
- Modify: `requirements.txt`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Modify: `.gitignore`

- [ ] **Step 14.1: Add gunicorn to requirements.txt**

Append to `requirements.txt`:
```
gunicorn==22.0.0
```

- [ ] **Step 14.2: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 appuser

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Set ownership
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

# 2 workers is appropriate for a single-user personal tool
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", "app:app"]
```

- [ ] **Step 14.3: Create docker-compose.yml**

```yaml
version: '3.9'

services:
  web:
    build: .
    ports:
      - "5000:5000"
    volumes:
      # newsletter.db is volume-mounted so data persists across container rebuilds.
      # IMPORTANT: protect this file — it contains contact emails and the shortener API key.
      # Run: chmod 600 newsletter.db
      - ./newsletter.db:/app/newsletter.db
    env_file:
      - .env
    restart: unless-stopped
```

- [ ] **Step 14.4: Create .dockerignore**

```
.git
.env
__pycache__
*.pyc
*.pyo
.superpowers/
newsletter.db
tests/
docs/
*.md
.gitignore
```

- [ ] **Step 14.5: Update .gitignore**

Add to `.gitignore` if not already present:
```
.superpowers/
newsletter.db
```

- [ ] **Step 14.6: Verify Docker build succeeds**

```bash
cd /home/evan/projects/Dead-Man-Newsletter
docker build -t dead-man-newsletter . 2>&1 | tail -5
```

Expected: `Successfully built <image-id>` with no errors.

- [ ] **Step 14.7: Verify container starts and serves requests**

```bash
# Copy .env.example to .env if needed
cp .env.example .env 2>/dev/null || true

# Pre-create newsletter.db as a file — if missing, Docker creates it as a directory
touch newsletter.db
chmod 600 newsletter.db

docker compose up -d
sleep 3
curl -s http://localhost:5000/ -o /dev/null -w "%{http_code}"
docker compose down
```

Expected: `302` (redirect to setup or dashboard).

- [ ] **Step 14.8: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore .gitignore requirements.txt
git commit -m "feat: add Dockerfile and docker-compose for containerized deployment"
```

---

### Task 15: DNS Setup Guide

**Files:**
- Create: `docs/deployment/dns-setup.md`

- [ ] **Step 15.1: Create docs/deployment/dns-setup.md**

Write a complete guide covering:

```markdown
# DNS Setup Guide

How to point a domain name at your Dead-Man-Newsletter server so that tracking pixels
and unsubscribe links work from inside email clients.

## Prerequisites

- A running server with a **static public IP address** (e.g. an EC2 Elastic IP)
- A domain name you control (e.g. `newsletter.yourdomain.com`)

## What You're Doing

You're creating an **A record** — a DNS entry that maps a hostname to an IP address.
Once propagated, `https://newsletter.yourdomain.com` will resolve to your server.

Then you set that URL as the **Base URL** in Dead-Man-Newsletter's Settings page.

---

## AWS Route 53

1. Go to **Route 53 → Hosted Zones** and click your domain.
2. Click **Create record**.
3. Fill in:
   - **Record name:** `newsletter` (creates `newsletter.yourdomain.com`)
   - **Record type:** `A`
   - **Value:** Your server's public IP address
   - **TTL:** `300` (5 minutes — change to `3600` once stable)
4. Click **Create records**.

---

## GoDaddy

1. Go to **My Products → DNS** for your domain.
2. Click **Add New Record**.
3. Fill in:
   - **Type:** `A`
   - **Host:** `newsletter`
   - **Points to:** Your server's public IP address
   - **TTL:** `600 seconds`
4. Click **Save**.

---

## Squarespace

1. Go to **Domains → [your domain] → DNS Settings**.
2. Under **Custom Records**, click **Add Record**.
3. Fill in:
   - **Type:** `A`
   - **Host:** `newsletter`
   - **Data:** Your server's public IP address
   - **TTL:** `3600`
4. Click **Save**.

---

## Namecheap

1. Go to **Domain List → [your domain] → Advanced DNS**.
2. Under **Host Records**, click **Add New Record**.
3. Fill in:
   - **Type:** `A Record`
   - **Host:** `newsletter`
   - **Value:** Your server's public IP address
   - **TTL:** `Automatic`
4. Click the green checkmark to save.

---

## Cloudflare

1. Go to **[your domain] → DNS → Records**.
2. Click **Add record**.
3. Fill in:
   - **Type:** `A`
   - **Name:** `newsletter`
   - **IPv4 address:** Your server's public IP address
   - **Proxy status:** **DNS only** (grey cloud) — do NOT proxy through Cloudflare unless you've configured SSL termination on your server
   - **TTL:** `Auto`
4. Click **Save**.

---

## Verify Propagation

DNS changes can take a few minutes to a few hours to propagate. Check with:

```bash
# From any machine
dig newsletter.yourdomain.com
nslookup newsletter.yourdomain.com 8.8.8.8
```

Both should return your server's IP address.

You can also use https://dnschecker.org to see propagation status worldwide.

---

## Set Base URL in the App

Once DNS resolves correctly and SSL is configured (see `server-hardening.md`):

1. Open Dead-Man-Newsletter → **Settings**
2. Set **Base URL** to `https://newsletter.yourdomain.com`
3. Click **Save Settings**

Tracking pixels and unsubscribe links in all future emails will now use this URL.
```

- [ ] **Step 15.2: Commit**

```bash
git add docs/deployment/dns-setup.md
git commit -m "docs: add DNS setup guide for Route 53, GoDaddy, Squarespace, Namecheap, Cloudflare"
```

---

### Task 16: Server Hardening Guide

**Files:**
- Create: `docs/deployment/server-hardening.md`

- [ ] **Step 16.1: Create docs/deployment/server-hardening.md**

Write the complete guide:

```markdown
# Server Hardening Guide

How to deploy Dead-Man-Newsletter on an EC2 instance (or any Ubuntu VPS) securely.
This guide uses Docker to run the app behind nginx with Let's Encrypt SSL.

## Security Model

- **No SSH port open.** Use AWS SSM Session Manager for shell access instead.
- **Only ports 80 and 443** are open to the internet.
- **nginx** handles SSL termination and proxies to the app on localhost:5000.
- **fail2ban** is configured for SSH protection as a safety net (dormant while port 22 is closed).

---

## 1. EC2 Security Group

In the AWS console, set your instance's security group inbound rules to:

| Type  | Protocol | Port | Source    |
|-------|----------|------|-----------|
| HTTP  | TCP      | 80   | 0.0.0.0/0 |
| HTTPS | TCP      | 443  | 0.0.0.0/0 |

**Do not add an SSH rule (port 22).** You will use SSM Session Manager instead.

---

## 2. AWS SSM Session Manager (Shell Access Without SSH)

SSM Session Manager gives you a terminal session to your EC2 instance with no open ports.

**One-time setup:**

1. Attach the `AmazonSSMManagedInstanceCore` IAM policy to your EC2 instance role.
2. Ensure the SSM Agent is running (it's pre-installed on Amazon Linux 2 and Ubuntu 20.04+):
   ```bash
   sudo systemctl status amazon-ssm-agent
   ```

**Starting a session:**
```bash
# From your local machine (requires AWS CLI + session-manager-plugin)
aws ssm start-session --target i-0123456789abcdef0
```

Or use the AWS Console: **EC2 → Instances → [your instance] → Connect → Session Manager**.

---

## 3. System Updates and Non-Root User

```bash
sudo apt update && sudo apt upgrade -y

# Create a deploy user
sudo useradd -m -s /bin/bash deploy
sudo usermod -aG docker deploy

# Switch to deploy user for all app operations
sudo su - deploy
```

---

## 4. UFW Firewall (Second Layer)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# Do NOT open port 22 — using SSM
sudo ufw enable
sudo ufw status
```

Expected output:
```
Status: active
To                         Action      From
--                         ------      ----
80/tcp                     ALLOW       Anywhere
443/tcp                    ALLOW       Anywhere
```

---

## 5. Install Docker

```bash
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable docker
sudo systemctl start docker
```

---

## 6. Deploy the App

```bash
# As the deploy user
cd /home/deploy
git clone https://github.com/youruser/Dead-Man-Newsletter.git app
cd app

# Create .env from example and fill in your SMTP credentials
cp .env.example .env
nano .env

# Set newsletter.db permissions
touch newsletter.db
chmod 600 newsletter.db

# Start the app
docker compose up -d
```

Verify it's running:
```bash
curl http://localhost:5000/
# Should return a redirect (HTTP 302)
```

---

## 7. nginx Reverse Proxy

```bash
sudo apt install -y nginx
```

Create `/etc/nginx/sites-available/newsletter`:

```nginx
server {
    listen 80;
    server_name newsletter.yourdomain.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/newsletter /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 8. Let's Encrypt SSL (Certbot)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d newsletter.yourdomain.com
```

Follow the prompts. Certbot will:
1. Obtain a certificate from Let's Encrypt
2. Automatically update your nginx config to serve HTTPS
3. Set up an HTTP → HTTPS redirect

**Test auto-renewal:**
```bash
sudo certbot renew --dry-run
```

**Auto-renewal cron** (runs twice daily — standard Certbot recommendation):
```bash
sudo crontab -e
```
Add:
```
0 3,15 * * * certbot renew --quiet
```

---

## 9. fail2ban (SSH Protection)

fail2ban monitors log files and bans IPs that show brute-force behaviour.
Port 22 is currently closed, so this is dormant — but it activates automatically if SSH is ever opened.

```bash
sudo apt install -y fail2ban
```

Create `/etc/fail2ban/jail.local`:
```ini
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port    = ssh
logpath = %(sshd_log)s
backend = %(syslog_backend)s
```

```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
sudo fail2ban-client status sshd
```

---

## 10. Keep the App Running with systemd

Create `/etc/systemd/system/newsletter.service`:

```ini
[Unit]
Description=Dead-Man-Newsletter Docker App
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/deploy/app
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=deploy

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable newsletter
sudo systemctl start newsletter
```

---

## 11. Final Checklist

- [ ] EC2 security group: only ports 80 and 443 open
- [ ] SSM Session Manager working (tested a session)
- [ ] UFW enabled with only ports 80 and 443
- [ ] App running: `docker compose ps` shows `Up`
- [ ] nginx serving HTTP: `curl http://newsletter.yourdomain.com` → redirect
- [ ] SSL working: `curl https://newsletter.yourdomain.com` → app
- [ ] Certbot renewal tested: `sudo certbot renew --dry-run`
- [ ] fail2ban running: `sudo fail2ban-client status`
- [ ] systemd service enabled: `sudo systemctl is-enabled newsletter`
- [ ] `newsletter.db` permissions: `ls -la newsletter.db` shows `-rw-------`
- [ ] Base URL set in app Settings to `https://newsletter.yourdomain.com`
```

- [ ] **Step 16.2: Run full test suite one final time**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 16.3: Commit**

```bash
git add docs/deployment/server-hardening.md
git commit -m "docs: add server hardening guide with EC2, nginx, Certbot, fail2ban, systemd"
```

---

## Done

All 16 tasks complete. Update the spec's Master Tracking Table — all tasks should show `completed`.

Run a final end-to-end smoke test:
```bash
python app.py
# Open http://localhost:5000 and verify:
# - Settings page loads and saves
# - Template compose form shows Quill editors and font picker
# - Sending a test email works
# - /unsubscribe/<any-token> shows confirmation page
# - /track/1/abcd1234abcd1234.gif returns a GIF
```
