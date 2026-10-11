"""Tests for location-aware discovery and extended technical/product role extraction."""

import pytest
from prospector.models import RoleCategory
from prospector.company_resolver import CompanyResolver
from prospector.lead_extractor import LeadExtractor


def test_extract_location_hint():
    """Verify natural language query strings cleanly extract company and target location."""
    c, loc = CompanyResolver.extract_location_hint("alaan.com indian team")
    assert c == "alaan.com"
    assert loc == "India"

    c, loc = CompanyResolver.extract_location_hint("https://alaan.com/ indian team")
    assert c == "https://alaan.com"
    assert loc == "India"

    c, loc = CompanyResolver.extract_location_hint("stripe.com in bengaluru")
    assert c == "stripe.com"
    assert loc == "Bengaluru"

    c, loc = CompanyResolver.extract_location_hint("stripe.com bangalore team")
    assert c == "stripe.com"
    assert loc == "Bengaluru"

    c, loc = CompanyResolver.extract_location_hint("http://www.ashima.in/")
    assert c == "http://www.ashima.in/"
    assert loc is None

    c, loc = CompanyResolver.extract_location_hint("OpenAI london office")
    assert c == "OpenAI"
    assert loc == "London"


def test_categorize_tech_and_product_roles():
    """Verify Tech Lead and Product roles fall into OTHER since only C-Suite and HR are targeted."""
    assert LeadExtractor.categorize_role("Tech Lead") == RoleCategory.OTHER
    assert LeadExtractor.categorize_role("Engineering Manager") == RoleCategory.OTHER
    assert LeadExtractor.categorize_role("Staff Software Architect") == RoleCategory.OTHER
    assert LeadExtractor.categorize_role("Lead Backend Engineer") == RoleCategory.OTHER

    assert LeadExtractor.categorize_role("Product Manager") == RoleCategory.OTHER
    assert LeadExtractor.categorize_role("Head of Product") == RoleCategory.OTHER
    assert LeadExtractor.categorize_role("Lead Product Designer") == RoleCategory.OTHER
    assert LeadExtractor.categorize_role("Product Analytics Lead") == RoleCategory.OTHER


def test_matches_target_location_aliases():
    """Verify country and city aliases (e.g. Bangalore -> Bengaluru, Indian cities -> India)."""
    assert LeadExtractor.matches_target_location("Bengaluru, India", "India") is True
    assert LeadExtractor.matches_target_location("Bangalore Urban", "India") is True
    assert LeadExtractor.matches_target_location("Mumbai, Maharashtra", "India") is True
    assert LeadExtractor.matches_target_location("Bangalore", "Bengaluru") is True
    assert LeadExtractor.matches_target_location("Bengaluru", "Bangalore") is True
    assert LeadExtractor.matches_target_location("Gurgaon", "Gurugram") is True
    assert LeadExtractor.matches_target_location("Sydney, Australia", "India") is False
    assert LeadExtractor.matches_target_location("London, UK", "India") is False


def test_extract_leads_with_location_filtering():
    """Verify extract_leads filters non-csuite leads based on target location."""
    raw_results = [
        {
            "link": "https://in.linkedin.com/in/jay-kumar",
            "title": "Jay Kumar - HR Specialist @ Alaan | LinkedIn",
            "snippet": "Experience: Alaan · Location: Bengaluru, Karnataka, India",
        },
        {
            "link": "https://ae.linkedin.com/in/dubai-hr",
            "title": "Omar Farooq - HR Manager @ Alaan | LinkedIn",
            "snippet": "Experience: Alaan · Location: Dubai, UAE",
        },
        {
            "link": "https://in.linkedin.com/in/shristy-prasad",
            "title": "Shristy Prasad - People @ Alaan | LinkedIn",
            "snippet": "Experience: Alaan · Location: Bengaluru, India",
        },
        {
            "link": "https://ae.linkedin.com/in/parthi-duraisamy",
            "title": "Parthi Duraisamy - Founder & CEO @ Alaan | LinkedIn",
            "snippet": "Experience: Alaan · Location: Dubai, UAE",
        },
    ]

    # Target: India
    leads = LeadExtractor.extract_leads(
        search_results=raw_results,
        company_name="Alaan",
        domain="alaan.com",
        location="India",
    )

    names = [l.full_name for l in leads]
    # Parthi Duraisamy (Founder/CEO) is preserved as global founder
    assert "Parthi Duraisamy" in names
    # Jay Kumar (Bengaluru HR lead) is included
    assert "Jay Kumar" in names
    # Shristy Prasad (Bengaluru HR lead) is included
    assert "Shristy Prasad" in names
    # Omar Farooq (Dubai HR lead) is excluded when location="India"
    assert "Omar Farooq" not in names
