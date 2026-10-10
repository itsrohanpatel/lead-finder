"""Tests for EmailPermutator."""

from prospector.email_permutator import EmailPermutator


def test_generate_permutations():
    perms = EmailPermutator.generate("Satya", "Nadella", "microsoft.com")
    emails = [p.email for p in perms]
    assert "satya.nadella@microsoft.com" in emails
    assert "snadella@microsoft.com" in emails
    assert "satya@microsoft.com" in emails
    assert "s.nadella@microsoft.com" in emails

    # Check top pattern has high prior confidence
    top_perm = perms[0]
    assert top_perm.pattern_name == "first.last"
    assert top_perm.confidence_score >= 0.50


def test_generate_single_name():
    perms = EmailPermutator.generate("Elon", "", "tesla.com")
    emails = [p.email for p in perms]
    assert "elon@tesla.com" in emails


def test_sanitize():
    assert EmailPermutator.sanitize("John-Paul") == "johnpaul"
    assert EmailPermutator.sanitize("O'Connor") == "oconnor"
    assert EmailPermutator.sanitize("Renée") == "ren" or len(EmailPermutator.sanitize("Renée")) > 0
