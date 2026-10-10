"""Tests for LeadExtractor."""

from prospector.models import RoleCategory
from prospector.lead_extractor import LeadExtractor


def test_is_individual_linkedin_profile():
    assert LeadExtractor.is_individual_linkedin_profile("https://www.linkedin.com/in/satyanadella") is True
    assert LeadExtractor.is_individual_linkedin_profile("https://linkedin.com/in/jane-doe-1234?trk=feed") is True
    assert LeadExtractor.is_individual_linkedin_profile("https://linkedin.com/company/microsoft") is False
    assert LeadExtractor.is_individual_linkedin_profile("https://linkedin.com/jobs/view/1234") is False
    assert LeadExtractor.is_individual_linkedin_profile("https://linkedin.com/pub/dir/John/Doe") is False


def test_parse_name_and_title():
    name, title = LeadExtractor.parse_name_and_title("Satya Nadella - Chairman and CEO - Microsoft | LinkedIn")
    assert name == "Satya Nadella"
    assert "CEO" in title

    name, title = LeadExtractor.parse_name_and_title("Jane Doe | Head of Talent Acquisition at Stripe")
    assert name == "Jane Doe"
    assert title == "Head of Talent Acquisition"


def test_categorize_role():
    assert LeadExtractor.categorize_role("Chief Executive Officer") == RoleCategory.C_SUITE
    assert LeadExtractor.categorize_role("Co-Founder & CTO") == RoleCategory.C_SUITE
    assert LeadExtractor.categorize_role("VP of Engineering") == RoleCategory.C_SUITE
    assert LeadExtractor.categorize_role("Head of Talent Acquisition") == RoleCategory.HR_TALENT
    assert LeadExtractor.categorize_role("Senior Technical Recruiter") == RoleCategory.HR_TALENT
    assert LeadExtractor.categorize_role("Software Engineer") == RoleCategory.OTHER


def test_extract_leads_deduplication():
    search_results = [
        {
            "link": "https://www.linkedin.com/in/satyanadella",
            "title": "Satya Nadella - Chairman and CEO - Microsoft | LinkedIn",
        },
        {
            "link": "https://www.linkedin.com/in/satyanadella?trk=1",
            "title": "Satya Nadella - Chairman and CEO - Microsoft | LinkedIn",
        },
        {
            "link": "https://www.linkedin.com/in/sarah-connor",
            "title": "Sarah Connor - Head of People - Microsoft | LinkedIn",
        },
    ]

    leads = LeadExtractor.extract_leads(search_results, company_name="Microsoft", domain="microsoft.com")
    assert len(leads) == 2
    assert leads[0].full_name == "Satya Nadella"
    assert leads[0].role_category == RoleCategory.C_SUITE
    assert leads[1].full_name == "Sarah Connor"
    assert leads[1].role_category == RoleCategory.HR_TALENT


def test_company_affiliation_filters_unrelated_companies():
    search_results = [
        {
            "link": "https://www.linkedin.com/in/terminator",
            "title": "T-800 - Head of Operations - Cyberdyne Systems | LinkedIn",
        }
    ]
    leads = LeadExtractor.extract_leads(search_results, company_name="Microsoft", domain="microsoft.com")
    assert len(leads) == 0
