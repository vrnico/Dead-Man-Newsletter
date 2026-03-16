import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'newsletter.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            groups TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            unsubscribed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            subject_template TEXT NOT NULL DEFAULT '',
            body_template TEXT NOT NULL,
            fields TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            recipient_count INTEGER NOT NULL DEFAULT 0,
            sent_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (template_id) REFERENCES templates(id)
        );

        CREATE TABLE IF NOT EXISTS deadman_switch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            active INTEGER NOT NULL DEFAULT 0,
            check_in_interval_hours INTEGER NOT NULL DEFAULT 72,
            last_check_in TEXT NOT NULL DEFAULT (datetime('now')),
            recipient_group TEXT NOT NULL DEFAULT 'emergency',
            subject TEXT NOT NULL DEFAULT 'Emergency: I may need help',
            body TEXT NOT NULL DEFAULT '',
            trip_details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    ''')
    conn.commit()

    # Seed default templates if empty
    if conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0] == 0:
        _seed_templates(conn)

    # Seed deadman switch config if empty
    if conn.execute("SELECT COUNT(*) FROM deadman_switch").fetchone()[0] == 0:
        conn.execute('''INSERT INTO deadman_switch
            (active, check_in_interval_hours, body, trip_details)
            VALUES (0, 72, '', '')''')
        conn.commit()

    conn.close()


# =====================================================================
# Style variables available in ALL templates:
#   {{_primary}}     - primary/accent color      (default varies by template)
#   {{_secondary}}   - secondary color           (default varies)
#   {{_bg}}          - email background color     (default #ffffff)
#   {{_text}}        - main text color            (default #333333)
#   {{_font}}        - font-family string         (default varies)
#   {{_header_img}}  - header/banner image URL    (optional)
#   {{_logo_img}}    - logo image URL             (optional)
#   {{_footer}}      - footer text                (optional)
# =====================================================================

def _seed_templates(conn):
    templates = [
        {
            'slug': 'newsletter',
            'name': 'Regular Newsletter',
            'description': 'A classic newsletter with a greeting, main content sections, and a sign-off.',
            'subject_template': '{{title}}',
            'fields': json.dumps([
                {'name': 'title', 'label': 'Newsletter Title', 'type': 'text'},
                {'name': 'intro', 'label': 'Introduction', 'type': 'textarea'},
                {'name': 'section1_title', 'label': 'Section 1 Title', 'type': 'text'},
                {'name': 'section1_body', 'label': 'Section 1 Content', 'type': 'textarea'},
                {'name': 'section2_title', 'label': 'Section 2 Title (optional)', 'type': 'text'},
                {'name': 'section2_body', 'label': 'Section 2 Content (optional)', 'type': 'textarea'},
                {'name': 'section3_title', 'label': 'Section 3 Title (optional)', 'type': 'text'},
                {'name': 'section3_body', 'label': 'Section 3 Content (optional)', 'type': 'textarea'},
                {'name': 'closing', 'label': 'Closing Message', 'type': 'textarea'},
            ]),
            'body_template': '''<div style="max-width:600px;margin:0 auto;font-family:{{_font}};background:{{_bg}};border-radius:12px;overflow:hidden;">
  {% if _header_img %}<img src="{{_header_img}}" alt="" style="width:100%;display:block;">{% endif %}
  <div style="background:{{_primary}};padding:32px 30px 24px;">
    {% if _logo_img %}<img src="{{_logo_img}}" alt="" style="max-height:48px;margin-bottom:12px;">{% endif %}
    <h1 style="color:#fff;margin:0;font-size:28px;letter-spacing:-0.5px;">{{title}}</h1>
  </div>
  <div style="padding:30px;color:{{_text}};">
    <p style="font-size:17px;line-height:1.7;margin:0 0 24px;">{{intro}}</p>
    {% if section1_title %}
    <h2 style="color:{{_primary}};margin:28px 0 10px;font-size:20px;border-left:4px solid {{_primary}};padding-left:12px;">{{section1_title}}</h2>
    {% endif %}
    <p style="font-size:16px;line-height:1.7;margin:0 0 20px;">{{section1_body}}</p>
    {% if section2_title %}
    <h2 style="color:{{_primary}};margin:28px 0 10px;font-size:20px;border-left:4px solid {{_primary}};padding-left:12px;">{{section2_title}}</h2>
    <p style="font-size:16px;line-height:1.7;margin:0 0 20px;">{{section2_body}}</p>
    {% endif %}
    {% if section3_title %}
    <h2 style="color:{{_primary}};margin:28px 0 10px;font-size:20px;border-left:4px solid {{_primary}};padding-left:12px;">{{section3_title}}</h2>
    <p style="font-size:16px;line-height:1.7;margin:0 0 20px;">{{section3_body}}</p>
    {% endif %}
    <div style="border-top:2px solid {{_secondary}};margin:32px 0 20px;"></div>
    <p style="font-size:16px;line-height:1.7;margin:0;">{{closing}}</p>
  </div>
  {% if _footer %}
  <div style="background:{{_secondary}};padding:16px 30px;font-size:13px;color:{{_text}};opacity:0.7;text-align:center;">{{_footer}}</div>
  {% endif %}
