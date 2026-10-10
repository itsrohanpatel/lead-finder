"""Tests for EmailVerifier with mocked DNS and SMTP."""

from unittest.mock import patch, MagicMock
from prospector.models import EmailPermutation, MXInfo
from prospector.email_verifier import EmailVerifier


def test_fingerprint_provider():
    assert EmailVerifier.fingerprint_provider(["aspmx.l.google.com"]) == "Google Workspace"
    assert EmailVerifier.fingerprint_provider(["stripe-com.mail.protection.outlook.com"]) == "Microsoft 365"
    assert EmailVerifier.fingerprint_provider(["smtp.zoho.com"]) == "Zoho Mail"
    assert EmailVerifier.fingerprint_provider(["mail.acme-corp.net"]) == "Custom/Enterprise"


@patch("dns.resolver.resolve")
def test_lookup_mx_records_success(mock_resolve):
    mock_item = MagicMock()
    mock_item.preference = 10
    mock_item.exchange = "aspmx.l.google.com."
    mock_resolve.return_value = [mock_item]

    mx_info = EmailVerifier.lookup_mx_records("example.com")
    assert mx_info.has_mx is True
    assert "aspmx.l.google.com" in mx_info.mx_records
    assert mx_info.provider == "Google Workspace"


@patch("dns.resolver.resolve", side_effect=Exception("No MX"))
def test_lookup_mx_records_failure(mock_resolve):
    mx_info = EmailVerifier.lookup_mx_records("invalid-nonexistent-domain-123.xyz")
    assert mx_info.has_mx is False
    assert mx_info.provider == "None/Failed"


def test_verify_permutation_without_mx():
    mx_info = MXInfo(domain="bad.xyz", has_mx=False, mx_records=[])
    perm = EmailPermutation(email="test@bad.xyz", pattern_name="first", confidence_score=0.5)

    v_perm = EmailVerifier.verify_permutation(perm, mx_info, check_smtp=False)
    assert v_perm.confidence_score == 0.0
    assert v_perm.verification_status == "undeliverable"


@patch.object(EmailVerifier, "smtp_probe_rcpt", return_value=(250, "OK"))
def test_verify_permutation_valid_smtp(mock_probe):
    mx_info = MXInfo(domain="good.com", has_mx=True, mx_records=["mx.good.com"])
    perm = EmailPermutation(email="alex@good.com", pattern_name="first", confidence_score=0.5)

    v_perm = EmailVerifier.verify_permutation(perm, mx_info, is_catch_all=False, check_smtp=True)
    assert v_perm.verification_status == "valid"
    assert v_perm.confidence_score >= 0.90
    assert v_perm.smtp_verified is True


@patch.object(EmailVerifier, "smtp_probe_rcpt", return_value=(250, "OK"))
def test_verify_permutation_catch_all_smtp(mock_probe):
    mx_info = MXInfo(domain="catchall.com", has_mx=True, mx_records=["mx.catchall.com"])
    perm = EmailPermutation(email="alex@catchall.com", pattern_name="first", confidence_score=0.5)

    v_perm = EmailVerifier.verify_permutation(perm, mx_info, is_catch_all=True, check_smtp=True)
    assert v_perm.verification_status == "catch_all"
    assert v_perm.is_catch_all is True
    # Should not overstate confidence on catch-all
    assert v_perm.confidence_score <= 0.65
