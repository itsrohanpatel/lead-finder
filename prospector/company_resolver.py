"""Company input resolver and normalizer."""

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Optional, Tuple, List, Dict, Any
from prospector.models import CompanyInfo


LEGAL_SUFFIXES = [
    r"\binc\.?\b",
    r"\bllc\.?\b",
    r"\bltd\.?\b",
    r"\bcorp\.?\b",
    r"\bcorporation\b",
    r"\btechnologies\b",
    r"\btechnology\b",
    r"\bgroup\b",
    r"\bservices\b",
    r"\bpvt\.?\b",
    r"\bprivate\b",
    r"\bpriovate\b",
    r"\bgmbh\b",
    r"\bco\.?\b",
]


LOCATION_ALIASES = {
    "indian": "India",
    "india": "India",
    "bengaluru": "Bengaluru",
    "bangalore": "Bengaluru",
    "mumbai": "Mumbai",
    "delhi": "Delhi",
    "noida": "Noida",
    "gurgaon": "Gurugram",
    "gurugram": "Gurugram",
    "hyderabad": "Hyderabad",
    "pune": "Pune",
    "chennai": "Chennai",
    "ahmedabad": "Ahmedabad",
    "kolkata": "Kolkata",
    "dubai": "Dubai",
    "uae": "UAE",
    "riyadh": "Riyadh",
    "saudi": "Saudi Arabia",
    "uk": "United Kingdom",
    "london": "London",
    "singapore": "Singapore",
    "usa": "United States",
    "us": "United States",
}