</div>''',
        },
        {
            'slug': 'job-seeking',
            'name': "I'm Looking for Work",
            'description': 'Let your network know you\'re available. Highlight your skills, experience, and what you\'re looking for.',
            'subject_template': "{{name}} is looking for new opportunities",
            'fields': json.dumps([
                {'name': 'name', 'label': 'Your Name', 'type': 'text'},
                {'name': 'tagline', 'label': 'Tagline (e.g. "Full-Stack Dev | 8 Years | Open to Remote")', 'type': 'text'},
                {'name': 'current_status', 'label': 'Current Status (e.g. "Recently laid off", "Wrapping up a contract")', 'type': 'text'},
                {'name': 'looking_for', 'label': 'What You\'re Looking For', 'type': 'textarea'},
                {'name': 'skills', 'label': 'Key Skills & Experience', 'type': 'textarea'},
                {'name': 'portfolio_url', 'label': 'Portfolio / LinkedIn URL', 'type': 'text'},
                {'name': 'personal_note', 'label': 'Personal Note', 'type': 'textarea'},
            ]),
            'body_template': '''<div style="max-width:600px;margin:0 auto;font-family:{{_font}};background:{{_bg}};border-radius:12px;overflow:hidden;">
  {% if _header_img %}<img src="{{_header_img}}" alt="" style="width:100%;display:block;">{% endif %}
  <div style="background:{{_primary}};padding:36px 30px;text-align:center;">
    {% if _logo_img %}<img src="{{_logo_img}}" alt="" style="width:80px;height:80px;border-radius:50%;border:3px solid rgba(255,255,255,0.3);margin-bottom:12px;">{% endif %}
    <h1 style="color:#fff;margin:0;font-size:26px;">{{name}}</h1>
    {% if tagline %}<p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:15px;">{{tagline}}</p>{% endif %}
  </div>
  <div style="padding:30px;color:{{_text}};">
    <div style="background:{{_secondary}};padding:16px 20px;border-radius:8px;border-left:4px solid {{_primary}};margin-bottom:24px;">
      <strong style="color:{{_primary}};">Status:</strong> {{current_status}}
    </div>
    <h2 style="color:{{_primary}};font-size:18px;margin:0 0 10px;">What I'm Looking For</h2>
    <p style="font-size:16px;line-height:1.7;margin:0 0 24px;">{{looking_for}}</p>
    <h2 style="color:{{_primary}};font-size:18px;margin:0 0 10px;">Skills & Experience</h2>
    <p style="font-size:16px;line-height:1.7;margin:0 0 24px;">{{skills}}</p>
    {% if portfolio_url %}
    <div style="text-align:center;margin:24px 0;">
      <a href="{{portfolio_url}}" style="display:inline-block;background:{{_primary}};color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">View My Work &rarr;</a>
    </div>
    {% endif %}
    {% if personal_note %}
    <div style="border-top:2px solid {{_secondary}};margin:24px 0;"></div>
    <p style="font-size:16px;line-height:1.7;font-style:italic;margin:0;">{{personal_note}}</p>
    {% endif %}
    <p style="font-size:14px;color:#999;margin:28px 0 0;text-align:center;">
      Know of something? I'd love an intro. Feel free to forward this along!
    </p>
  </div>
  {% if _footer %}
  <div style="background:{{_secondary}};padding:16px 30px;font-size:13px;color:{{_text}};opacity:0.7;text-align:center;">{{_footer}}</div>
  {% endif %}
