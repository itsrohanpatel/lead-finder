"""Parses search results into validated LeadRecord objects."""

import re
from typing import List, Optional, Tuple, Dict, Any
from prospector.models import LeadRecord, RoleCategory


C_SUITE_KEYWORDS = [
    r"\bc[.-]?e[.-]?o\b",
    r"\bchief executive\b",
    r"\bc[.-]?t[.-]?o\b",
    r"\bchief technology\b",
    r"\bchief technical\b",
    r"\bc[.-]?o[.-]?o\b",
    r"\bchief operating\b",
    r"\bc[.-]?f[.-]?o\b",
    r"\bchief financial\b",
    r"\bc[.-]?m[.-]?o\b",
    r"\bchief marketing\b",
    r"\bc[.-]?r[.-]?o\b",
    r"\bchief revenue\b",
    r"\bc[.-]?p[.-]?o\b",
    r"\bchief product\b",
    r"\bc[.-]?i[.-]?o\b",
    r"\bchief information\b",
    r"\bc[.-]?i[.-]?s[.-]?o\b",
    r"\bchief information security\b",
    r"\bc[.-]?b[.-]?o\b",
    r"\bchief business\b",
    r"\bc[.-]?c[.-]?o\b",
    r"\bchief commercial\b",
    r"\bc[.-]?s[.-]?o\b",
    r"\bchief strategy\b",
    r"\bc[.-]?d[.-]?o\b",
    r"\bchief digital\b",
    r"\bchief data\b",
    r"\bc[.-]?x[.-]?o\b",
    r"\bco-?founder\b",
    r"\bcofounder\b",
    r"\bfounder\b",
    r"\bfounding partner\b",
    r"\bfounding member\b",
    r"\bpresident\b",
    r"\bchairman\b",
    r"\bchairperson\b",
    r"\bchair\b",
    r"\bboard member\b",
    r"\bboard of directors\b",
    r"\bmanaging director\b",
    r"\bdirector\b",
    r"\bdirectors\b",
    r"\bmanaging partner\b",
    r"\bowner\b",
    r"\bco-?owner\b",
    r"\bproprietor\b",
    r"\bpromoter\b",
    r"\bentrepreneur\b",
    r"\bmanaging trustee\b",
    r"\bvp\b",
    r"\bvice president\b",
    r"\bpartner\b",
    r"\bchief\b",
    r"\bfounder'?s? office\b",
]

HR_TALENT_KEYWORDS = [
    r"\bhuman resources?\b",
    r"\bhr\b",
    r"\bhrbp\b",
    r"\bchro\b",
    r"\bchief human resources\b",
    r"\bchief people\b",
    r"\btalent\b",
    r"\brecruit\w*\b",
    r"\bpeople\b",
    r"\bstaffing\b",
    r"\bsourcing\b",
    r"\bhiring\b",
    r"\bonboarding\b",
    r"\btrain\w*\b",
    r"\blearning\b",
    r"\bl&d\b",
    r"\bl & d\b",
    r"\blearning and development\b",
    r"\blearning & development\b",
    r"\bpayroll\b",
    r"\bemployee experience\b",
    r"\bemployee relations\b",
    r"\bemployee engagement\b",
    r"\bpeople ops\b",
    r"\bpeople operations\b",
    r"\bpeople & culture\b",
    r"\bpeople and culture\b",
    r"\bworkforce\b",
    r"\bhuman capital\b",
    r"\bhead of hr\b",
    r"\bhead of people\b",
    r"\bhead of talent\b",
    r"\bhead of recruiting\b",
    r"\bvp hr\b",
    r"\bvp of human resources\b",
    r"\bvp human resources\b",
    r"\bvp of people\b",
    r"\bvp people\b",
    r"\bvp of people and culture\b",
    r"\bvp people & culture\b",
    r"\bvp of talent\b",
    r"\bvp talent\b",
    r"\bdirector of human resources\b",
    r"\bdirector of people\b",
    r"\bdirector of talent acquisition\b",
    r"\bhr director\b",
    r"\bhr generalist\b",
    r"\bhuman resources generalist\b",
    r"\bhr specialist\b",
    r"\bhr manager\b",
    r"\bhuman resources manager\b",
    r"\bpeople manager\b",
    r"\bpeople operations manager\b",
    r"\bhr lead\b",
    r"\bhr leader\b",
    r"\bhr partner\b",
    r"\bhr business partner\b",
    r"\bsenior hr business partner\b",
    r"\bsr\.?\s*hrbp\b",
    r"\btalent acquisition manager\b",
    r"\btalent acquisition specialist\b",
    r"\brecruiting manager\b",
    r"\bcorporate recruiter\b",
    r"\btechnical recruiter\b",
    r"\btech recruiter\b",
    r"\bta lead\b",
    r"\bta manager\b",
    r"\bta\s+(?:specialist|lead|manager|partner|head|recruiter|director)\b",
    r"\bcomp(?:ensation)? & ben(?:efits)?\b",
    r"\btotal rewards\b",
    r"\bindustrial relations\b",
    r"\bir & hr\b",
    r"\bhr & ir\b",
]

