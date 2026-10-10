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
