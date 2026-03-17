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

    with patch('app.send_email', side_effect=mock_send):
        from app import check_deadman_switch
        result = check_deadman_switch()

    assert result == 'triggered'
    assert len(sent_bodies) == 1
    assert '<!DOCTYPE html>' in sent_bodies[0]
    assert '/unsubscribe/bobtoken123456' in sent_bodies[0]


def test_deadman_send_creates_sends_row(db, app):
    _setup_deadman(db)
    with patch('app.send_email'):
        from app import check_deadman_switch
        check_deadman_switch()

    count = db.execute("SELECT COUNT(*) FROM sends").fetchone()[0]
    assert count == 1
