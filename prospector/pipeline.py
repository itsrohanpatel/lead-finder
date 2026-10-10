"""Master orchestrator pipeline for Prospector-AI."""

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
        target_roles: Optional[List[RoleCategory]] = None,
    ) -> ProspectorResult:
        """Execute prospecting workflow for a single company."""
        start_time = time.time()
        logger.info(f"Starting prospecting for: {company_input}")

        if target_roles is None:
            target_roles = [RoleCategory.C_SUITE, RoleCategory.HR_TALENT]

        # Step 1: Resolve Company Info
        company_info = CompanyResolver.resolve(company_input)

        # If domain missing, attempt to discover it via search engine
        if not company_info.domain:
            discovered_domain = self.search_engine.find_company_domain(company_info.clean_name)
            if discovered_domain:
                company_info.domain = discovered_domain
                logger.info(f"Discovered domain for {company_info.clean_name}: {discovered_domain}")

        # Step 2: Query Search Engine with Role-Specific Dorks
        raw_search_items = []
        name = company_info.clean_name

        # Build smart company name variations (e.g. tigihr -> "tigihr" OR "TIGI HR")
        name_variations = [f'"{name}"']
        name_lower = name.lower()
        if name_lower.endswith("hrm") and len(name) > 3:
            base = name[:-3].strip()
            name_variations.append(f'"{base.upper()} HR"')
            name_variations.append(f'"{base.upper()} HRM"')
            name_variations.append(f'"{base.upper()} HR Management"')
        elif name_lower.endswith("hr") and len(name) > 2:
            base = name[:-2].strip()
            name_variations.append(f'"{base.upper()} HR"')
            name_variations.append(f'"{base.title()} HR"')
        elif name_lower.endswith("ai") and len(name) > 2:
            base = name[:-2].strip()
            name_variations.append(f'"{base.upper()} AI"')
            name_variations.append(f'"{base.title()} AI"')
        elif name_lower.endswith("tech") and len(name) > 4:
            base = name[:-4].strip()
            name_variations.append(f'"{base.title()} Tech"')

        # Deduplicate variations
        seen_vars = set()
        clean_vars = []
        for v in name_variations:
            if v.lower() not in seen_vars:
                seen_vars.add(v.lower())
                clean_vars.append(v)

        company_query_term = " OR ".join(clean_vars)
        if len(clean_vars) > 1:
            company_query_term = f"({company_query_term})"

        if RoleCategory.C_SUITE in target_roles:
            c_suite_dork = f'site:linkedin.com/in ("CEO" OR "Founder" OR "Co-Founder" OR "Chief" OR "Director" OR "CTO" OR "COO" OR "CFO") {company_query_term}'
            c_results = self.search_engine.query(c_suite_dork, max_results=self.max_leads_per_role)
            if not c_results:
                # Resilient fallback: simplified keywords without complex boolean grouping
                fallback_dork = f'site:linkedin.com/in {name} CEO OR Founder'
                c_results = self.search_engine.query(fallback_dork, max_results=self.max_leads_per_role)
            raw_search_items.extend(c_results)

        if RoleCategory.HR_TALENT in target_roles:
            hr_dork = f'site:linkedin.com/in ("Talent Acquisition" OR "Head of Talent" OR "Recruiter" OR "HR" OR "People Ops") {company_query_term}'
            hr_results = self.search_engine.query(hr_dork, max_results=self.max_leads_per_role)
            if not hr_results:
                # Resilient fallback: simplified keywords
                fallback_dork = f'site:linkedin.com/in {name} Talent OR Recruiter OR HR'
                hr_results = self.search_engine.query(fallback_dork, max_results=self.max_leads_per_role)
            raw_search_items.extend(hr_results)

        # Step 3: Extract Leads
        extracted_leads = LeadExtractor.extract_leads(
            search_results=raw_search_items,
            company_name=company_info.clean_name,
            domain=company_info.domain,
            target_roles=target_roles,
        )

        # Step 4: MX Lookup & Fingerprinting
        mx_info: Optional[MXInfo] = None
        if company_info.domain:
            mx_info = EmailVerifier.lookup_mx_records(company_info.domain)

        # Step 5: Email Permutations & Multi-Signal Verification
        enriched_leads: List[LeadRecord] = []
        c_suite_count = 0
        hr_count = 0

        for lead in extracted_leads:
            if lead.role_category == RoleCategory.C_SUITE:
                c_suite_count += 1
            elif lead.role_category == RoleCategory.HR_TALENT:
                hr_count += 1

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
            total_leads=len(enriched_leads),
            execution_time_sec=elapsed,
        )
