"""Multi-signal email deliverability and mailbox verifier."""

import smtplib
import socket
import logging
from typing import List, Optional, Tuple
import dns.resolver
from prospector.models import EmailPermutation, MXInfo

logger = logging.getLogger(__name__)


class EmailVerifier:
    """Verifies email deliverability using MX records, catch-all detection, and SMTP handshakes."""

    @classmethod
    def lookup_mx_records(cls, domain: str) -> MXInfo:
        """Query DNS for domain MX records and fingerprint mail provider."""
        clean_domain = domain.strip().lower()
        try:
            answers = dns.resolver.resolve(clean_domain, "MX", lifetime=4.0)
            # Sort by priority
            sorted_records = sorted(answers, key=lambda r: r.preference)
            mx_hosts = [str(r.exchange).rstrip(".") for r in sorted_records]
            provider = cls.fingerprint_provider(mx_hosts)
            return MXInfo(
                domain=clean_domain,
                has_mx=len(mx_hosts) > 0,
                mx_records=mx_hosts,
                provider=provider,
            )
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.LifetimeTimeout, Exception) as exc:
            logger.debug(f"DNS MX lookup failed for {clean_domain}: {exc}")
            return MXInfo(
                domain=clean_domain,
                has_mx=False,
                mx_records=[],
                provider="None/Failed",
            )

    @classmethod
    def fingerprint_provider(cls, mx_hosts: List[str]) -> str:
        """Identify email provider from MX hostname signatures."""
        joined = " ".join(mx_hosts).lower()
        if "google" in joined or "googlemail" in joined:
            return "Google Workspace"
        elif "outlook" in joined or "microsoft" in joined or "pphosted" in joined:
            return "Microsoft 365"
        elif "zoho" in joined:
            return "Zoho Mail"
        elif "mimecast" in joined:
            return "Mimecast"
        elif "barracuda" in joined:
            return "Barracuda"
        elif "secureserver" in joined:
            return "GoDaddy"
        return "Custom/Enterprise"

    @classmethod
    def check_catch_all(cls, domain: str, mx_host: str, timeout: float = 4.0) -> Optional[bool]:
        """Test if the mail server accepts non-existent bogus email addresses (Catch-All)."""
        bogus_email = f"audit_probe_unlikely_xyz99281@{domain}"
        code, _ = cls.smtp_probe_rcpt(mx_host, bogus_email, timeout=timeout)
        if code == 250:
            return True
        elif code in {550, 551, 552, 553, 554}:
            return False
        return None

    @classmethod
    def smtp_probe_rcpt(cls, mx_host: str, recipient_email: str, timeout: float = 4.0) -> Tuple[Optional[int], str]:
        """Perform SMTP handshake without sending an email."""
        try:
            with smtplib.SMTP(mx_host, port=25, timeout=timeout) as server:
                server.ehlo_or_helo_if_needed()
                server.mail("probe@prospector-audit.org")
                code, msg = server.rcpt(recipient_email)
                return code, msg.decode("utf-8", errors="ignore")
        except (socket.timeout, TimeoutError):
            return None, "Connection timeout (Port 25 filtered or slow host)"
        except (socket.error, ConnectionRefusedError, OSError) as exc:
            return None, f"Socket error: {str(exc)}"
        except smtplib.SMTPException as exc:
            return None, f"SMTP protocol error: {str(exc)}"
        except Exception as exc:
            return None, f"Unexpected error: {str(exc)}"

    @classmethod
    def verify_permutation(
        cls,
        permutation: EmailPermutation,
        mx_info: MXInfo,
        is_catch_all: Optional[bool] = None,
        check_smtp: bool = True,
        timeout: float = 3.5,
    ) -> EmailPermutation:
        """Run deliverability verification for a single permutation."""
        if not mx_info.has_mx or not mx_info.mx_records:
            return permutation.model_copy(
                update={
                    "confidence_score": 0.0,
                    "verification_status": "undeliverable",
                    "smtp_verified": False,
                }
            )

        updated_confidence = permutation.confidence_score
        status = "likely"
        smtp_success: Optional[bool] = None
        top_mx = mx_info.mx_records[0]

        if check_smtp and top_mx:
            code, msg = cls.smtp_probe_rcpt(top_mx, permutation.email, timeout=timeout)
            if code == 250:
                smtp_success = True
                if is_catch_all is True:
                    status = "catch_all"
                    # Catch-all: cannot confirm exact mailbox, keep pattern prior
                    updated_confidence = min(0.65, permutation.confidence_score + 0.10)
                else:
                    status = "valid"
                    updated_confidence = 0.95
            elif code in {550, 551, 552, 553, 554}:
                # Check if rejection is due to sender/IP policy (e.g. Spamhaus, residential IP block)
                msg_lower = msg.lower()
                is_policy_block = any(
                    phrase in msg_lower
                    for phrase in [
                        "policy", "spamhaus", "dynamic ip", "blacklist", "blocklist",
                        "rbl", "unauthenticated", "rejected for policy"
                    ]
                )
                if is_policy_block:
                    # Server refused us due to our IP reputation, not because the mailbox is invalid
                    smtp_success = None
                    status = "likely" if is_catch_all is not True else "catch_all"
                else:
                    smtp_success = False
                    status = "undeliverable"
                    updated_confidence = 0.0
            else:
                # Port 25 timeout/blocked or server refused probe
                smtp_success = None
                status = "likely" if is_catch_all is not True else "catch_all"

        return permutation.model_copy(
            update={
                "confidence_score": updated_confidence,
                "verification_status": status,
                "smtp_verified": smtp_success,
                "is_catch_all": is_catch_all is True,
            }
        )

    @classmethod
    def test_port25_reachability(cls, mx_host: str, timeout: float = 1.5) -> bool:
        """Quickly probe if TCP port 25 is reachable from current host/ISP."""
        try:
            with socket.create_connection((mx_host, 25), timeout=timeout):
                return True
        except (socket.timeout, TimeoutError, OSError):
            return False

    @classmethod
    def verify_lead_permutations(
        cls,
        permutations: List[EmailPermutation],
        domain: str,
        mx_info: Optional[MXInfo] = None,
        check_smtp: bool = True,
    ) -> Tuple[List[EmailPermutation], Optional[str], float]:
        """Verify permutations with fast-fail port 25 probing to prevent socket hangs."""
        if not mx_info:
            mx_info = cls.lookup_mx_records(domain)

        can_probe_smtp = False
        is_catch_all = None

        if check_smtp and mx_info.has_mx and mx_info.mx_records:
            top_mx = mx_info.mx_records[0]
            # Fast 1.5s probe to check if Port 25 is filtered by ISP/cloud firewall
            can_probe_smtp = cls.test_port25_reachability(top_mx, timeout=1.5)
            if can_probe_smtp:
                is_catch_all = cls.check_catch_all(domain, top_mx, timeout=2.0)
                mx_info.is_catch_all = is_catch_all

        verified_perms: List[EmailPermutation] = []
        for idx, p in enumerate(permutations):
            # Only probe top 2 candidate permutations via SMTP to preserve speed
            probe_this = can_probe_smtp and (idx < 2)
            v_p = cls.verify_permutation(
                p,
                mx_info,
                is_catch_all=is_catch_all,
                check_smtp=probe_this,
                timeout=2.0,
            )
            verified_perms.append(v_p)

        # Sort by confidence score descending
        verified_perms.sort(key=lambda x: x.confidence_score, reverse=True)

        best_email = verified_perms[0].email if verified_perms and verified_perms[0].confidence_score > 0 else None
        best_confidence = verified_perms[0].confidence_score if verified_perms else 0.0

        return verified_perms, best_email, best_confidence
