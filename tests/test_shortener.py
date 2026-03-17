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