</div>''',
        },
        {
            'slug': 'social-roundup',
            'name': 'Social Media Roundup',
            'description': "Recap what you posted this week across platforms. Great for influencers and creators.",
            'subject_template': "{{creator_name}}'s Weekly Roundup — {{week_label}}",
            'fields': json.dumps([
                {'name': 'creator_name', 'label': 'Your Name / Handle', 'type': 'text'},
                {'name': 'week_label', 'label': 'Week Label (e.g. "March 10-16")', 'type': 'text'},
                {'name': 'intro_note', 'label': 'Quick Intro Note', 'type': 'textarea'},
                {'name': 'highlight1', 'label': 'Highlight 1 (title or link)', 'type': 'textarea'},
                {'name': 'highlight2', 'label': 'Highlight 2 (optional)', 'type': 'textarea'},
                {'name': 'highlight3', 'label': 'Highlight 3 (optional)', 'type': 'textarea'},
                {'name': 'stats', 'label': 'Stats / Milestones (optional)', 'type': 'textarea'},
                {'name': 'upcoming', 'label': 'Coming Up Next Week', 'type': 'textarea'},
            ]),
            'body_template': '''<div style="max-width:600px;margin:0 auto;font-family:{{_font}};background:{{_bg}};border-radius:12px;overflow:hidden;">
  {% if _header_img %}<img src="{{_header_img}}" alt="" style="width:100%;display:block;">{% endif %}
  <div style="background:linear-gradient(135deg,{{_primary}} 0%,{{_secondary}} 100%);padding:32px 30px;color:white;">
    {% if _logo_img %}<img src="{{_logo_img}}" alt="" style="max-height:40px;margin-bottom:10px;">{% endif %}
    <h1 style="margin:0;font-size:26px;">Weekly Roundup</h1>
    <p style="margin:4px 0 0;opacity:0.9;font-size:15px;">{{creator_name}} &mdash; {{week_label}}</p>
  </div>
  <div style="padding:30px;color:{{_text}};">
    <p style="font-size:17px;line-height:1.7;margin:0 0 24px;">{{intro_note}}</p>
    <h2 style="color:{{_primary}};font-size:18px;margin:0 0 14px;">Highlights</h2>
    {% if highlight1 %}
    <div style="background:{{_secondary}};border-radius:8px;padding:16px 20px;margin-bottom:10px;border-left:4px solid {{_primary}};">
      <p style="margin:0;font-size:15px;line-height:1.6;">{{highlight1}}</p>
    </div>
    {% endif %}
    {% if highlight2 %}
    <div style="background:{{_secondary}};border-radius:8px;padding:16px 20px;margin-bottom:10px;border-left:4px solid {{_primary}};">
      <p style="margin:0;font-size:15px;line-height:1.6;">{{highlight2}}</p>
    </div>
    {% endif %}
    {% if highlight3 %}
    <div style="background:{{_secondary}};border-radius:8px;padding:16px 20px;margin-bottom:10px;border-left:4px solid {{_primary}};">
      <p style="margin:0;font-size:15px;line-height:1.6;">{{highlight3}}</p>
    </div>
    {% endif %}
    {% if stats %}
    <h2 style="color:{{_primary}};font-size:18px;margin:24px 0 10px;">Stats & Milestones</h2>
    <p style="font-size:16px;line-height:1.7;margin:0 0 20px;">{{stats}}</p>
    {% endif %}
    {% if upcoming %}
    <h2 style="color:{{_primary}};font-size:18px;margin:24px 0 10px;">Coming Up</h2>
    <p style="font-size:16px;line-height:1.7;margin:0;">{{upcoming}}</p>
    {% endif %}
  </div>
  {% if _footer %}
  <div style="background:{{_secondary}};padding:16px 30px;font-size:13px;color:{{_text}};opacity:0.7;text-align:center;">{{_footer}}</div>
  {% endif %}
