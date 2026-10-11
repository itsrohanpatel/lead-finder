"""Tests for ProspectorPipeline."""

from unittest.mock import MagicMock, patch
from prospector.models import RoleCategory, MXInfo
from prospector.pipeline import ProspectorPipeline


def test_pipeline_execution_with_mocks():
    mock_search = MagicMock()
    mock_search.query.return_value = [
        {
            "link": "https://www.linkedin.com/in/satyanadella",
            "title": "Satya Nadella - Chairman and CEO - Microsoft | LinkedIn",
        },
        {
            "link": "https://www.linkedin.com/in/sarah-connor",
            "title": "Sarah Connor - Head of Talent Acquisition - Microsoft | LinkedIn",
        },
    ]

    mock_mx = MXInfo(
        domain="microsoft.com",
        has_mx=True,
        mx_records=["ms.mail.com"],
        provider="Microsoft 365",
        is_catch_all=False,
    )

    with patch("prospector.pipeline.EmailVerifier.lookup_mx_records", return_value=mock_mx):
        with patch("prospector.pipeline.EmailVerifier.verify_lead_permutations") as mock_verify:
            mock_verify.return_value = ([], "satya.nadella@microsoft.com", 0.95)

            pipeline = ProspectorPipeline(search_engine=mock_search, check_smtp=False)
            res = pipeline.run("microsoft.com", target_roles=[RoleCategory.C_SUITE, RoleCategory.HR_TALENT])

            assert res.company.domain == "microsoft.com"
            assert res.company.clean_name == "Microsoft"
            assert res.total_leads == 2
            assert res.c_suite_count == 1
            assert res.hr_count == 1
            assert res.leads[0].best_email == "satya.nadella@microsoft.com"
            assert res.leads[0].email_confidence == 0.95


def test_pipeline_dork_roles_queried():
    mock_search = MagicMock()
    mock_search.query.return_value = []

    mock_mx = MXInfo(
        domain="example.com",
        has_mx=True,
        mx_records=["mail.example.com"],
        provider="Google Workspace",
        is_catch_all=False,
    )

    with patch("prospector.pipeline.EmailVerifier.lookup_mx_records", return_value=mock_mx):
        pipeline = ProspectorPipeline(search_engine=mock_search, check_smtp=False)
        pipeline.run("example.com", target_roles=[RoleCategory.HR_TALENT, RoleCategory.C_SUITE])

        queried_dorks = [call[0][0] for call in mock_search.query.call_args_list]
        # Verify C-Suite keywords
        assert any("CEO" in d for d in queried_dorks)
        assert any("Founder" in d for d in queried_dorks)
        assert any("Director" in d for d in queried_dorks)
        # Verify HR/Talent keywords including People and Hiring
        assert any("HR" in d for d in queried_dorks)
        assert any("Talent" in d for d in queried_dorks)
        assert any("People" in d for d in queried_dorks)
        assert any("Hiring" in d for d in queried_dorks)


def test_pipeline_location_query_and_filtering():
    mock_search = MagicMock()
    mock_search.query.return_value = [
        {
            "link": "https://au.linkedin.com/in/global-founder",
            "title": "Alex Smith - Founder at Acme Corp | LinkedIn",
            "snippet": "Founder · Location: Sydney, Australia",
        },
        {
            "link": "https://in.linkedin.com/in/india-hr",
            "title": "Priya Sharma - HR Manager at Acme Corp | LinkedIn",
            "snippet": "HR Professional · Location: Mumbai, Maharashtra, India",
        },
        {
            "link": "https://au.linkedin.com/in/australia-hr",
            "title": "Sarah Connor - Head of People at Acme Corp | LinkedIn",
            "snippet": "HR Leader · Location: Sydney, Australia",
        },
    ]

    mock_mx = MXInfo(
        domain="acmecorp.com",
        has_mx=True,
        mx_records=["mail.acmecorp.com"],
        provider="Google Workspace",
        is_catch_all=False,
    )

    with patch("prospector.pipeline.EmailVerifier.lookup_mx_records", return_value=mock_mx):
        with patch("prospector.pipeline.EmailVerifier.verify_lead_permutations", return_value=([], "test@acmecorp.com", 0.9)):
            pipeline = ProspectorPipeline(search_engine=mock_search, check_smtp=False)
            res = pipeline.run("acmecorp.com", location="Pan India")

            # Check that HR dork included India
            queried_dorks = [call[0][0] for call in mock_search.query.call_args_list]
            assert any("HR India" in d or "Hiring India" in d for d in queried_dorks)

            # Check lead filtering:
            # Founder in Sydney is kept
            # HR in Mumbai is kept
            # HR in Sydney is filtered out
            lead_names = [l.full_name for l in res.leads]
            assert "Alex Smith" in lead_names
            assert "Priya Sharma" in lead_names
            assert "Sarah Connor" not in lead_names

            # Check location is populated
            for l in res.leads:
                if l.full_name == "Priya Sharma":
                    assert "India" in l.location
