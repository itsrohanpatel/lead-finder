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
    assert LeadExtractor.categorize_role("Cofounder") == RoleCategory.C_SUITE
    assert LeadExtractor.categorize_role("C.E.O.") == RoleCategory.C_SUITE
    assert LeadExtractor.categorize_role("Managing Director") == RoleCategory.C_SUITE
    assert LeadExtractor.categorize_role("Owner & Founder") == RoleCategory.C_SUITE
    assert LeadExtractor.categorize_role("VP of Engineering") == RoleCategory.C_SUITE
    assert LeadExtractor.categorize_role("Head of Talent Acquisition") == RoleCategory.HR_TALENT
    assert LeadExtractor.categorize_role("Senior Technical Recruiter") == RoleCategory.HR_TALENT
    assert LeadExtractor.categorize_role("CHRO & General Counsel") == RoleCategory.HR_TALENT
    assert LeadExtractor.categorize_role("Senior Partner - People and Culture") == RoleCategory.HR_TALENT
    assert LeadExtractor.categorize_role("Senior Payroll Administrator") == RoleCategory.HR_TALENT
    assert LeadExtractor.categorize_role("Head of Hiring") == RoleCategory.HR_TALENT
    assert LeadExtractor.categorize_role("Hiring & Recruitment Lead") == RoleCategory.HR_TALENT
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


def test_extract_location():
    loc = LeadExtractor.extract_location("Location: Ahmedabad · 500+ connections", "https://in.linkedin.com/in/john-doe")
    assert loc == "Ahmedabad, India"

    loc_uk = LeadExtractor.extract_location("Location: London", "https://uk.linkedin.com/in/jane-doe")
    assert loc_uk == "London, United Kingdom"

    loc_sub = LeadExtractor.extract_location("", "https://in.linkedin.com/in/raj-patel")
    assert loc_sub == "India"


def test_location_filtering_hr_vs_founder():
    search_results = [
        {
            "link": "https://au.linkedin.com/in/global-founder",
            "title": "Alex Smith - Founder at Acme Corp | LinkedIn",
            "snippet": "Founder · Location: Sydney, Australia",
        },
        {
            "link": "https://au.linkedin.com/in/australia-hr",
            "title": "Sarah Connor - Head of People at Acme Corp | LinkedIn",
            "snippet": "HR Leader · Location: Sydney, Australia",
        },
        {
            "link": "https://in.linkedin.com/in/india-hr",
            "title": "Priya Sharma - HR Manager at Acme Corp | LinkedIn",
            "snippet": "HR Professional · Location: Mumbai, Maharashtra, India",
        },
    ]

    # When location="Pan India" is provided:
    # 1. Foreign HR lead should be filtered out.
    # 2. Indian HR lead should be kept.
    # 3. Foreign Founder should still be kept because founders can be anywhere.
    leads = LeadExtractor.extract_leads(
        search_results,
        company_name="Acme Corp",
        domain="acmecorp.com",
        location="Pan India",
    )

    names = [l.full_name for l in leads]
    assert "Alex Smith" in names      # Founder: kept regardless of foreign location
    assert "Priya Sharma" in names    # HR: Indian location kept
    assert "Sarah Connor" not in names  # HR: Foreign location filtered out


def test_extract_headline_with_pipe_subrole():
    search_results = [
        {
            "link": "https://in.linkedin.com/in/shloka-gajendra-29a541264",
            "title": "Shloka Gajendra - HR and Admin Assistant | Human resources ...",
            "snippet": "Currently working in Spectro Cloud India pvt ltd for almost 1.10 years. Have 5 years+ of experience in overall HR & admin, accounting department.",
        }
    ]
    leads = LeadExtractor.extract_leads(
        search_results,
        company_name="Spectro Cloud",
        domain="spectrocloud.com",
    )
    assert len(leads) == 1
    assert leads[0].full_name == "Shloka Gajendra"
    assert leads[0].job_title == "HR and Admin Assistant"
    assert leads[0].role_category == RoleCategory.HR_TALENT


def test_extract_headline_ending_with_location_city():
    search_results = [
        {
            "link": "https://in.linkedin.com/in/debashree-ghosh-dutta-45276860",
            "title": "Debashree Ghosh Dutta - HR Manager(Group) - Kolkata | LinkedIn",
            "snippet": "HR Manager(Group) at Kisah Apparels Private Limited · Experience: Kisah Apparels Private Limited · Location: Kolkata",
        }
    ]
    leads = LeadExtractor.extract_leads(
        search_results,
        company_name="Kisah",
        domain="kisah.in",
    )
    assert len(leads) == 1
    assert leads[0].full_name == "Debashree Ghosh Dutta"
    assert leads[0].job_title == "HR Manager(Group)"
    assert leads[0].role_category == RoleCategory.HR_TALENT
    assert "Kolkata" in leads[0].location