</div>''',
        },
        {
            'slug': 'new-videos',
            'name': 'New Videos',
            'description': 'Announce your latest video releases with thumbnails and links.',
            'subject_template': 'New from {{channel_name}}: {{video1_title}}',
            'fields': json.dumps([
                {'name': 'channel_name', 'label': 'Channel / Creator Name', 'type': 'text'},
                {'name': 'intro', 'label': 'Quick Intro', 'type': 'textarea'},
                {'name': 'video1_title', 'label': 'Video 1 Title', 'type': 'text'},
                {'name': 'video1_url', 'label': 'Video 1 URL', 'type': 'text'},
                {'name': 'video1_thumb', 'label': 'Video 1 Thumbnail URL (optional)', 'type': 'text'},
                {'name': 'video1_description', 'label': 'Video 1 Description', 'type': 'textarea'},
                {'name': 'video2_title', 'label': 'Video 2 Title (optional)', 'type': 'text'},
                {'name': 'video2_url', 'label': 'Video 2 URL (optional)', 'type': 'text'},
                {'name': 'video2_thumb', 'label': 'Video 2 Thumbnail URL (optional)', 'type': 'text'},
                {'name': 'video2_description', 'label': 'Video 2 Description (optional)', 'type': 'textarea'},
                {'name': 'video3_title', 'label': 'Video 3 Title (optional)', 'type': 'text'},
                {'name': 'video3_url', 'label': 'Video 3 URL (optional)', 'type': 'text'},
                {'name': 'video3_thumb', 'label': 'Video 3 Thumbnail URL (optional)', 'type': 'text'},
                {'name': 'video3_description', 'label': 'Video 3 Description (optional)', 'type': 'textarea'},
                {'name': 'outro', 'label': 'Closing Note', 'type': 'textarea'},
            ]),
            'body_template': '''<div style="max-width:600px;margin:0 auto;font-family:{{_font}};background:{{_bg}};border-radius:12px;overflow:hidden;">
  {% if _header_img %}<img src="{{_header_img}}" alt="" style="width:100%;display:block;">{% endif %}
  <div style="background:{{_primary}};padding:28px 30px;">
    {% if _logo_img %}<img src="{{_logo_img}}" alt="" style="max-height:40px;margin-bottom:8px;">{% endif %}
    <h1 style="color:#fff;margin:0;font-size:26px;">{{channel_name}}</h1>
  </div>
  <div style="padding:30px;color:{{_text}};">
    <p style="font-size:17px;line-height:1.7;margin:0 0 24px;">{{intro}}</p>
    <div style="background:{{_secondary}};border-radius:10px;overflow:hidden;margin-bottom:16px;">
      {% if video1_thumb %}<a href="{{video1_url}}"><img src="{{video1_thumb}}" alt="" style="width:100%;display:block;"></a>{% endif %}
      <div style="padding:20px;">
        <h2 style="color:{{_text}};margin:0 0 8px;font-size:18px;">{{video1_title}}</h2>
        <p style="font-size:15px;line-height:1.6;margin:0 0 14px;color:{{_text}};opacity:0.8;">{{video1_description}}</p>
        <a href="{{video1_url}}" style="display:inline-block;background:{{_primary}};color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px;">&#9654; Watch Now</a>
      </div>
    </div>
    {% if video2_title %}
    <div style="background:{{_secondary}};border-radius:10px;overflow:hidden;margin-bottom:16px;">
      {% if video2_thumb %}<a href="{{video2_url}}"><img src="{{video2_thumb}}" alt="" style="width:100%;display:block;"></a>{% endif %}
      <div style="padding:20px;">
        <h2 style="color:{{_text}};margin:0 0 8px;font-size:18px;">{{video2_title}}</h2>
        <p style="font-size:15px;line-height:1.6;margin:0 0 14px;color:{{_text}};opacity:0.8;">{{video2_description}}</p>
        <a href="{{video2_url}}" style="display:inline-block;background:{{_primary}};color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px;">&#9654; Watch Now</a>
      </div>
    </div>
    {% endif %}
    {% if video3_title %}
    <div style="background:{{_secondary}};border-radius:10px;overflow:hidden;margin-bottom:16px;">
      {% if video3_thumb %}<a href="{{video3_url}}"><img src="{{video3_thumb}}" alt="" style="width:100%;display:block;"></a>{% endif %}
      <div style="padding:20px;">
        <h2 style="color:{{_text}};margin:0 0 8px;font-size:18px;">{{video3_title}}</h2>
        <p style="font-size:15px;line-height:1.6;margin:0 0 14px;color:{{_text}};opacity:0.8;">{{video3_description}}</p>
        <a href="{{video3_url}}" style="display:inline-block;background:{{_primary}};color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px;">&#9654; Watch Now</a>
      </div>
    </div>
    {% endif %}
    {% if outro %}
    <div style="border-top:2px solid {{_secondary}};margin:24px 0;"></div>
    <p style="font-size:15px;line-height:1.6;margin:0;">{{outro}}</p>
    {% endif %}
  </div>
  {% if _footer %}
  <div style="background:{{_secondary}};padding:16px 30px;font-size:13px;color:{{_text}};opacity:0.7;text-align:center;">{{_footer}}</div>
  {% endif %}
