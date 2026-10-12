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


def test_resolve_departments():
    deps = ApolloProvider.resolve_departments(["hr", "recruiting", "talent", "tech", "sales", "csuite", "unknown_dept"])
    assert "human_resources" in deps
    assert "engineering_technical" in deps
    assert "sales" in deps
    assert "c_suite" in deps
    assert len(deps) == 4


def test_resolve_seniorities():
    sens = ApolloProvider.resolve_seniorities(["founder", "cofounder", "exec", "lead", "mgr", "senior"])
    assert "founder" in sens
    assert "c_suite" in sens
    assert "head" in sens
    assert "manager" in sens
    assert "senior" in sens


def test_match_obfuscated_last_name():
    # Exact pattern matches
    assert ApolloProvider.match_obfuscated_last_name("Verma", "Ve***a") is True
    assert ApolloProvider.match_obfuscated_last_name("Gupta", "Gu***a") is True
    assert ApolloProvider.match_obfuscated_last_name("Kumar", "Ku***r") is True
    assert ApolloProvider.match_obfuscated_last_name("Raghavan", "Ra***n") is True
    assert ApolloProvider.match_obfuscated_last_name("Shah", "S***h") is True
    assert ApolloProvider.match_obfuscated_last_name("Balaraman", "Ba***n") is True

    # Case insensitivity
    assert ApolloProvider.match_obfuscated_last_name("verma", "Ve***a") is True
    assert ApolloProvider.match_obfuscated_last_name("VERMA", "ve***a") is True

    # Mismatches
    assert ApolloProvider.match_obfuscated_last_name("Sharma", "Ve***a") is False
    assert ApolloProvider.match_obfuscated_last_name("Gupta", "Ku***r") is False
    assert ApolloProvider.match_obfuscated_last_name("Patel", "Ra***n") is False
    assert ApolloProvider.match_obfuscated_last_name("", "Ve***a") is False
    assert ApolloProvider.match_obfuscated_last_name("Verma", "") is False


def test_extract_name_from_linkedin_title():
    # Matches
    res1 = ApolloProvider.extract_name_from_linkedin_title(
        "Sshubam Verma - ML Engineer @ Sarvam | LinkedIn", "Sshubam", "Ve***a"
    )
    assert res1 == ("Sshubam Verma", "Verma")

    res2 = ApolloProvider.extract_name_from_linkedin_title(
        "Aarthi Balaraman - Hiring @ Sarvam; Ex-Abnormal AI, Google ...", "Aarthi", "Ba***n"
    )
    assert res2 == ("Aarthi Balaraman", "Balaraman")

    res3 = ApolloProvider.extract_name_from_linkedin_title(
        "Vivek Raghavan - Sarvam AI | LinkedIn", "Vivek", "Ra***n"
    )
    assert res3 == ("Vivek Raghavan", "Raghavan")

    # Rejection of mismatched last name
    res4 = ApolloProvider.extract_name_from_linkedin_title(
        "Vivek Raghavan - Sarvam AI | LinkedIn", "Vivek", "Gu***a"
    )
    assert res4 is None


def test_unmask_candidate_via_title():
    provider = ApolloProvider(api_key="test_key")
    mock_search_engine = MagicMock()
    mock_search_engine.search_duckduckgo.return_value = [
        {
            "title": "Sshubam Verma - ML Engineer @ Sarvam | LinkedIn",
            "link": "https://in.linkedin.com/in/sshubamverma",
        }
    ]

    candidate = {
        "first_name": "Sshubam",
        "last_name": "Ve***a",
        "last_name_obfuscated": "Ve***a",
        "is_obfuscated": True,
        "name": "Sshubam Ve***a",
        "title": "ML Engineer",
    }

    unmasked = provider.unmask_candidate(candidate, mock_search_engine, "Sarvam AI")
    assert unmasked["name"] == "Sshubam Verma"
    assert unmasked["last_name"] == "Verma"
    assert unmasked["is_obfuscated"] is False
    assert unmasked["linkedin_url"] == "https://in.linkedin.com/in/sshubamverma"


def test_unmask_candidate_via_slug():
    provider = ApolloProvider(api_key="test_key")
    mock_search_engine = MagicMock()
    mock_search_engine.search_duckduckgo.return_value = [
        {
            "title": "Sshubam - ML Engineer",
            "link": "https://in.linkedin.com/in/sshubamverma",
        }
    ]

    candidate = {
        "first_name": "Sshubam",
        "last_name": "Ve***a",
        "last_name_obfuscated": "Ve***a",
        "is_obfuscated": True,
        "name": "Sshubam Ve***a",
        "title": "ML Engineer",
    }

    unmasked = provider.unmask_candidate(candidate, mock_search_engine, "Sarvam AI")
    assert unmasked["name"] == "Sshubam Verma"
    assert unmasked["last_name"] == "Verma"
    assert unmasked["is_obfuscated"] is False
    assert unmasked["linkedin_url"] == "https://in.linkedin.com/in/sshubamverma"


def test_unmask_already_complete():
    provider = ApolloProvider(api_key="test_key")
    mock_search_engine = MagicMock()

    candidate = {
        "first_name": "Pratyush",
        "last_name": "Kumar",
        "is_obfuscated": False,
        "name": "Pratyush Kumar",
        "title": "Co-Founder",
    }

    unmasked = provider.unmask_candidate(candidate, mock_search_engine, "Sarvam AI")
    assert unmasked["name"] == "Pratyush Kumar"
    mock_search_engine.search_duckduckgo.assert_not_called()

