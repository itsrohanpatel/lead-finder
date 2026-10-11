"""Master orchestrator pipeline for Prospector-AI."""

import re
import time
import logging
from typing import List, Optional
from prospector.models import (
    CompanyInfo,
    LeadRecord,
    MXInfo,
    ProspectorResult,
    RoleCategory,
)
from prospector.company_resolver import CompanyResolver
from prospector.search_engine import SearchEngine
from prospector.lead_extractor import LeadExtractor
from prospector.email_permutator import EmailPermutator
from prospector.email_verifier import EmailVerifier

logger = logging.getLogger(__name__)


class ProspectorPipeline:
    """End-to-end prospecting pipeline."""

    def __init__(
        self,
        search_engine: Optional[SearchEngine] = None,
        check_smtp: bool = True,
        max_leads_per_role: int = 10,
    ):
        self.search_engine = search_engine or SearchEngine()
        self.check_smtp = check_smtp
        self.max_leads_per_role = max_leads_per_role

    def run(
        self,
        company_input: str,
        company_name_hint: Optional[str] = None,
        target_roles: Optional[List[RoleCategory]] = None,
        location: Optional[str] = None,
    ) -> ProspectorResult:
        """Execute prospecting workflow for a single company."""
        start_time = time.time()
        logger.info(f"Starting prospecting for: {company_input}")

        if target_roles is None:
            target_roles = [RoleCategory.C_SUITE, RoleCategory.HR_TALENT, RoleCategory.TECH_LEAD, RoleCategory.PRODUCT]

        # Step 1: Resolve Company Info
        company_info = CompanyResolver.resolve(company_input, user_hint_name=company_name_hint)

        # If user did not pass explicit location, use auto-detected location hint from input
        if location is None and company_info.location_hint:
            location = company_info.location_hint
            logger.info(f"Auto-detected target location from query: {location}")

        # If domain missing, attempt to discover it via search engine
        if not company_info.domain:
            discovered_domain = self.search_engine.find_company_domain(company_info.clean_name)
            if discovered_domain:
                company_info.domain = discovered_domain
                logger.info(f"Discovered domain for {company_info.clean_name}: {discovered_domain}")

        # Step 2: Initialize leads with direct website team members (if discovered)
        extracted_leads: List[LeadRecord] = []
        seen_names = set()
        seen_urls = set()

        if company_info.direct_website_leads and RoleCategory.C_SUITE in target_roles:
            for dl in company_info.direct_website_leads:
                fname, lname = LeadExtractor.split_name(dl["name"])
                if fname:
                    lead_rec = LeadRecord(
                        full_name=dl["name"],
                        first_name=fname,
                        last_name=lname,
                        job_title=dl.get("job_title", "Leadership / Founder"),
                        role_category=RoleCategory.C_SUITE,
                        linkedin_url=dl.get("linkedin_url"),
                        company_name=company_info.clean_name,
                        domain=company_info.domain,
                    )
                    extracted_leads.append(lead_rec)
                    seen_names.add(f"{fname.lower()} {lname.lower()}")
                    if dl.get("linkedin_url"):
                        seen_urls.add(dl.get("linkedin_url"))

        # Step 3: Query Search Engine with Role-Specific Dorks
        raw_search_items = []
        name = company_info.clean_name
        domain_sld = company_info.domain.split(".")[0].lower() if company_info.domain else ""

        # Collect distinct search terms without restrictive quotes
        search_terms = []
        if name:
            search_terms.append(name)
            base_words = [w for w in name.split() if w.lower() not in {"innovations", "technologies", "technology", "solutions", "services", "systems", "labs", "studio", "group", "ventures", "pvt", "ltd", "inc"}]
            if base_words and len(base_words) < len(name.split()):
                search_terms.append(" ".join(base_words))

        if domain_sld and domain_sld not in [s.lower().replace(" ", "") for s in search_terms]:
            search_terms.append(domain_sld)

        if company_info.linkedin_company_url:
            match_slug = re.search(r"linkedin\.com/company/([a-zA-Z0-9_\-]+)", company_info.linkedin_company_url)
            if match_slug:
                raw_slug = match_slug.group(1).lower()
                if raw_slug not in [s.lower().replace(" ", "") for s in search_terms]:
                    search_terms.append(raw_slug)

        # Smart acronym expansions for HR/Tech/AI
        name_lower = name.lower()
        if name_lower.endswith("hrm") and len(name) > 3:
            base = name[:-3].strip()
            search_terms.extend([f"{base.upper()} HR", f"{base.upper()} HR Management"])
        elif name_lower.endswith("hr") and len(name) > 2:
            base = name[:-2].strip()
            search_terms.extend([f"{base.upper()} HR", f"{base.title()} HR"])
        elif name_lower.endswith("ai") and len(name) > 2:
            base = name[:-2].strip()
            search_terms.append(f"{base.title()} AI")

        # Execute queries per target role and term (up to 3 unique terms)
        seen_query_terms = set()
        for term in search_terms[:3]:
            term_variants = [term]
            if term.lower() != term:
                term_variants.append(term.lower())

            for t_var in term_variants:
                t_clean = t_var.strip()
                if t_clean in seen_query_terms:
                    continue
                seen_query_terms.add(t_clean)

                loc_suffix = ""
                if location:
                    loc_clean = location.strip()
                    if loc_clean.lower() in ["pan india", "pan-india", "all india"]:
                        loc_suffix = "India"
                    else:
                        loc_suffix = loc_clean

                term_q = f'"{t_var}"' if (" " in t_var and not t_var.startswith('"')) else t_var

                if RoleCategory.C_SUITE in target_roles:
                    for role_kw in ["CEO", "Founder", "Director"]:
                        dork = f"site:linkedin.com/in {term_q} {role_kw}"
                        results = self.search_engine.query(dork, max_results=self.max_leads_per_role)
                        if results:
                            raw_search_items.extend(results)
                        if loc_suffix:
                            dork_loc = f"site:linkedin.com/in {term_q} {role_kw} {loc_suffix}".strip()
                            results_loc = self.search_engine.query(dork_loc, max_results=self.max_leads_per_role)
                            if results_loc:
                                raw_search_items.extend(results_loc)

                if RoleCategory.HR_TALENT in target_roles:
                    hr_kws = ["HR", "Talent", "People", "Hiring"]
                    for role_kw in hr_kws:
                        dork = f"site:linkedin.com/in {term_q} {role_kw} {loc_suffix}".strip()
                        results = self.search_engine.query(dork, max_results=self.max_leads_per_role)
                        if results:
                            raw_search_items.extend(results)

                if RoleCategory.TECH_LEAD in target_roles:
                    tech_kws = ["Tech Lead", "Founding Engineer", "Head of Engineering", "Engineering Lead", "Software Engineer"]
                    for role_kw in tech_kws:
                        dork = f"site:linkedin.com/in {term_q} \"{role_kw}\" {loc_suffix}".strip()
                        results = self.search_engine.query(dork, max_results=self.max_leads_per_role)
                        if results:
                            raw_search_items.extend(results)

                if RoleCategory.PRODUCT in target_roles:
                    prod_kws = ["Head of Product", "Product Manager", "Product Lead"]
                    for role_kw in prod_kws:
                        dork = f"site:linkedin.com/in {term_q} \"{role_kw}\" {loc_suffix}".strip()
                        results = self.search_engine.query(dork, max_results=self.max_leads_per_role)
                        if results:
                            raw_search_items.extend(results)

        # Step 4: Extract Leads from Search Results
        search_leads = LeadExtractor.extract_leads(
            search_results=raw_search_items,
            company_name=company_info.clean_name,
            domain=company_info.domain,
            target_roles=target_roles,
            location=location,
        )

        # Merge deduplicated leads
        for sl in search_leads:
            name_key = f"{sl.first_name.lower()} {sl.last_name.lower()}"
            if name_key not in seen_names and sl.linkedin_url not in seen_urls:
                extracted_leads.append(sl)
                seen_names.add(name_key)
                if sl.linkedin_url:
                    seen_urls.add(sl.linkedin_url)


        # Step 4: MX Lookup & Fingerprinting
        mx_info: Optional[MXInfo] = None
        if company_info.domain:
            mx_info = EmailVerifier.lookup_mx_records(company_info.domain)

        # Step 5: Email Permutations & Multi-Signal Verification
        enriched_leads: List[LeadRecord] = []
        c_suite_count = 0
        hr_count = 0
        tech_count = 0
        product_count = 0

        for lead in extracted_leads:
            if lead.role_category == RoleCategory.C_SUITE:
                c_suite_count += 1
            elif lead.role_category == RoleCategory.HR_TALENT:
                hr_count += 1
            elif lead.role_category == RoleCategory.TECH_LEAD:
                tech_count += 1
            elif lead.role_category == RoleCategory.PRODUCT:
                product_count += 1

            if company_info.domain:
                raw_perms = EmailPermutator.generate(
                    first_name=lead.first_name,
                    last_name=lead.last_name,
                    domain=company_info.domain,
                )
                verified_perms, best_email, best_confidence = EmailVerifier.verify_lead_permutations(
                    permutations=raw_perms,
                    domain=company_info.domain,
                    mx_info=mx_info,
                    check_smtp=self.check_smtp,
                )
                notes = []
                if mx_info and mx_info.has_mx:
                    notes.append(f"Mail provider: {mx_info.provider}")
                if mx_info and mx_info.is_catch_all:
                    notes.append("Domain is catch-all; deliverability score based on corporate pattern frequency")

                enriched_lead = lead.model_copy(
                    update={
                        "domain": company_info.domain,
                        "permutations": verified_perms,
                        "best_email": best_email,
                        "email_confidence": best_confidence,
                        "verification_notes": notes,
                    }
                )
                enriched_leads.append(enriched_lead)
            else:
                enriched_leads.append(lead)

        elapsed = round(time.time() - start_time, 2)
        return ProspectorResult(
            company=company_info,
            mx_info=mx_info,
            leads=enriched_leads,
            c_suite_count=c_suite_count,
            hr_count=hr_count,
            tech_count=tech_count,
            product_count=product_count,
            total_leads=len(enriched_leads),
            execution_time_sec=elapsed,
        )
