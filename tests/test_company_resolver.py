"""Tests for CompanyResolver."""

import pytest
from prospector.company_resolver import CompanyResolver


def test_resolve_from_domain():
    info = CompanyResolver.resolve("stripe.com")
    assert info.domain == "stripe.com"
    assert info.clean_name == "Stripe"


def test_resolve_from_url():
    info = CompanyResolver.resolve("https://www.openai.com/about/")
    assert info.domain == "openai.com"
    assert info.clean_name.lower() == "openai"


def test_resolve_from_linkedin_company():
    info = CompanyResolver.resolve("https://www.linkedin.com/company/apple/")
    assert info.clean_name == "Apple"
    assert info.linkedin_company_url == "https://www.linkedin.com/company/apple/"


def test_resolve_from_name_with_legal_suffixes():
    info = CompanyResolver.resolve("Acme Corporation, Inc.")
    assert info.clean_name == "Acme"
    assert info.domain is None


def test_resolve_empty_raises_error():
    with pytest.raises(ValueError):
        CompanyResolver.resolve("   ")
