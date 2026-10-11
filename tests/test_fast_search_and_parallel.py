"""TDD Tests for Fast Direct Bing Search Provider and Concurrent Batch Pipeline."""

import pytest
from unittest.mock import patch, MagicMock
from prospector.bing_web_provider import BingWebSearchProvider
from prospector.search_engine import SearchEngine
from prospector.pipeline import ProspectorPipeline
from prospector.models import CompanyInfo, ProspectorResult, LeadRecord, RoleCategory


SAMPLE_BING_HTML = """
<!DOCTYPE html>
<html>
<body>
<ol id="b_results">
  <li class="b_algo">
    <h2>
      <a href="https://www.bing.com/ck/a?!&&p=123&u=a1aHR0cHM6Ly93d3cubGlua2VkaW4uY29tL2luL3NhdHlhbmFkZWxsYQ==&ntb=1">
        Satya Nadella - Chairman and CEO - Microsoft | LinkedIn
      </a>
    </h2>
    <div class="b_caption">
      <p>Satya Nadella is Chairman and CEO of Microsoft Corporation. Leading cloud and AI.</p>
    </div>
  </li>
  <li class="b_algo">
    <h2>
      <a href="https://www.linkedin.com/in/amy-hood">
        Amy Hood - EVP and CFO - Microsoft | LinkedIn
      </a>
    </h2>
    <div class="b_caption">
      <p>Amy Hood serves as Executive Vice President and CFO.</p>
    </div>
  </li>
</ol>
</body>
</html>
"""


def test_bing_web_provider_parsing():
    """Verify Bing HTML parsing decodes tracking links and extracts titles/snippets."""
    provider = BingWebSearchProvider()
    results = provider.parse_html(SAMPLE_BING_HTML, max_results=5)
    assert len(results) == 2
    assert results[0]["title"] == "Satya Nadella - Chairman and CEO - Microsoft | LinkedIn"
    # Decoded from a1 base64 wrapper
    assert "https://www.linkedin.com/in/satyanadella" in results[0]["link"]
    assert "Satya Nadella is Chairman" in results[0]["snippet"]
    assert results[1]["link"] == "https://www.linkedin.com/in/amy-hood"


def test_bing_web_provider_clean_url_fallback():
    """Verify fallback for malformed or direct URLs."""
    assert BingWebSearchProvider._clean_bing_url("https://example.com/direct") == "https://example.com/direct"
    # Malformed base64
    assert "bing.com/ck/a" in BingWebSearchProvider._clean_bing_url("https://www.bing.com/ck/a?u=a1INVALID!!!")


def test_search_engine_uses_fast_bing_first():
    """Verify SearchEngine queries fast Bing provider first and avoids ddgs client if Bing succeeds."""
    engine = SearchEngine()
    engine.bing_provider = MagicMock()
    engine.bing_provider.query.return_value = [
        {
            "title": "Satya Nadella - CEO - Microsoft",
            "link": "https://linkedin.com/in/satyanadella",
            "snippet": "CEO at Microsoft",
        }
    ]
    engine._ddgs_client = MagicMock()

    results = engine.query("site:linkedin.com/in Microsoft CEO", max_results=5)
    assert len(results) == 1
    assert results[0]["title"] == "Satya Nadella - CEO - Microsoft"
    assert engine.bing_provider.query.called
    # Did not invoke slow DDGS text search because Bing returned results
    assert not engine._ddgs_client.text.called


def test_pipeline_run_batch_concurrent():
    """Verify ProspectorPipeline.run_batch executes companies concurrently with max_workers."""
    mock_search = MagicMock()
    mock_search.query.return_value = []

    pipeline = ProspectorPipeline(search_engine=mock_search, check_smtp=False)

    def mock_run_single(company_input, **kwargs):
        return ProspectorResult(
            company=CompanyInfo(raw_input=company_input, clean_name=company_input.split(".")[0].title(), domain=company_input),
            leads=[],
            c_suite_count=0,
            hr_count=0,
            total_leads=0,
            execution_time_sec=0.1,
        )

    with patch.object(pipeline, "run", side_effect=mock_run_single) as mock_single:
        results = pipeline.run_batch(["microsoft.com", "apple.com", "google.com"], max_workers=3)
        assert len(results) == 3
        assert mock_single.call_count == 3
        domains = [r.company.domain for r in results]
        assert "microsoft.com" in domains
        assert "apple.com" in domains
        assert "google.com" in domains


def test_pipeline_run_batch_error_isolation():
    """Verify run_batch handles an exception in one domain without failing the entire batch."""
    pipeline = ProspectorPipeline(check_smtp=False)

    def flaky_run(company_input, **kwargs):
        if company_input == "failing.com":
            raise ConnectionResetError("Remote server closed socket")
        return ProspectorResult(
            company=CompanyInfo(raw_input=company_input, clean_name="Success", domain=company_input),
            leads=[],
            c_suite_count=0,
            hr_count=0,
            total_leads=0,
            execution_time_sec=0.1,
        )

    with patch.object(pipeline, "run", side_effect=flaky_run):
        results = pipeline.run_batch(["good1.com", "failing.com", "good2.com"], max_workers=2)
        assert len(results) == 2
        domains = [r.company.domain for r in results]
        assert "good1.com" in domains
        assert "good2.com" in domains
        assert "failing.com" not in domains
