# NewsLetterGo

A free, self-hosted email newsletter app with templates and a dead man's switch safety feature.

## Quick Start

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd WEEK_6

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your email
cp .env.example .env
# Edit .env with your SMTP credentials (see Email Setup below)

# 5. Run it
python app.py
# Open http://localhost:5000
```

## Email Setup (Free Options)

### Gmail (Recommended for getting started)

Gmail lets you send **500 emails/day** for free via SMTP.

1. **Enable 2-Factor Authentication** on your Google account
   - Go to https://myaccount.google.com/security
   - Turn on 2-Step Verification

2. **Create an App Password**
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" as the app
   - Select your device
   - Click "Generate"
   - Copy the 16-character password

3. **Configure `.env`**:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=you@gmail.com
   SMTP_PASSWORD=xxxx xxxx xxxx xxxx   # The app password from step 2
   FROM_NAME=Your Name
   FROM_EMAIL=you@gmail.com
   ```

> **Important:** Use an App Password, NOT your regular Gmail password. Regular passwords won't work with SMTP.

---

### Outlook / Hotmail (Free)

500 emails/day limit.

```
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_USER=you@outlook.com
SMTP_PASSWORD=your-password
FROM_NAME=Your Name
FROM_EMAIL=you@outlook.com
```

> Note: Outlook may require you to enable SMTP access in settings. Go to Settings > Mail > Sync email > POP and IMAP, and set "Let devices and apps use POP" to Yes.

---

### Yahoo Mail (Free)

```
SMTP_HOST=smtp.mail.yahoo.com
SMTP_PORT=587
SMTP_USER=you@yahoo.com
SMTP_PASSWORD=your-app-password
FROM_NAME=Your Name
FROM_EMAIL=you@yahoo.com
```

Generate an app password at: Account Security > Generate app password

---

### Zoho Mail (Free tier — 50 emails/day)

```
SMTP_HOST=smtp.zoho.com
SMTP_PORT=587
SMTP_USER=you@zoho.com
SMTP_PASSWORD=your-password
FROM_NAME=Your Name
FROM_EMAIL=you@zoho.com
```

---

### ProtonMail (Free with Bridge)

Requires ProtonMail Bridge (desktop app) running locally.

```
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
SMTP_USER=you@protonmail.com
SMTP_PASSWORD=bridge-password
FROM_NAME=Your Name
FROM_EMAIL=you@protonmail.com
```

---

### Brevo (formerly Sendinblue) — Free tier: 300 emails/day

Best option if you need higher volume for free.

1. Sign up at https://www.brevo.com (free)
2. Go to SMTP & API > SMTP Settings
3. Get your SMTP credentials

```
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=your-brevo-login-email
SMTP_PASSWORD=your-smtp-key
FROM_NAME=Your Name
FROM_EMAIL=you@yourdomain.com
```

---

### Mailgun (Free tier: 100 emails/day)

1. Sign up at https://www.mailgun.com
2. Verify a domain or use the sandbox domain
3. Get SMTP credentials from the domain settings

```
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USER=postmaster@your-domain.mailgun.org
SMTP_PASSWORD=your-smtp-password
FROM_NAME=Your Name
FROM_EMAIL=you@your-domain.mailgun.org
```

---

## Templates

The app comes with 5 built-in templates:

| Template | Use Case |
|----------|----------|
| **Regular Newsletter** | Classic newsletter with sections |
| **I'm Looking for Work** | Job seeking announcement to your network |
| **Social Media Roundup** | Weekly recap of your posts across platforms |
| **New Videos** | Announce new YouTube/video content |
| **Dead Man's Switch** | Emergency alert if you don't check in (for solo travel) |

All templates are stored in the database and can be customized by editing `database.py`.

## Dead Man's Switch

The safety feature for solo travelers:

1. Add emergency contacts and put them in the "emergency" group
2. Go to Safety Switch, fill in your trip details
3. Activate the switch before your trip
4. Check in regularly by clicking "I'm OK"
5. If you miss your check-in window, the alert fires automatically

**For real trips:** Deploy this to a server that stays online. Running locally only works if your computer stays on. Options:
- A cheap VPS ($5/mo on DigitalOcean, Linode, etc.)
- A free Render.com or Railway.app deployment
- A Raspberry Pi at home

## Deployment

### Render.com (Free)

1. Push to GitHub
2. Create a new Web Service on Render
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `gunicorn app:app`
5. Add your `.env` variables in the Environment tab

Add `gunicorn` to requirements.txt for production:
```
pip install gunicorn
echo "gunicorn==21.2.0" >> requirements.txt
```

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt gunicorn
COPY . .
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
```

## Project Structure

```
├── app.py              # Main Flask application
├── database.py         # SQLite database setup & seed data
├── mailer.py           # SMTP email sending
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variable template
├── .gitignore
├── templates/          # HTML templates (Jinja2)
│   ├── base.html       # Layout with dark theme
│   ├── dashboard.html
│   ├── contacts.html
│   ├── templates.html
│   ├── template_detail.html
│   ├── deadman.html
│   ├── history.html
│   └── history_detail.html
└── newsletter.db       # SQLite database (auto-created)
```

## License

Do whatever you want with it. No warranty.
