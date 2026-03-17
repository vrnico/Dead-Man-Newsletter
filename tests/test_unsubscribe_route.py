def _add_contact(db, email, token):
    db.execute(
        "INSERT INTO contacts (email, name, groups, unsubscribe_token) "
        "VALUES (?, '', '[]', ?)",
        (email, token)
    )
    db.commit()


def test_get_shows_confirmation_form(client, db):
    _add_contact(db, 'user@example.com', 'validtoken123abc')
    resp = client.get('/unsubscribe/validtoken123abc')
    assert resp.status_code == 200
    assert b'Confirm Unsubscribe' in resp.data
    # GET should NOT unsubscribe
    row = db.execute(
        "SELECT unsubscribed FROM contacts WHERE email='user@example.com'"
    ).fetchone()
    assert row['unsubscribed'] == 0


def test_post_unsubscribes_contact(client, db):
    _add_contact(db, 'user@example.com', 'validtoken123abc')
    resp = client.post('/unsubscribe/validtoken123abc')
    assert resp.status_code == 200
    row = db.execute(
        "SELECT unsubscribed FROM contacts WHERE email='user@example.com'"
    ).fetchone()
    assert row['unsubscribed'] == 1


def test_post_shows_confirmed_message(client, db):
    _add_contact(db, 'user2@example.com', 'anothertoken456')
    resp = client.post('/unsubscribe/anothertoken456')
    assert resp.status_code == 200
    assert b"unsubscribed" in resp.data.lower()


def test_invalid_token_returns_200_no_error(client):
    resp = client.get('/unsubscribe/doesnotexist')
    assert resp.status_code == 200


def test_invalid_token_post_returns_200(client):
    resp = client.post('/unsubscribe/doesnotexist')
    assert resp.status_code == 200
    assert b"unsubscribed" in resp.data.lower()
