"""Integration tests for ProspectorPipeline Apollo integration, unmasking, and custom department features."""

import pytest
from unittest.mock import patch, MagicMock
from prospector.models import RoleCategory, CompanyInfo, MXInfo
from prospector.pipeline import ProspectorPipeline
from prospector.apollo_provider import ApolloProvider


def test_pipeline_apollo_integration_success():
    """Verify that when Apollo returns candidates, pipeline unmasks them and skips broad dorks."""
    mock_search = MagicMock()
    mock_apollo = MagicMock()

    # Apollo returns 2 candidates with obfuscated last names
    mock_apollo.search_employees.return_value = [
        {
            "name": "Pratyush Ku***r",
            "first_name": "Pratyush",
            "last_name": "Ku***r",
            "last_name_obfuscated": "Ku***r",
            "is_obfuscated": True,
            "title": "Co-Founder",
            "linkedin_url": "",
            "location": "Bengaluru, India",
        },
        {
            "name": "Aarthi Ba***n",
            "first_name": "Aarthi",
            "last_name": "Ba***n",
            "last_name_obfuscated": "Ba***n",
            "is_obfuscated": True,
            "title": "Lead Recruiter, R&D",
            "linkedin_url": "",
            "location": "Bengaluru, India",
        },
    ]

    # Unmask candidates mock
    mock_apollo.unmask_candidates.return_value = [
        {
            "name": "Pratyush Kumar",
            "first_name": "Pratyush",
            "last_name": "Kumar",
            "last_name_obfuscated": "Ku***r",
            "is_obfuscated": False,
            "title": "Co-Founder",
            "linkedin_url": "https://in.linkedin.com/in/pratyush-kumar",
            "location": "Bengaluru, India",
        },
        {
            "name": "Aarthi Balaraman",
            "first_name": "Aarthi",
            "last_name": "Balaraman",
            "last_name_obfuscated": "Ba***n",
            "is_obfuscated": False,
            "title": "Lead Recruiter, R&D",
            "linkedin_url": "https://in.linkedin.com/in/aarthibalaraman",
            "location": "Bengaluru, India",
        },
    ]
    mock_apollo.resolve_departments.return_value = ["c_suite", "human_resources"]
    mock_apollo.resolve_seniorities.return_value = ["founder", "head"]

    pipeline = ProspectorPipeline(
        search_engine=mock_search,
        apollo_provider=mock_apollo,
        check_smtp=False,
    )

    with patch("prospector.company_resolver.CompanyResolver.resolve") as mock_resolve:
        mock_resolve.return_value = CompanyInfo(
            clean_name="Sarvam AI",
            domain="sarvam.ai",
            raw_input="sarvam.ai",
        )
        with patch("prospector.email_verifier.EmailVerifier.lookup_mx_records") as mock_mx:
            mock_mx.return_value = MXInfo(
                domain="sarvam.ai",
                has_mx=True,
                mx_records=["aspmx.l.google.com"],
                provider="Google Workspace",
            )
            result = pipeline.run("sarvam.ai")

    assert result.total_leads == 2
    assert result.c_suite_count == 1
    assert result.hr_count == 1
    assert result.leads[0].full_name == "Pratyush Kumar"
    assert result.leads[1].full_name == "Aarthi Balaraman"

    # Apollo satisfied both C-Suite and HR, so search engine query dorks should have been skipped!
    mock_search.query.assert_not_called()


