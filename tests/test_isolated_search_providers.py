"""TDD Tests for Isolated Search Providers (Workaround 2A: DDG HTML & Workaround 2B: Bing Web)."""

import pytest
from unittest.mock import patch, MagicMock
from isolated_experiments.ddg_html_provider import DDGHtmlSearchProvider
from isolated_experiments.bing_web_provider import BingWebSearchProvider


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

SAMPLE_BING_HTML = """
<!DOCTYPE html>
<html>
<body>
<ol id="b_results">
  <li class="b_algo">
    <h2>
      <a href="https://in.linkedin.com/in/satya-nadella">Satya Nadella - Chairman and CEO - Microsoft | LinkedIn</a>
    </h2>
    <div class="b_caption">
      <p>Satya Nadella is Chairman and Chief Executive Officer of Microsoft. Lead operations globally.</p>
    </div>
  </li>
  <li class="b_algo">
    <h2>
      <a href="https://in.linkedin.com/in/amy-hood">Amy Hood - Executive Vice President and CFO - Microsoft | LinkedIn</a>
    </h2>
    <div class="b_caption">
      <p>Amy Hood is Executive Vice President and Chief Financial Officer at Microsoft.</p>
    </div>
  </li>
</ol>
</body>
</html>
"""


# ==========================================
# Workaround 2A: DDG HTML Lite Tests
# ==========================================

def test_ddg_html_parser_extracts_results():
    """Verify DDG HTML parses title, link, and snippet correctly."""
    provider = DDGHtmlSearchProvider()
    results = provider.parse_html(SAMPLE_DDG_HTML, max_results=10)
    assert len(results) == 2
    assert results[0]["title"] == "Satya Nadella - Chairman and CEO - Microsoft | LinkedIn"
    assert results[0]["link"] == "https://in.linkedin.com/in/satya-nadella"
    assert "Chairman and Chief Executive Officer" in results[0]["snippet"]


def test_ddg_html_parser_respects_max_results():
    """Verify DDG HTML parser limits results to max_results."""
    provider = DDGHtmlSearchProvider()
    results = provider.parse_html(SAMPLE_DDG_HTML, max_results=1)
    assert len(results) == 1
    assert "Satya Nadella" in results[0]["title"]


def test_ddg_html_handles_empty_html():
    """Verify DDG HTML handles empty or no-result HTML without errors."""
    provider = DDGHtmlSearchProvider()
    results = provider.parse_html("<html><body><div class='no-results'>No results found</div></body></html>")
    assert results == []


@patch("urllib.request.urlopen")
def test_ddg_html_query_network_call(mock_urlopen):
    """Verify network request formatting and error resilience."""
    mock_response = MagicMock()
    mock_response.read.return_value = SAMPLE_DDG_HTML.encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    provider = DDGHtmlSearchProvider()
    results = provider.query("site:linkedin.com/in Microsoft CEO", max_results=5)
    assert len(results) == 2
    assert mock_urlopen.called


# ==========================================
# Workaround 2B: Bing Web Search Tests
# ==========================================

def test_bing_web_parser_extracts_results():
    """Verify Bing Web parses title, link, and snippet correctly."""
    provider = BingWebSearchProvider()
    results = provider.parse_html(SAMPLE_BING_HTML, max_results=10)
    assert len(results) == 2
    assert results[0]["title"] == "Satya Nadella - Chairman and CEO - Microsoft | LinkedIn"
    assert results[0]["link"] == "https://in.linkedin.com/in/satya-nadella"
    assert "Lead operations globally" in results[0]["snippet"]


def test_bing_web_parser_respects_max_results():
    """Verify Bing Web parser limits results to max_results."""
    provider = BingWebSearchProvider()
    results = provider.parse_html(SAMPLE_BING_HTML, max_results=1)
    assert len(results) == 1
    assert "Satya Nadella" in results[0]["title"]


def test_bing_web_handles_empty_html():
    """Verify Bing Web handles empty or no-result HTML without errors."""
    provider = BingWebSearchProvider()
    results = provider.parse_html("<html><body><div id='noresults'>No results found</div></body></html>")
    assert results == []


@patch("urllib.request.urlopen")
def test_bing_web_query_network_call(mock_urlopen):
    """Verify Bing Web network request formatting and error resilience."""
    mock_response = MagicMock()
    mock_response.read.return_value = SAMPLE_BING_HTML.encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    provider = BingWebSearchProvider()
    results = provider.query("site:linkedin.com/in Microsoft CEO", max_results=5)
    assert len(results) == 2
    assert mock_urlopen.called


def test_interface_compatibility_with_original_engine():
    """Verify both providers return the exact dictionary schema used by Prospector's LeadExtractor."""
    ddg_p = DDGHtmlSearchProvider()
    bing_p = BingWebSearchProvider()

    ddg_res = ddg_p.parse_html(SAMPLE_DDG_HTML, max_results=1)[0]
    bing_res = bing_p.parse_html(SAMPLE_BING_HTML, max_results=1)[0]

    for item in [ddg_res, bing_res]:
        assert "title" in item
        assert "link" in item
        assert "snippet" in item
        assert isinstance(item["title"], str)
        assert isinstance(item["link"], str)
        assert isinstance(item["snippet"], str)