TECH_LEAD_KEYWORDS = [
    r"\btech(?:nical)?\s+lead\b",
    r"\blead\s+(?:software\s+)?(?:engineer|developer|architect)\b",
    r"\bhead\s+of\s+(?:engineering|tech(?:nology)?|software)\b",
    r"\bvp\s+(?:of\s+)?(?:engineering|tech(?:nology)?|software)\b",
    r"\bvice\s+president\s+(?:of\s+)?(?:engineering|tech(?:nology)?|software)\b",
    r"\bdirector\s+(?:of\s+)?(?:engineering|tech(?:nology)?|software)\b",
    r"\bengineering\s+(?:manager|director|lead|head)\b",
    r"\bfounding\s+engineer\b",
    r"\bfounding\s+developer\b",
    r"\bprincipal\s+(?:software\s+)?(?:engineer|architect|developer)\b",
    r"\bstaff\s+(?:software\s+)?(?:engineer|architect|developer)\b",
    r"\bsoftware\s+architect\b",
    r"\bsolutions?\s+architect\b",
    r"\bbackend\s+(?:lead|architect|engineer)\b",
    r"\bfrontend\s+(?:lead|architect|engineer)\b",
    r"\bdata\s+science\s+lead\b",
    r"\bai\s+(?:engineer|lead|architect)\b",
    r"\bml\s+(?:engineer|lead|architect)\b",
    r"\bdevops\s+lead\b",
    r"\bsre\s+lead\b",
]

PRODUCT_KEYWORDS = [
    r"\bhead\s+of\s+product\b",
    r"\bvp\s+(?:of\s+)?product\b",
    r"\bvice\s+president\s+(?:of\s+)?product\b",
    r"\bdirector\s+(?:of\s+)?product\b",
    r"\bproduct\s+manager\b",
    r"\bgroup\s+product\s+manager\b",
    r"\bprincipal\s+product\s+manager\b",
    r"\blead\s+product\s+manager\b",
    r"\bsenior\s+product\s+manager\b",
    r"\bproduct\s+lead\b",
    r"\bproduct\s+owner\b",
    r"\bproduct\s+analytics\b",
    r"\bhead\s+of\s+design\b",
    r"\bproduct\s+designer\b",
    r"\bdesign\s+lead\b",
]


