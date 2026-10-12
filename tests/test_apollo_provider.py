"""Unit tests for ApolloProvider (the reverse-engineered alternative to Apify's company-employees-scraper)."""

import pytest
from unittest.mock import patch, MagicMock
from prospector.apollo_provider import ApolloProvider


def test_clean_domain():
    assert ApolloProvider.clean_domain("https://www.sarvam.ai/about") == "sarvam.ai"
    assert ApolloProvider.clean_domain("http://carmelrealtycompany.com/") == "carmelrealtycompany.com"
    assert ApolloProvider.clean_domain("google.com") == "google.com"
    assert ApolloProvider.clean_domain("  WWW.EXAMPLE.CO.UK/path?query=1  ") == "example.co.uk"


def test_search_employees_no_key():
    provider = ApolloProvider(api_key="")
    results = provider.search_employees("sarvam.ai")
    assert results == []


@patch("prospector.apollo_provider.requests.post")
def test_search_employees_success(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "people": [
            {
                "id": "123",
                "first_name": "John",
                "last_name": "Doe",
                "name": "John Doe",
                "title": "Chief Executive Officer",
                "linkedin_url": "https://www.linkedin.com/in/johndoe",
                "city": "Bengaluru",
                "country": "India",
                "organization": {"name": "Sarvam AI"}
            },
            {
                "id": "456",
                "first_name": "Jane",
                "last_name": "Smith",
                "name": "Jane Smith",
                "title": "Head of People",
                "linkedin_url": "https://www.linkedin.com/in/janesmith",
                "city": "Mumbai",
                "country": "India",
                "organization": {"name": "Sarvam AI"}
            }
        ]
    }
    mock_post.return_value = mock_response

    provider = ApolloProvider(api_key="test_key_123")
    results = provider.search_employees(
        website="https://sarvam.ai",
        departments=["c_suite", "human_resources"],
        seniority=["founder", "head"],
        max_records=10
    )

    assert len(results) == 2
    assert results[0]["name"] == "John Doe"
    assert results[0]["title"] == "Chief Executive Officer"
    assert results[0]["location"] == "Bengaluru, India"
    assert results[1]["name"] == "Jane Smith"
    assert results[1]["title"] == "Head of People"
    assert results[1]["linkedin_url"] == "https://www.linkedin.com/in/janesmith"

    # Verify request payload
    mock_post.assert_called_once()
    called_args, called_kwargs = mock_post.call_args
    payload = called_kwargs["json"]
    assert payload["q_organization_domains_list"] == ["sarvam.ai"]
    assert "human_resources" in payload["person_departments"]
    assert "head" in payload["person_seniorities"]
    assert called_kwargs["headers"]["X-Api-Key"] == "test_key_123"
