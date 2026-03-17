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
