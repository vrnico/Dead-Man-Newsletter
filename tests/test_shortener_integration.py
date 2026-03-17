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

    with patch('app.send_email', side_effect=mock_send), \
         patch('shortener.shorten_url', return_value='https://bit.ly/short') as mock_shorten:
        client.post('/templates/link-tpl/send', data={'target_group': 'all'})

    mock_shorten.assert_called()
    assert 'https://bit.ly/short' in sent_bodies[0]


def test_shortener_not_called_when_disabled(client, db):
    _seed(db)
    db.execute("UPDATE settings SET value='0' WHERE key='url_shortener_enabled'")
    db.commit()

    with patch('app.send_email'), \
         patch('shortener.shorten_url') as mock_shorten:
        client.post('/templates/link-tpl/send', data={'target_group': 'all'})

    mock_shorten.assert_not_called()
