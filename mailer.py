import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(to_email, to_name, subject, html_body):
    """Send a single HTML email via SMTP."""
    host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    port = int(os.environ.get('SMTP_PORT', 587))
    user = os.environ.get('SMTP_USER', '')
    password = os.environ.get('SMTP_PASSWORD', '')
    from_name = os.environ.get('FROM_NAME', 'Newsletter')
    from_email = os.environ.get('FROM_EMAIL', user)

    if not user or not password:
        raise ValueError("SMTP_USER and SMTP_PASSWORD must be set in .env")

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f'{from_name} <{from_email}>'
    msg['To'] = f'{to_name} <{to_email}>' if to_name else to_email

    # Plain text fallback
    plain = "This email requires an HTML-capable email client to view."
    msg.attach(MIMEText(plain, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


def send_bulk(recipients, subject, html_body):
    """Send to a list of (email, name) tuples. Returns (success_count, errors)."""
    successes = 0
    errors = []
    for email, name in recipients:
        try:
            send_email(email, name, subject, html_body)
            successes += 1
        except Exception as e:
            errors.append((email, str(e)))
    return successes, errors
