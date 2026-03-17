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