class LeadExtractor:
    """Extracts, categorizes, and validates leads from search result items."""

    @classmethod
    def is_individual_linkedin_profile(cls, url: str) -> bool:
        """Verify URL is an individual profile (not company, job, or search page)."""
        clean_url = url.lower()
        if "linkedin.com/in/" not in clean_url:
            return False
        # Exclude directories and job listings
        if any(bad in clean_url for bad in ["/dir/", "/jobs/", "/pulse/", "/learning/"]):
            return False
        return True

    @classmethod
    def clean_linkedin_url(cls, url: str) -> str:
        """Strip tracking query parameters from LinkedIn URL."""
        return url.split("?")[0].rstrip("/")

    @classmethod
    def parse_name_and_title(cls, raw_title: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract person's name and job title from typical LinkedIn SERP titles.
        
        Examples:
        - "Satya Nadella - Chairman and CEO - Microsoft | LinkedIn"
        - "Jane Doe | Head of Talent - Stripe"
        - "Alex Smith - Chief Technology Officer at Acme"
        """
        # Split on concatenated profile separators (e.g. DuckDuckGo clustered results)
        first_chunk = re.split(r"(?:\|\s*LinkedIn|\.\.\.)", raw_title, flags=re.IGNORECASE)[0].strip()

        # Strip trailing branding ("| LinkedIn", "- LinkedIn", etc.)
        cleaned = re.sub(r"[\-\|\–\—]\s*LinkedIn.*$", "", first_chunk, flags=re.IGNORECASE).strip()

        # Common delimiters between Name, Title, and Company: ' - ', ' | ', ' – ', ' — '
        parts = re.split(r"\s+[\-\|\–\—]\s+", cleaned)
        CERT_REGEX = r"(?i),?\s*(?:shrm[-–]?[a-z]*|phr|sphr|pmp|cpa|mba|ca|cfa|acc)\b"

        if len(parts) >= 2:
            name_candidate = re.sub(CERT_REGEX, "", parts[0]).strip()
            title_candidate = parts[1].strip()
            # If title contains ' at Company' or ' @Company', clean it
            title_candidate = re.sub(r"(?:\s+\bat\b\s+|\s+@\s*).*$", "", title_candidate, flags=re.IGNORECASE).strip()
            return name_candidate, title_candidate

        # Alternate format: "John Doe, CEO at Company"
        match = re.search(r"^([a-zA-Z\s\.\'\-]+),\s*(.*?)(?:\s+at\s+.*|\s+@\s*.*)?$", cleaned)
        if match:
            raw_name = match.group(1).strip()
            name_candidate = re.sub(CERT_REGEX, "", raw_name).strip()
            return name_candidate, match.group(2).strip()

        return None, None

    @classmethod
    def split_name(cls, full_name: str) -> Tuple[str, str]:
        """Split full name into first name and last name."""
        CERT_REGEX = r"(?i),?\s*(?:shrm[-–]?[a-z]*|phr|sphr|pmp|cpa|mba|ca|cfa|acc)\b"
        cleaned_name = re.sub(CERT_REGEX, "", full_name).strip()
        tokens = [t.strip() for t in cleaned_name.split() if t.strip()]
        if not tokens:
            return "", ""
        if len(tokens) == 1:
            return tokens[0], ""
        return tokens[0], tokens[-1]

    @classmethod
    def categorize_role(cls, title: str) -> RoleCategory:
        """Categorize job title into C-Suite, HR/Talent, or Other."""
        title_lower = title.lower()
        for kw in HR_TALENT_KEYWORDS:
            if re.search(kw, title_lower):
                return RoleCategory.HR_TALENT
        for kw in C_SUITE_KEYWORDS:
            if re.search(kw, title_lower):
                return RoleCategory.C_SUITE
        return RoleCategory.OTHER

    @classmethod
    def get_brand_tokens(cls, company_name: str, domain: Optional[str] = None) -> List[str]:
        """Extract unique core brand tokens (excluding generic terms like 'technologies', 'solutions')."""
        tokens = set()
        COMMON_PREFIXES = {"web", "info", "data", "cloud", "tech", "soft", "net", "app", "digi", "cyber", "the", "and", "india", "global"}
        GENERIC_WORDS = {
            "innovations", "technologies", "technology", "solutions", "services", "systems",
            "consultancy", "consulting", "labs", "studio", "group", "international", "enterprises",
            "pvt", "pvts", "ltd", "inc", "llc", "the", "and", "co", "management", "holdings",
            "agency", "global", "media", "admedia", "business", "master", "mastertech", "venture", "ventures",
            "design", "marketing", "digital", "creative", "studios", "lab", "electric", "supply",
            "robotics", "robotic", "steam", "toy", "estate", "real", "security", "fast", "app", "apps",
            "cloud", "data", "soft", "ai", "tech", "web", "india", "legal", "online", "institute", "connect",
            "brand", "direct", "interiors", "capital", "advisors", "partners", "llp", "pty", "corp", "corporation",
            "company", "team", "network", "works", "space", "hub"
        }

        # 1. Full unspaced name and base without legal suffixes
        unspaced = re.sub(r"[^a-z0-9]", "", company_name.lower())
        for g in ["inc", "pvt", "ltd", "co", "llc", "technologies", "solutions"]:
            if unspaced.endswith(g) and len(unspaced) > len(g) + 3:
                base_cand = unspaced[:-len(g)]
                # Don't add base if it's composed purely of common prefixes (e.g. 'web' + 'india')
                rem = base_cand
                for p in sorted(COMMON_PREFIXES, key=len, reverse=True):
                    rem = rem.replace(p, "")
                if len(rem) > 0:
                    tokens.add(base_cand)
        tokens.add(unspaced)

        # 2. Domain SLD
        if domain:
            domain_sld = domain.split(".")[0].lower()
            clean_sld = re.sub(r"[^a-z0-9]", "", domain_sld)
            tokens.add(clean_sld)
            for g in ["inc", "pvt", "ltd", "co", "llc", "tech", "labs", "solutions", "agency", "hq", "studio"]:
                if clean_sld.endswith(g) and len(clean_sld) > len(g) + 2:
                    base_cand = clean_sld[:-len(g)]
                    rem = base_cand
                    for p in sorted(COMMON_PREFIXES, key=len, reverse=True):
                        rem = rem.replace(p, "")
                    if len(rem) > 0:
                        tokens.add(base_cand)

        # 3. Individual words from company name ONLY if >= 4 chars and not in COMMON_PREFIXES/GENERIC_WORDS
        for w in re.findall(r"[a-zA-Z0-9]+", company_name.lower()):
            if len(w) >= 4 and w not in GENERIC_WORDS and w not in COMMON_PREFIXES:
                tokens.add(w)

        return [t for t in tokens if len(t) >= 4 and t not in GENERIC_WORDS and t not in COMMON_PREFIXES]

    @classmethod
    def extract_explicit_employer(cls, headline: str) -> Optional[str]:
        """Extract explicit employer name from headline if present."""
        # Pattern 1: standard prepositions (at, @, for, and qualified 'of')
        # Negative lookbehinds ONLY apply to 'of' to avoid matching 'Head of Talent', 'Director of HR', etc.
        m = re.search(
            r"(?:(?:\bat\b|@|\bfor\b)|(?<!\bhead\s)(?<!\bdirector\s)(?<!\bvp\s)(?<!\bchief\s)(?<!\bmanager\s)(?<!\blead\s)(?<!\bofficer\s)(?<!\bpresident\s)\bof\b)\s*([A-Za-z0-9\s\.\&\-]+)",
            headline,
            re.IGNORECASE,
        )
        if m:
            emp = re.split(r"[\-\|\–\—:,]", m.group(1))[0].strip()
            if len(emp) >= 2:
                return emp

        role_words = {
            "founder", "ceo", "director", "partner", "lead", "manager", "specialist",
            "recruiter", "recruiting", "generalist", "head", "vp", "president", "consultant", "engineer",
            "developer", "innovator", "strategist", "hiring", "talent", "hr", "operations",
            "human", "resources", "assistant", "accounting", "admin", "administrator", "people", "staff"
        }
        non_entity_words = {
            "business", "personal", "portfolio", "growth", "speaker", "author", "coach",
            "mentor", "advisor", "enthusiast", "leader", "passionate", "helping", "building",
            "driving", "experienced", "professional", "strategy", "innovation", "management",
            "education", "experience", "about", "skills", "activities", "contact", "info",
            "view", "profile", "projects", "certifications", "licenses", "honors", "awards", "volunteer"
        }

        location_words = {
            "india", "usa", "uk", "kolkata", "mumbai", "delhi", "bengaluru", "bangalore",
            "hyderabad", "pune", "chennai", "ahmedabad", "gurgaon", "gurugram", "noida",
            "jaipur", "surat", "lucknow", "chandigarh", "coimbatore", "indore", "vadodara",
            "san francisco", "new york", "london", "dubai", "singapore", "toronto", "sydney",
            "remote", "area", "region", "city", "metro", "greater"
        }
        entity_indicators = {
            "ltd", "pvt", "inc", "llc", "holdings", "group", "solutions", "technologies",
            "innovations", "studio", "labs", "agency", "ventures", "enterprises", "pty",
            "llp", "capital", "advisors", "master", "interiors", "systems", "consulting",
            "media", "infosys", "supply", "fast", "corporation", "company", "apparel", "apparels"
        }

        # Pattern 2: comma or pipe followed by an entity name (e.g. 'CEO, Infocus Holdings Pty Ltd', 'Founder, Infosys')
        m2 = re.search(r"(?:,\s*|\s*\|\s*)([A-Za-z0-9\s\.\&]+)", headline)
        if m2:
            candidate = m2.group(1).strip()
            cand_words = set(candidate.lower().split())
            is_loc = any(loc in cand_words for loc in location_words) and not any(ind in cand_words for ind in entity_indicators)
            is_dir = candidate.lower() in {"linkedin", "profiles", "directory", "jobs", "hiring", "careers"}
            if any(ind in cand_words for ind in entity_indicators) or (len(cand_words) <= 4 and not (cand_words & role_words) and not (cand_words & non_entity_words) and not is_loc and not is_dir):
                return candidate

        # Pattern 3: multi-segment headline 'Name - Title - Company'
        parts = re.split(r"\s+[\-\|\–\—]\s+", headline)
        if len(parts) >= 3:
            candidate = parts[-1].strip()
            cand_words = set(candidate.lower().split())
            is_loc = any(loc in cand_words for loc in location_words) and not any(ind in cand_words for ind in entity_indicators)
            is_dir = candidate.lower() in {"linkedin", "profiles", "directory", "jobs", "hiring", "careers"}
            if len(candidate) >= 2 and not (cand_words & role_words) and not (cand_words & non_entity_words) and not is_loc and not is_dir:
                return candidate

        return None

    @classmethod
    def employer_matches_company(cls, explicit_employer: str, company_name: str, domain: Optional[str] = None) -> bool:
        """Check if an explicitly stated employer matches the target company."""
        brand_tokens = cls.get_brand_tokens(company_name, domain)
        if not brand_tokens:
            return True
        c_emp = re.sub(r"[^a-z0-9]", "", explicit_employer.lower())
        return any(t in c_emp for t in brand_tokens)

    @classmethod
    def extract_location(cls, snippet: str, url: str, candidate_name: Optional[str] = None) -> Optional[str]:
        """Extract geographic location from search snippet or LinkedIn country subdomain."""
        if not snippet:
            snippet = ""
        loc = None

        # Localize snippet search window if candidate name is present (prevents cluster leakage)
        target_text = snippet
        if candidate_name and candidate_name in snippet:
            idx = snippet.find(candidate_name)
            target_text = snippet[idx:idx + 400]
        elif candidate_name and len(candidate_name.split()) > 1:
            last_name = candidate_name.split()[-1]
            if last_name in snippet:
                idx = snippet.find(last_name)
                target_text = snippet[idx:idx + 400]

        # 1. Explicit 'Location: <value>' pattern
        m = re.search(r"Location:\s*([^·•\|\–\—\n\r\<\>]+)", target_text, re.IGNORECASE)
        if not m and target_text != snippet:
            m = re.search(r"Location:\s*([^·•\|\–\—\n\r\<\>]+)", snippet, re.IGNORECASE)

        if m:
            candidate = m.group(1).strip()
            if "{" in candidate or "}" in candidate:
                candidate = re.sub(r"\{[^\}]*\}", "", candidate).strip()
            candidate = re.split(
                r"(\d+\+?\s*connections|\bview\b|\bexperience\b|\beducation\b|\babout\b)",
                candidate,
                flags=re.IGNORECASE,
            )[0].strip()
            candidate = re.sub(r"^[^\w]+", "", candidate).strip()
            candidate = re.sub(r"[\.\,\s]+$", "", candidate).strip()
            if len(candidate) >= 2 and not candidate.isdigit() and "{" not in candidate:
                loc = candidate

        # 2. Pattern: "<City>, <State>, <Country>" or "<City>, <Country>" in snippet
        if not loc:
            m_city = re.search(
                r"\b([A-Z][a-zA-Z\s]{2,20},\s*(?:[A-Z][a-zA-Z\s]{2,20},\s*)?(?:India|USA|United States|UK|United Kingdom|Australia|Canada|Singapore|UAE|Germany))\b",
                target_text,
            )
            if m_city:
                loc = m_city.group(1).strip()

        # 3. Check explicit Indian tech cities in snippet
        INDIAN_CITY_NAMES = [
            "Bengaluru", "Bangalore", "Mumbai", "Delhi", "New Delhi", "Gurgaon", "Gurugram",
            "Noida", "Hyderabad", "Pune", "Chennai", "Ahmedabad", "Kolkata", "Jaipur",
            "Kochi", "Chandigarh", "Indore", "Surat", "Vadodara"
        ]
        if not loc:
            for city in INDIAN_CITY_NAMES:
                if re.search(rf"\b{city}\b", target_text, re.IGNORECASE):
                    loc = f"{city}, India"
                    break

        # 4. Country inference from LinkedIn country subdomain (e.g., in.linkedin.com)
        country_map = {
            "in": "India",
            "uk": "United Kingdom",
            "au": "Australia",
            "ca": "Canada",
            "sg": "Singapore",
            "ae": "UAE",
            "de": "Germany",
            "fr": "France",
            "nl": "Netherlands",
            "us": "United States",
        }
        subdomain_match = re.search(r"https?://([a-z]{2})\.linkedin\.com", url.lower())
        country = country_map.get(subdomain_match.group(1)) if subdomain_match else None

        FOREIGN_CITIES = {
            "sydney", "melbourne", "brisbane", "perth", "london", "manchester", "birmingham",
            "portland", "new york", "san francisco", "chicago", "los angeles", "seattle",
            "toronto", "vancouver", "montreal", "singapore", "dubai", "berlin", "paris"
        }

        if loc and country:
            loc_lower = loc.lower()
            is_foreign = any(fc in loc_lower for fc in FOREIGN_CITIES)
            if country == "India" and is_foreign:
                pass  # Do not attach India to a known foreign city
            elif country.lower() not in loc_lower:
                loc = f"{loc}, {country}"
        elif not loc and country:
            loc = country

        return loc

    @classmethod
    def matches_target_location(cls, lead_location: Optional[str], target_location: str) -> bool:
        """Check if a lead's location matches the target location criteria."""
        if not target_location or not target_location.strip():
            return True
        t_loc = target_location.strip().lower()

        # 'Pan India' or 'India' matches any lead located in India or with unknown location
        if t_loc in ["pan india", "pan-india", "all india", "india"]:
            if not lead_location:
                return True
            l_lower = lead_location.lower()
            foreign_countries = [
                "australia", "canada", "united kingdom", "uk", "usa", "united states",
                "germany", "singapore", "france", "uae", "taiwan", "georgia"
            ]
            if any(fc in l_lower for fc in foreign_countries) and "india" not in l_lower:
                return False
            indian_cities = [
                "bengaluru", "bangalore", "mumbai", "delhi", "gurgaon", "gurugram",
                "noida", "hyderabad", "pune", "chennai", "ahmedabad", "kolkata", "jaipur"
            ]
            if any(ic in l_lower for ic in indian_cities):
                return True
            return "india" in l_lower

        # Specific city or region requested (e.g., 'Ahmedabad', 'Bengaluru', 'Mumbai')
        if not lead_location:
            return True  # Benefit of doubt if location is unspecified

        if t_loc in ["bengaluru", "bangalore"]:
            return any(b in lead_location.lower() for b in ["bengaluru", "bangalore"])
        if t_loc in ["gurgaon", "gurugram"]:
            return any(g in lead_location.lower() for g in ["gurgaon", "gurugram"])

        return t_loc in lead_location.lower()

    @classmethod
    def extract_leads(
        cls,
        search_results: List[Dict[str, Any]],
        company_name: str,
        domain: Optional[str] = None,
        target_roles: Optional[List[RoleCategory]] = None,
        location: Optional[str] = None,
    ) -> List[LeadRecord]:
        """Extract deduplicated and qualified leads from raw search engine results."""
        leads: List[LeadRecord] = []
        seen_urls = set()
        seen_names = set()

        if target_roles is None:
            target_roles = [RoleCategory.C_SUITE, RoleCategory.HR_TALENT]

        brand_tokens = cls.get_brand_tokens(company_name, domain)

        GENERIC_NAME_WORDS = {
            "blog", "solutions", "services", "technologies", "innovations", "consulting",
            "software", "private", "limited", "company", "team", "support", "sales",
            "office", "payroll", "management", "portal", "expert", "corporation",
            "labs", "studio", "enterprises", "agency", "ventures", "technolab", "digital",
            "group", "holdings", "media", "ai", "hub", "tech", "india", "pvt", "ltd", "inc",
            "llc", "institute", "connect", "supply", "electric", "brand"
        }

        for item in search_results:
            link = item.get("link", "")
            title = item.get("title", "")

            if not cls.is_individual_linkedin_profile(link):
                continue

            clean_url = cls.clean_linkedin_url(link)
            if clean_url in seen_urls:
                continue

            # Split out first chunk corresponding to this specific person's profile
            first_chunk = re.split(r"(?:\|\s*LinkedIn|\.\.\.)", title, flags=re.IGNORECASE)[0].strip()
            name, job_title = cls.parse_name_and_title(first_chunk or title)
            if not name or not job_title:
                continue

            # Skip if name looks like generic text, directory, or company entity
            name_words = name.lower().split()
            if any(w in name_words for w in GENERIC_NAME_WORDS):
                continue
            if any(bad in name.lower() for bad in ["linkedin", "profiles", "directory", "jobs", "hiring", "careers"]):
                continue

            # Reject if candidate name matches company (e.g. 'Avyam Labs', 'EVEOAI Private Limited')
            compact_name = re.sub(r"[^a-z0-9]", "", name.lower())
            c_comp = re.sub(r"[^a-z0-9]", "", company_name.lower())
            if compact_name == c_comp:
                continue

            first_name, last_name = cls.split_name(name)
            if not first_name:
                continue

            name_key = f"{first_name.lower()} {last_name.lower()}"
            if name_key in seen_names:
                continue

            # 1. Check if headline states an explicit employer
            explicit_emp = cls.extract_explicit_employer(first_chunk)
            emp_verified = False
            if explicit_emp:
                if cls.employer_matches_company(explicit_emp, company_name, domain):
                    emp_verified = True
                else:
                    continue

            # 2. Verify brand token presence in person's headline or immediate snippet header
            if emp_verified:
                chunk_has_brand = True
            else:
                # Strip candidate's own name to prevent self-name false matches (e.g. surname 'Jain' matching brand token 'jain')
                non_name_chunk = first_chunk
                if name:
                    non_name_chunk = re.sub(r"\b" + re.escape(name) + r"\b", "", non_name_chunk, flags=re.IGNORECASE)
                if first_name:
                    non_name_chunk = re.sub(r"\b" + re.escape(first_name) + r"\b", "", non_name_chunk, flags=re.IGNORECASE)
                if last_name:
                    non_name_chunk = re.sub(r"\b" + re.escape(last_name) + r"\b", "", non_name_chunk, flags=re.IGNORECASE)

                c_chunk = re.sub(r"[^a-z0-9]", "", non_name_chunk.lower())
                chunk_has_brand = any(token in c_chunk for token in brand_tokens) if brand_tokens else True

            # If headline doesn't explicitly have the brand token, inspect only the first 140 chars
            # of snippet (excluding candidate name) to avoid cross-profile leakage from search engine clustering
            snippet_has_brand = False
            if not chunk_has_brand and brand_tokens:
                snippet_head = item.get("snippet", "")[:140]
                if name:
                    snippet_head = re.sub(r"\b" + re.escape(name) + r"\b", "", snippet_head, flags=re.IGNORECASE)
                if last_name:
                    snippet_head = re.sub(r"\b" + re.escape(last_name) + r"\b", "", snippet_head, flags=re.IGNORECASE)
                c_snip_head = re.sub(r"[^a-z0-9]", "", snippet_head.lower())
                snippet_has_brand = any(token in c_snip_head for token in brand_tokens)

            if not (chunk_has_brand or snippet_has_brand) and len(company_name) > 2:
                continue

            role_cat = cls.categorize_role(job_title)
            if role_cat not in target_roles and RoleCategory.OTHER not in target_roles:
                continue

            # Extract location from snippet and LinkedIn URL
            snippet_text = item.get("snippet") or item.get("body") or ""
            lead_loc = cls.extract_location(snippet_text, link, candidate_name=name)

            # Location filtering for non-C-Suite regional leads:
            # If target location is specified, filter out non-matching regional leads.
            # (Founders / C-Suite are preserved because founders can be anywhere)
            if location and role_cat == RoleCategory.HR_TALENT:
                if not cls.matches_target_location(lead_loc, location):
                    continue

            seen_urls.add(clean_url)
            seen_names.add(name_key)

            leads.append(
                LeadRecord(
                    full_name=name,
                    first_name=first_name,
                    last_name=last_name,
                    job_title=job_title,
                    role_category=role_cat,
                    linkedin_url=clean_url,
                    company_name=company_name,
                    domain=domain,
                    location=lead_loc,
                )
            )

        return leads

