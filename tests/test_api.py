"""Tests for FastAPI endpoints."""

from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from prospector.api import app
from prospector.models import CompanyInfo, ProspectorResult, LeadRecord, RoleCategory

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "Prospector-AI"


@patch("prospector.api.ProspectorPipeline.run")
def test_prospect_post_endpoint(mock_run):
    mock_result = ProspectorResult(
        company=CompanyInfo(raw_input="test.com", clean_name="Test", domain="test.com"),
        leads=[
            LeadRecord(
                full_name="Alice CEO",
                first_name="Alice",
                last_name="CEO",
                job_title="CEO",
                role_category=RoleCategory.C_SUITE,
                linkedin_url="https://linkedin.com/in/alice",
                company_name="Test",
                best_email="alice@test.com",
                email_confidence=0.9,
            )
        ],
        c_suite_count=1,
        hr_count=0,
        total_leads=1,
        execution_time_sec=0.5,
    )
    mock_run.return_value = mock_result

    payload = {"company": "test.com", "roles": ["c_suite"], "check_smtp": False}
    response = client.post("/api/prospect", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["company"]["clean_name"] == "Test"
    assert len(data["leads"]) == 1
    assert data["leads"][0]["best_email"] == "alice@test.com"
