import pytest
from prospector.company_resolver import CompanyResolver, GENERIC_TERMS
from prospector.lead_extractor import LeadExtractor
from prospector.models import RoleCategory


def test_reject_partner_badges_in_company_resolver():
    """Ensure vendor and agency partner badges are rejected as generic terms."""
    badges = [
        "Google Partner",
        "Premier Google Partner",
        "Meta Business Partner",
        "AWS Advanced Partner",
        "Certified Partner",
        "Platinum Partner",
    ]
    for badge in badges:
        assert any(term in badge.lower() for term in GENERIC_TERMS), f"Badge '{badge}' should be in GENERIC_TERMS"


def test_strict_multi_token_brand_anchoring():
    """Ensure single common names like 'Jain' do not match 'Jain Infotech' without secondary token or SLD."""
    # Target is 'Jain Infotech', candidate employer is 'Accelsoft' or just 'Jain'
    assert not LeadExtractor.employer_matches_company("Accelsoft", "Jain Infotech", "jaininfotech.in")
    assert not LeadExtractor.employer_matches_company("Google", "Jain Infotech", "jaininfotech.in")
    
    # Valid matches should still pass
    assert LeadExtractor.employer_matches_company("Jain Infotech", "Jain Infotech", "jaininfotech.in")
    assert LeadExtractor.employer_matches_company("Jain InfoTech Services", "Jain Infotech", "jaininfotech.in")
    assert LeadExtractor.employer_matches_company("JainInfotech", "Jain Infotech", "jaininfotech.in")


def test_headline_excludes_candidate_self_name_for_brand_token():
    """Ensure a candidate whose surname is 'Jain' working at 'Accelsoft' is NOT falsely matched to 'Jain Infotech'."""
    raw_item = {
        "title": "Anil Jain - Founder at Accelsoft | LinkedIn",
        "link": "https://in.linkedin.com/in/anil-jain-accelsoft",
        "snippet": "Founder at Accelsoft Technologies · Experience: Accelsoft · Location: India",
    }
    leads = LeadExtractor.extract_leads(
        search_results=[raw_item],
        company_name="Jain Infotech",
        domain="jaininfotech.in",
        target_roles=[RoleCategory.C_SUITE]
    )
    assert len(leads) == 0, f"Expected 0 leads for Accelsoft employee, got {len(leads)}"


def test_genuine_employee_with_brand_in_title_passes():
    """Ensure genuine employee with brand in headline passes cleanly."""
    raw_item = {
        "title": "Pankaj Jain - Founder at Jain InfoTech | LinkedIn",
        "link": "https://in.linkedin.com/in/viswapankaj",
        "snippet": "Founder at Jain InfoTech · Location: Bengaluru, India",
    }
    leads = LeadExtractor.extract_leads(
        search_results=[raw_item],
        company_name="Jain Infotech",
        domain="jaininfotech.in",
        target_roles=[RoleCategory.C_SUITE]
    )
    assert len(leads) == 1
    assert leads[0].full_name == "Pankaj Jain"


def test_genuine_employees_with_same_surname_as_brand_pass():
    """Ensure candidate with same surname as brand passes when employer is verified, even if company name is unspaced."""
    raw = [
        {
            "title": "Pankaj Jain - Founder, Jain InfoTech | LinkedIn",
            "link": "https://in.linkedin.com/in/viswapankaj",
            "snippet": "Founder, Jain InfoTech · Location: Bengaluru, India"
        },
        {
            "title": "Roshan Jain - Director - Jain Infotech | LinkedIn",
            "link": "https://in.linkedin.com/in/roshanjain",
            "snippet": "Director at Jain Infotech · Location: Mumbai, India"
        },
        {
            "title": "Avinash Jain - Senior Software Engineer - Microsoft | LinkedIn",
            "link": "https://in.linkedin.com/in/avinashjain",
            "snippet": "Software Engineer at Microsoft, Bengaluru"
        }
    ]
    leads = LeadExtractor.extract_leads(
        search_results=raw,
        company_name="Jaininfotech",
        domain="jaininfotech.in",
        target_roles=[RoleCategory.C_SUITE, RoleCategory.OTHER]
    )
    assert len(leads) == 2
    names = [l.full_name for l in leads]
    assert "Pankaj Jain" in names
    assert "Roshan Jain" in names
    assert "Avinash Jain" not in names