class CompanyResolver:
    """Normalizes and resolves domain, company name, and LinkedIn URL."""

    @classmethod
    def extract_location_hint(cls, raw_input: str) -> Tuple[str, Optional[str]]:
        """Extract explicit target location and clean remaining company string."""
        cleaned = raw_input.strip()
        loc_hint = None

        pattern = r"(?i)\b(?:in|at|for|from)?\s*(" + "|".join(LOCATION_ALIASES.keys()) + r")\s*(?:team|teams|office|hub|branch|leads?|engineers?)?\b"
        match = re.search(pattern, cleaned)
        if match:
            alias = match.group(1).lower()
            loc_hint = LOCATION_ALIASES.get(alias)
            remainder = re.sub(pattern, "", cleaned).strip()
            remainder = re.sub(r"[\s\-\/]+$", "", remainder).strip()
            # Preserve if the entire input was just the company name (e.g. "Air India")
            if remainder and not remainder.lower().startswith("http") and remainder.lower() in ["air", "make"]:
                loc_hint = None
            elif remainder:
                cleaned = remainder

        return cleaned, loc_hint

    @classmethod
    def clean_company_name(cls, name: str) -> str:
        """Strip legal entity suffixes, punctuation, and extraneous words."""
        cleaned = name.strip()
        # Split CamelCase (e.g. WebIndiaInc -> Web India Inc)
        cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned)
        for suffix in LEGAL_SUFFIXES:
            cleaned = re.sub(suffix, "", cleaned, flags=re.IGNORECASE).strip()
        # Clean trailing commas/dashes/periods
        cleaned = re.sub(r"[\s,\-\.]+$", "", cleaned).strip()
        return cleaned or name.strip()

    @classmethod
    def enrich_from_website(cls, domain: str) -> Tuple[Optional[str], Optional[str], List[Dict[str, Any]]]:
        """Fetch homepage and extract official trade name, LinkedIn company page, and direct team profiles."""
        url = f"https://{domain}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        trade_name = None
        linkedin_company = None
        team_leads: List[Dict[str, Any]] = []

        GENERIC_TERMS = [
            "digital marketing", "marketing agency", "seo agency", "web development",
            "software company", "software development", "it services", "it company",
            "consultancy", "consulting", "solutions", "services", "human resource",
            "staffing", "recruitment", "home", "about us", "welcome", "official website",
            "design studio", "creative agency", "tech lab", "technologies",
            "india", "usa", "united states", "uk", "united kingdom", "australia", "canada",
            "singapore", "uae", "dubai", "global", "contact", "privacy policy",
            "one moment", "just a moment", "attention required", "cloudflare", "security check",
            "robot check", "access denied", "ddos-guard", "checking your browser", "please enable"
        ]

        try:
            resp = requests.get(url, headers=headers, timeout=3.5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")

                # 1. Clean Title Name
                if soup.title and soup.title.string:
                    title_text = soup.title.string.strip()
                    parts = re.split(r"[-|:•–—\ufffd]", title_text)
                    valid_candidates = []
                    for p in parts:
                        p_clean = cls.clean_company_name(p.strip())
                        if not p_clean or len(p_clean) > 35:
                            continue
                        if any(term == p_clean.lower() or term in p_clean.lower() for term in GENERIC_TERMS):
                            continue
                        valid_candidates.append(p_clean)

                    if valid_candidates:
                        domain_sld = domain.split(".")[0].lower()
                        sld_match = [c for c in valid_candidates if domain_sld in c.lower().replace(" ", "")]
                        if sld_match:
                            trade_name = sld_match[0]
                        else:
                            geo_names = {"india", "usa", "uk", "uae", "singapore", "australia", "canada", "global", "home"}
                            non_geo = [c for c in valid_candidates if c.lower() not in geo_names and len(c) > 2]
                            if non_geo:
                                trade_name = non_geo[0]

                # 2. LinkedIn company page
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "linkedin.com/company/" in href:
                        clean_li = href.split("?")[0].rstrip("/")
                        if clean_li.startswith("http://"):
                            clean_li = "https://" + clean_li[7:]
                        linkedin_company = clean_li
                        break

                # Fallback trade name from LinkedIn company slug if title was purely generic/geo
                if not trade_name and linkedin_company:
                    li_slug, _ = cls.parse_linkedin_company(linkedin_company)
                    if li_slug and li_slug.lower() not in {"company"}:
                        trade_name = li_slug

                # 3. Direct LinkedIn personal profiles
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "linkedin.com/in/" in href:
                        clean_url = href.split("?")[0].rstrip("/")
                        name = a.get_text(strip=True)
                        if not name and a.parent:
                            name = a.parent.get_text(strip=True)
                        if not name and a.parent and a.parent.parent:
                            gp_text = a.parent.parent.get_text(separator=" ", strip=True)
                            m = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})", gp_text)
                            if m:
                                name = m.group(1).strip()
                        if name and len(name.split()) in [2, 3]:
                            if not any(bad in name.lower() for bad in ["linkedin", "follow", "share", "view", "connect"]):
                                team_leads.append({
                                    "name": name,
                                    "linkedin_url": clean_url,
                                    "job_title": "Founder / Leadership",
                                })

                # 4. Schema.org JSON-LD & Author metadata
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        import json
                        data = json.loads(script.string or "")
                        def extract_ld_persons(obj):
                            if isinstance(obj, dict):
                                if obj.get("@type") == "Person" and obj.get("name"):
                                    p_name = obj.get("name", "").strip()
                                    if len(p_name.split()) in [2, 3] and not any(bad in p_name.lower() for bad in ["admin", "theme"]):
                                        if not any(tl["name"].lower() == p_name.lower() for tl in team_leads):
                                            team_leads.append({
                                                "name": p_name,
                                                "linkedin_url": None,
                                                "job_title": "Founder & CEO",
                                            })
                                for v in obj.values():
                                    extract_ld_persons(v)
                            elif isinstance(obj, list):
                                for item in obj:
                                    extract_ld_persons(item)
                        extract_ld_persons(data)
                    except Exception:
                        pass

                for meta in soup.find_all("meta"):
                    prop = (meta.get("property") or meta.get("name") or "").lower()
                    content = (meta.get("content") or "").strip()
                    if any(k in prop for k in ["author", "article:author"]):
                        if content and len(content.split()) in [2, 3] and not re.search(r"\d", content) and not any(bad in content.lower() for bad in ["admin", "theme", "http", "minute", "read", "view"]):
                            if not any(tl["name"].lower() == content.lower() for tl in team_leads):
                                team_leads.append({
                                    "name": content,
                                    "linkedin_url": None,
                                    "job_title": "Founder & CEO",
                                })
                # 5. Discover team/leadership subpages from nav links
                team_links = set()
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    h_lower = href.lower()
                    if any(kw in h_lower for kw in ["/team", "/leadership", "/board", "/directors", "/about"]):
                        if href.startswith("/"):
                            team_links.add(f"https://{domain}{href}")
                        elif href.startswith("http") and domain in href:
                            team_links.add(href)

                # Check top team subpage if found
                for sub_url in list(team_links)[:2]:
                    try:
                        s_resp = requests.get(sub_url, headers=headers, timeout=2.5)
                        if s_resp.status_code == 200:
                            s_soup = BeautifulSoup(s_resp.text, "html.parser")
                            for h in s_soup.find_all(["h2", "h3", "h4", "p", "strong"]):
                                text = h.get_text(strip=True)
                                m = re.match(r"(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s*([A-Za-z\s]+?)(?:\s*[-–—]\s*(.*))?$", text)
                                if m:
                                    p_name = m.group(1).strip()
                                    p_title = m.group(2).strip() if m.group(2) else "Director / Leadership"
                                    if len(p_name.split()) in [2, 3] and not any(bad in p_name.lower() for bad in ["admin", "theme"]):
                                        if not any(tl["name"].lower() == p_name.lower() for tl in team_leads):
                                            team_leads.append({
                                                "name": p_name,
                                                "linkedin_url": None,
                                                "job_title": p_title,
                                            })
                    except Exception:
                        pass
        except Exception:
            pass

        return trade_name, linkedin_company, team_leads

    @classmethod
    def extract_domain_from_url(cls, url_or_domain: str) -> Optional[str]:
        """Extract clean FQDN domain from a URL or domain string."""
        raw = url_or_domain.strip().lower()
        if not raw:
            return None

        # Add protocol if missing to assist urlparse
        if not raw.startswith(("http://", "https://")):
            raw_url = "https://" + raw
        else:
            raw_url = raw

        try:
            parsed = urlparse(raw_url)
            netloc = parsed.netloc or parsed.path
            # Strip port if present
            netloc = netloc.split(":")[0]
            # Strip www
            if netloc.startswith("www."):
                netloc = netloc[4:]
            # Ensure it looks like a valid domain with a TLD
            if "." in netloc and len(netloc.split(".")[-1]) >= 2:
                return netloc
        except Exception:
            pass

        return None

    @classmethod
    def parse_linkedin_company(cls, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse company identifier from linkedin.com/company/<slug> URL."""
        match = re.search(r"linkedin\.com/company/([a-zA-Z0-9_\-]+)", url, re.IGNORECASE)
        if match:
            slug = match.group(1).replace("-", " ").title()
            full_url = f"https://www.linkedin.com/company/{match.group(1)}/"
            return slug, full_url
        return None, None

    @classmethod
    def resolve(cls, raw_input: str, user_hint_name: Optional[str] = None) -> CompanyInfo:
        """Resolve arbitrary user input into structured CompanyInfo."""
        raw = raw_input.strip()
        if not raw:
            raise ValueError("Input company/domain string cannot be empty.")

        clean_input, loc_hint = cls.extract_location_hint(raw)
        raw_to_process = clean_input or raw

        hint_clean = cls.clean_company_name(user_hint_name) if (user_hint_name and not user_hint_name.startswith(("http://", "https://"))) else None

        # Case 1: LinkedIn Company URL
        if "linkedin.com/company/" in raw_to_process.lower():
            slug_name, linkedin_url = cls.parse_linkedin_company(raw_to_process)
            clean_name = hint_clean or slug_name or "Company"
            return CompanyInfo(
                raw_input=raw,
                clean_name=clean_name,
                domain=None,
                linkedin_company_url=linkedin_url,
                location_hint=loc_hint,
            )

        # Case 2: Looks like a domain or website URL
        extracted_domain = cls.extract_domain_from_url(raw_to_process)
        if extracted_domain and not (" " in raw_to_process and "." not in raw_to_process.split()[0]):
            # Baseline name derived from domain SLD
            parts = extracted_domain.split(".")
            sld = parts[-2] if len(parts) > 2 and parts[-2] in {"co", "com", "org", "net", "gov"} else parts[0]
            clean_name = sld.replace("-", " ").capitalize()

            # Attempt live website metadata enrichment
            trade_name, li_company, direct_leads = cls.enrich_from_website(extracted_domain)
            final_name = hint_clean or trade_name or clean_name
            # If hint unspaced matches domain sld exactly, preserve the user hint (e.g. WebIndiaInc)
            if user_hint_name and sld:
                if re.sub(r"[^a-z0-9]", "", user_hint_name.lower()) == sld.lower():
                    final_name = user_hint_name
            # If hint_clean is a typo of domain sld (e.g. Codal vs codale), prioritize domain SLD
            elif hint_clean and sld and hint_clean.lower() != sld.lower():
                if sld.lower().startswith(hint_clean.lower()) or hint_clean.lower().startswith(sld.lower()):
                    final_name = sld.capitalize()

            return CompanyInfo(
                raw_input=raw,
                clean_name=final_name,
                domain=extracted_domain,
                linkedin_company_url=li_company,
                location_hint=loc_hint,
                direct_website_leads=direct_leads,
            )

        # Case 3: Raw company name
        clean_name = hint_clean or cls.clean_company_name(raw_to_process)
        return CompanyInfo(
            raw_input=raw,
            clean_name=clean_name,
            domain=None,
            linkedin_company_url=None,
            location_hint=loc_hint,
        )