</div>''',
        },
        {
            'slug': 'deadman-switch',
            'name': "Dead Man's Switch (Safety Alert)",
            'description': "Automatically sent if you don't check in. For solo travel, backpacking, etc.",
            'subject_template': 'SAFETY ALERT: {{traveler_name}} has not checked in',
            'fields': json.dumps([
                {'name': 'traveler_name', 'label': 'Your Name', 'type': 'text'},
                {'name': 'trip_name', 'label': 'Trip Name / Location', 'type': 'text'},
                {'name': 'last_known_location', 'label': 'Last Known Location / Trailhead', 'type': 'text'},
                {'name': 'trip_dates', 'label': 'Trip Dates', 'type': 'text'},
                {'name': 'itinerary', 'label': 'Planned Itinerary / Route', 'type': 'textarea'},
                {'name': 'gear_description', 'label': 'Gear / What I\'m Wearing', 'type': 'textarea'},
                {'name': 'vehicle_info', 'label': 'Vehicle Info (parked at trailhead)', 'type': 'text'},
                {'name': 'emergency_contacts', 'label': 'Emergency Contacts / Who to Call', 'type': 'textarea'},
                {'name': 'instructions', 'label': 'What To Do (call ranger station, etc.)', 'type': 'textarea'},
            ]),
            'body_template': '''<div style="max-width:600px;margin:0 auto;font-family:{{_font}};background:{{_bg}};border-radius:12px;overflow:hidden;">
  <div style="background:#d63031;padding:24px 30px;text-align:center;color:white;">
    <h1 style="margin:0;font-size:26px;">SAFETY ALERT</h1>
    <p style="margin:6px 0 0;font-size:17px;">{{traveler_name}} has not checked in</p>
  </div>
  <div style="padding:30px;color:{{_text}};border:2px solid #d63031;border-top:none;border-radius:0 0 12px 12px;">
    <p style="font-size:16px;line-height:1.7;margin:0 0 20px;">
      This is an automated safety message. <strong>{{traveler_name}}</strong> set up this alert
      before going on a trip and has not checked in within the expected timeframe.
      <strong>This may mean they need help.</strong>
    </p>
    {% if _header_img %}<img src="{{_header_img}}" alt="Trip photo" style="width:100%;border-radius:8px;margin-bottom:20px;">{% endif %}
    <h2 style="color:#d63031;font-size:18px;margin:0 0 10px;">Trip Details</h2>
    <table style="width:100%;font-size:15px;line-height:1.6;margin-bottom:20px;">
      <tr><td style="padding:6px 12px;font-weight:bold;vertical-align:top;width:140px;">Trip:</td><td style="padding:6px 12px;">{{trip_name}}</td></tr>
      <tr><td style="padding:6px 12px;font-weight:bold;vertical-align:top;">Dates:</td><td style="padding:6px 12px;">{{trip_dates}}</td></tr>
      <tr><td style="padding:6px 12px;font-weight:bold;vertical-align:top;">Last Known Location:</td><td style="padding:6px 12px;">{{last_known_location}}</td></tr>
      {% if vehicle_info %}
      <tr><td style="padding:6px 12px;font-weight:bold;vertical-align:top;">Vehicle:</td><td style="padding:6px 12px;">{{vehicle_info}}</td></tr>
      {% endif %}
    </table>
    {% if itinerary %}
    <h2 style="color:#d63031;font-size:18px;margin:0 0 10px;">Planned Route / Itinerary</h2>
    <p style="font-size:15px;line-height:1.7;background:#f9f9f9;padding:16px;border-radius:8px;border:1px solid #eee;margin:0 0 20px;">{{itinerary}}</p>
    {% endif %}
    {% if gear_description %}
    <h2 style="color:#d63031;font-size:18px;margin:0 0 10px;">Gear / Appearance</h2>
    <p style="font-size:15px;line-height:1.7;margin:0 0 20px;">{{gear_description}}</p>
    {% endif %}
    {% if emergency_contacts %}
    <h2 style="color:#d63031;font-size:18px;margin:0 0 10px;">Emergency Contacts</h2>
    <p style="font-size:15px;line-height:1.7;margin:0 0 20px;">{{emergency_contacts}}</p>
    {% endif %}
    {% if instructions %}
    <h2 style="color:#d63031;font-size:18px;margin:0 0 10px;">What To Do</h2>
    <div style="background:#fff5f5;border:2px solid #d63031;border-radius:8px;padding:16px 20px;font-size:16px;line-height:1.7;font-weight:bold;">
      {{instructions}}
    </div>
    {% endif %}
    <div style="border-top:2px solid #d63031;margin:28px 0 16px;"></div>
    <p style="font-size:13px;color:#999;text-align:center;margin:0;">
      Sent automatically because {{traveler_name}} did not check in.
      If confirmed safe, no action needed.
    </p>
  </div>
</div>''',
        },
    ]

    for t in templates:
        conn.execute(
            '''INSERT INTO templates (slug, name, description, subject_template, body_template, fields)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (t['slug'], t['name'], t['description'], t['subject_template'], t['body_template'], t['fields'])
        )
    conn.commit()
