"""Tests for Resilient Multi-Backend Search Engine and Direct HTML Fallback."""

import pytest
from unittest.mock import patch, MagicMock
from prospector.ddg_html_provider import DDGHtmlSearchProvider
from prospector.search_engine import SearchEngine


SAMPLE_DDG_HTML = """
<!DOCTYPE html>
<html>
<body>
<div class="results">
  <div class="result results_links results_links_deep web-result">
    <div class="links_main links_deep result__body">
      <h2 class="result__title">
        <a class="result__url" href="https://in.linkedin.com/in/satya-nadella">Satya Nadella - Chairman and CEO - Microsoft | LinkedIn</a>
      </h2>
      <a class="result__snippet" href="https://in.linkedin.com/in/satya-nadella">
        Satya Nadella is Chairman and Chief Executive Officer of Microsoft. Based in Redmond, WA.
      </a>
    </div>
  </div>
  <div class="result results_links results_links_deep web-result">
    <div class="links_main links_deep result__body">
      <h2 class="result__title">
        <a class="result__url" href="https://in.linkedin.com/in/amy-hood">Amy Hood - Executive Vice President and CFO - Microsoft | LinkedIn</a>
      </h2>
      <a class="result__snippet" href="https://in.linkedin.com/in/amy-hood">
        Amy Hood is Executive Vice President and Chief Financial Officer at Microsoft.
      </a>
    </div>
  </div>
</div>
</body>
</html>
"""


def test_ddg_html_provider_parse():
    provider = DDGHtmlSearchProvider()
    results = provider.parse_html(SAMPLE_DDG_HTML, max_results=5)
    assert len(results) == 2
    assert results[0]["title"] == "Satya Nadella - Chairman and CEO - Microsoft | LinkedIn"
    assert "https://in.linkedin.com/in/satya-nadella" in results[0]["link"]
    assert "Satya Nadella is Chairman" in results[0]["snippet"]


def test_ddg_html_provider_empty():
    provider = DDGHtmlSearchProvider()
    results = provider.parse_html("<html><body>No results</body></html>", max_results=5)
    assert results == []


@patch("urllib.request.urlopen")
def test_ddg_html_provider_query(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = SAMPLE_DDG_HTML.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    provider = DDGHtmlSearchProvider()
    results = provider.query("site:linkedin.com/in Satya Nadella Microsoft", max_results=2)
    assert len(results) == 2
    assert mock_urlopen.called


def test_search_engine_fallback_chain():
    """Verify that if primary DDGS backends fail or return empty, the direct HTML provider is invoked."""
    engine = SearchEngine()

    # Mock bing provider and ddgs client to return empty
    engine.bing_provider = MagicMock()
    engine.bing_provider.query.return_value = []
    engine._ddgs_client = MagicMock()
    engine._ddgs_client.text.return_value = []

    # Mock direct html provider
    engine.html_provider = MagicMock()
    engine.html_provider.query.return_value = [
        {
            "title": "Satya Nadella - CEO - Microsoft",
            "link": "https://linkedin.com/in/satyanadella",
            "snippet": "CEO at Microsoft",
        }
    ]

    with patch.object(engine, "_init_ddgs_client"):
        with patch("time.sleep"):
            results = engine.query("site:linkedin.com/in Microsoft CEO", max_results=5)

    assert len(results) == 1
    assert results[0]["title"] == "Satya Nadella - CEO - Microsoft"
    assert engine.html_provider.query.called
