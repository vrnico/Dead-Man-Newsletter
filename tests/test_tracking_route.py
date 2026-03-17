import email_builder


def _seed_send_and_contact(db, app):
    """Insert a template, a send row, and a contact. Return (send_id, valid_token)."""
    db.execute(
        "INSERT INTO templates (slug, name, subject_template, body_template, fields) "
        "VALUES ('test', 'Test', 'subj', '<p>body</p>', '[]')"
    )
    db.execute(
        "INSERT INTO contacts (email, name, groups, unsubscribe_token) "
        "VALUES ('track@example.com', 'Tracker', '[]', 'tok123')"
    )
    db.execute(
        "INSERT INTO sends (template_id, subject, body, recipient_count, open_count) "
        "VALUES (1, 'subj', '<p>body</p>', 1, 0)"
    )
    db.commit()
    send_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    token = email_builder._make_pixel_token(send_id, 'track@example.com', app.secret_key)
    return send_id, token


def test_pixel_returns_gif(client, db, app):
    send_id, token = _seed_send_and_contact(db, app)
    resp = client.get(f'/track/{send_id}/{token}.gif')
    assert resp.status_code == 200
    assert resp.content_type == 'image/gif'


def test_pixel_increments_open_count_with_valid_token(client, db, app):
    send_id, token = _seed_send_and_contact(db, app)
    client.get(f'/track/{send_id}/{token}.gif')
    count = db.execute(
        "SELECT open_count FROM sends WHERE id=?", (send_id,)
    ).fetchone()['open_count']
    assert count == 1


def test_pixel_does_not_increment_with_invalid_token(client, db, app):
    send_id, _ = _seed_send_and_contact(db, app)
    client.get(f'/track/{send_id}/abcd1234abcd1234.gif')
    count = db.execute(
        "SELECT open_count FROM sends WHERE id=?", (send_id,)
    ).fetchone()['open_count']
    assert count == 0


def test_pixel_unknown_send_id_still_returns_gif(client):
    resp = client.get('/track/99999/abcd1234abcd1234.gif')
    assert resp.status_code == 200
    assert resp.content_type == 'image/gif'


def test_pixel_invalid_token_format_still_returns_gif(client, db, app):
    send_id, _ = _seed_send_and_contact(db, app)
    resp = client.get(f'/track/{send_id}/not-valid-token.gif')
    assert resp.status_code == 200
    assert resp.content_type == 'image/gif'


def test_history_page_shows_open_count(client, db, app):
    send_id, _ = _seed_send_and_contact(db, app)
    db.execute("UPDATE sends SET open_count=7 WHERE id=?", (send_id,))
    db.commit()
    resp = client.get('/history')
    assert b'7' in resp.data