def test_pipeline_apollo_zero_records_fallback():
    """Verify that when Apollo returns 0 records (boutique SME gap), pipeline cascades to search engine dorks."""
    mock_search = MagicMock()
    mock_apollo = MagicMock()

    # Apollo returns empty list
    mock_apollo.search_employees.return_value = []
    mock_apollo.resolve_departments.return_value = []
    mock_apollo.resolve_seniorities.return_value = []

    # Search engine returns 1 C-Suite lead via dorks
    mock_search.query.return_value = [
        {
            "title": "Alexis Smith - Creative Director @ Eklex | LinkedIn",
            "link": "https://www.linkedin.com/in/alexissmith",
            "snippet": "Creative Director at Eklex Solutions.",
        }
    ]

    pipeline = ProspectorPipeline(
        search_engine=mock_search,
        apollo_provider=mock_apollo,
        check_smtp=False,
    )

    with patch("prospector.company_resolver.CompanyResolver.resolve") as mock_resolve:
        mock_resolve.return_value = CompanyInfo(
            clean_name="Eklex Solutions",
            domain="eklexic.com",
            raw_input="eklexic.com",
        )
        with patch("prospector.email_verifier.EmailVerifier.lookup_mx_records") as mock_mx:
            mock_mx.return_value = MXInfo(
                domain="eklexic.com",
                has_mx=True,
                mx_records=["mail.eklexic.com"],
                provider="Custom",
            )
            result = pipeline.run("eklexic.com")

    # Step 3 search engine dorks were called because Apollo returned 0 leads
    assert mock_search.query.called


def test_cli_apollo_argument_parsing():
    """Verify that CLI parser accepts --apollo-key, --departments, and --seniorities."""
    from prospector.cli import main
    import sys

    # Test argument parsing with mock sys.argv
    test_args = [
        "prospector",
        "sarvam.ai",
        "--apollo-key", "test_key_xyz",
        "--departments", "c_suite,hr,tech",
        "--seniorities", "founder,c_suite,lead",
    ]

    with patch.object(sys, "argv", test_args):
        with patch("prospector.pipeline.ProspectorPipeline.run") as mock_run:
            mock_run.return_value = MagicMock(
                leads=[],
                total_leads=0,
                c_suite_count=0,
                hr_count=0,
                execution_time_sec=1.0,
                company=MagicMock(clean_name="Sarvam AI", domain="sarvam.ai"),
                mx_info=None,
            )
            with patch("prospector.cli.render_results_table"):
                main()

            mock_run.assert_called_once()
            _, kwargs = mock_run.call_args
            assert kwargs["departments"] == ["c_suite", "hr", "tech"]
            assert kwargs["seniorities"] == ["founder", "c_suite", "lead"]


def test_pipeline_apollo_preserves_obfuscated_roster_candidates():
    """Verify that when unmasking fails, candidates with obfuscated last names are preserved and generate valid first-name emails."""
    mock_search = MagicMock()
    mock_apollo = MagicMock()

    mock_apollo.search_employees.return_value = [
        {
            "name": "Aarthi Ba***n",
            "first_name": "Aarthi",
            "last_name": "Ba***n",
            "last_name_obfuscated": "Ba***n",
            "is_obfuscated": True,
            "title": "Lead Recruiter, R&D",
            "linkedin_url": "",
            "location": "Bengaluru, India",
        },
    ]
    mock_apollo.unmask_candidates.return_value = [
        {
            "name": "Aarthi Ba***n",
            "first_name": "Aarthi",
            "last_name": "Ba***n",
            "last_name_obfuscated": "Ba***n",
            "is_obfuscated": True,
            "title": "Lead Recruiter, R&D",
            "linkedin_url": "",
            "location": "Bengaluru, India",
        },
    ]
    mock_apollo.resolve_departments.return_value = ["human_resources"]
    mock_apollo.resolve_seniorities.return_value = ["all"]

    pipeline = ProspectorPipeline(
        search_engine=mock_search,
        apollo_provider=mock_apollo,
        check_smtp=False,
    )

    with patch("prospector.company_resolver.CompanyResolver.resolve") as mock_resolve:
        mock_resolve.return_value = CompanyInfo(
            clean_name="Sarvam AI",
            domain="sarvam.ai",
            raw_input="sarvam.ai",
        )
        with patch("prospector.email_verifier.EmailVerifier.lookup_mx_records") as mock_mx:
            mock_mx.return_value = MXInfo(
                domain="sarvam.ai",
                has_mx=True,
                mx_records=["aspmx.l.google.com"],
                provider="Google Workspace",
            )
            result = pipeline.run("sarvam.ai", departments=["human_resources"])

    assert result.total_leads == 1
    assert result.leads[0].first_name == "Aarthi"
    assert result.leads[0].best_email == "aarthi@sarvam.ai"

