"""Tests for CLI Markdown Summary generation (e.g. for GitHub Actions Step Summary)."""

import os
from prospector.models import (
    CompanyInfo,
    MXInfo,
    ProspectorResult,
    LeadRecord,
    RoleCategory,
)
from prospector.cli import generate_markdown_summary


def test_generate_markdown_summary_with_leads():
    company = CompanyInfo(raw_input="acme.com", clean_name="Acme Corp", domain="acme.com")
    mx = MXInfo(domain="acme.com", has_mx=True, provider="Google Workspace", is_catch_all=False)
    leads = [
        LeadRecord(
            full_name="Jane Doe",
            first_name="Jane",
            last_name="Doe",
            role_category=RoleCategory.C_SUITE,
            job_title="CEO",
            company_name="Acme Corp",
            domain="acme.com",
            location="San Francisco, USA",
            best_email="jane@acme.com",
            email_confidence=0.85,
            linkedin_url="https://linkedin.com/in/janedoe",
        ),
        LeadRecord(
            full_name="John Smith",
            first_name="John",
            last_name="Smith",
            role_category=RoleCategory.HR_TALENT,
            job_title="Head of Talent",
            company_name="Acme Corp",
            domain="acme.com",
            location="Remote",
            best_email="john@acme.com",
            email_confidence=0.65,
            linkedin_url="https://linkedin.com/in/johnsmith",
        ),
    ]
    result = ProspectorResult(
        company=company,
        mx_info=mx,
        leads=leads,
        total_leads=2,
        c_suite_count=1,
        hr_count=1,
        execution_time_sec=2.5,
    )

    md = generate_markdown_summary(result)

    assert "### 🎯 Prospector-AI Lead Discovery Summary" in md
    assert "Acme Corp" in md
    assert "`acme.com`" in md
    assert "`Google Workspace`" in md
    assert "| Category | Full Name | Job Title | Location | Best Email | Confidence | LinkedIn |" in md
    assert "🔴 **C-Suite**" in md
    assert "**Jane Doe**" in md
    assert "`jane@acme.com`" in md
    assert "85%" in md
    assert "[Profile](https://linkedin.com/in/janedoe)" in md
    assert "🔵 **HR/Talent**" in md
    assert "**John Smith**" in md


def test_generate_markdown_summary_empty():
    company = CompanyInfo(raw_input="ghost.com", clean_name="Ghost Inc", domain="ghost.com")
    result = ProspectorResult(
        company=company,
        leads=[],
        total_leads=0,
        c_suite_count=0,
        hr_count=0,
        execution_time_sec=1.1,
    )

    md = generate_markdown_summary(result)
    assert "Ghost Inc" in md
    assert "No leads matching the specified criteria were discovered." in md


def test_cli_summary_file_arg(tmp_path, monkeypatch):
    from unittest.mock import patch
    from prospector.cli import main

    summary_file = tmp_path / "step_summary.md"
    company = CompanyInfo(raw_input="test.com", clean_name="Test Co", domain="test.com")
    fake_result = ProspectorResult(
        company=company,
        leads=[],
        total_leads=0,
        c_suite_count=0,
        hr_count=0,
        execution_time_sec=0.5,
    )

    with patch("prospector.cli.ProspectorPipeline.run", return_value=fake_result):
        monkeypatch.setattr(
            "sys.argv",
            ["cli.py", "test.com", "--format", "table", "--summary-file", str(summary_file)],
        )
        main()

    assert summary_file.exists()
    content = summary_file.read_text(encoding="utf-8")
    assert "Test Co" in content
    assert "### 🎯 Prospector-AI Lead Discovery Summary" in content
