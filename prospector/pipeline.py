import os
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
from prospector.apollo_provider import ApolloProvider

logger = logging.getLogger(__name__)


class ProspectorPipeline:
    """End-to-end prospecting pipeline."""

    def __init__(
        self,
        search_engine: Optional[SearchEngine] = None,
        check_smtp: bool = True,
        max_leads_per_role: int = 10,
        apollo_provider: Optional[ApolloProvider] = None,
        apollo_api_key: Optional[str] = None,
    ):
        self.search_engine = search_engine or SearchEngine()
        self.check_smtp = check_smtp
        self.max_leads_per_role = max_leads_per_role

        if apollo_provider:
            self.apollo_provider = apollo_provider
        else:
            candidate_provider = ApolloProvider(api_key=apollo_api_key)
            if candidate_provider.api_keys:
                self.apollo_provider = candidate_provider
            else:
                self.apollo_provider = None

    def run(
        self,
        company_input: str,
        company_name_hint: Optional[str] = None,
        target_roles: Optional[List[RoleCategory]] = None,
        location: Optional[str] = None,
        departments: Optional[List[str]] = None,
        seniorities: Optional[List[str]] = None,
    ) -> ProspectorResult:
        """Execute prospecting workflow for a single company."""
        start_time = time.time()
        logger.info(f"Starting prospecting for: {company_input}")

        if target_roles is None:
            target_roles = [RoleCategory.C_SUITE, RoleCategory.HR_TALENT]

        # Align target_roles with explicitly requested departments
        if departments:
            resolved_deps = self.apollo_provider.resolve_departments(departments) if self.apollo_provider else [d.lower().strip() for d in departments]
            if resolved_deps and target_roles == [RoleCategory.C_SUITE, RoleCategory.HR_TALENT]:
                derived_roles = []
                if any(d in resolved_deps for d in ("c_suite", "csuite", "executive", "exec")):
                    derived_roles.append(RoleCategory.C_SUITE)
                if any(d in resolved_deps for d in ("human_resources", "hr", "talent", "recruiting", "people")):
                    derived_roles.append(RoleCategory.HR_TALENT)
                if any(d in resolved_deps for d in ("engineering_technical", "engineering", "tech", "dev", "it", "information_technology")):
                    derived_roles.append(RoleCategory.TECH_LEAD)
                if any(d in resolved_deps for d in ("product", "design")):
                    derived_roles.append(RoleCategory.PRODUCT)
                if derived_roles:
                    target_roles = derived_roles

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

        # Step 2.5: Apollo Direct Roster Acceleration & Search-Engine Unmasking
        skip_search_dorks = False
        if self.apollo_provider and company_info.domain:
            apollo_deps = self.apollo_provider.resolve_departments(departments)
            apollo_sens = self.apollo_provider.resolve_seniorities(seniorities)

            # If no custom departments or seniorities specified, default to unified query for target_roles
            if not apollo_deps and not apollo_sens:
                if RoleCategory.C_SUITE in target_roles and RoleCategory.HR_TALENT in target_roles:
                    apollo_deps = ["c_suite", "human_resources"]
                    apollo_sens = ["founder", "c_suite", "owner", "director", "vp", "head", "manager"]
                elif RoleCategory.C_SUITE in target_roles:
                    apollo_deps = ["c_suite"]
                    apollo_sens = ["founder", "c_suite", "owner", "director", "vp", "head"]
                elif RoleCategory.HR_TALENT in target_roles:
                    apollo_deps = ["human_resources"]
                    apollo_sens = ["head", "director", "vp", "manager", "senior", "entry"]

            apollo_candidates = self.apollo_provider.search_employees(
                website=company_info.domain,
                departments=apollo_deps,
                seniority=apollo_sens,
                max_records=self.max_leads_per_role * 2,
            )

            # Targeted title expansion query: many SME/startup recruiters & leaders have deps: None in Apollo
            if apollo_deps and len(apollo_candidates) < self.max_leads_per_role * 2:
                target_titles = []
                for d in apollo_deps:
                    if d in self.apollo_provider.DEPARTMENT_TITLES_MAP:
                        target_titles.extend(self.apollo_provider.DEPARTMENT_TITLES_MAP[d])
                if target_titles:
                    title_cands = self.apollo_provider.search_employees(
                        website=company_info.domain,
                        titles=target_titles[:15],
                        seniority=apollo_sens,
                        max_records=self.max_leads_per_role * 2,
                    )
                    seen_cand_keys = {c.get("linkedin_url") or c.get("name") for c in apollo_candidates}
                    for tc in title_cands:
                        key = tc.get("linkedin_url") or tc.get("name")
                        if key and key not in seen_cand_keys:
                            seen_cand_keys.add(key)
                            apollo_candidates.append(tc)

            if apollo_candidates:
                logger.info(f"Apollo returned {len(apollo_candidates)} raw candidate records for {company_info.domain}")
                unmasked = self.apollo_provider.unmask_candidates(
                    candidates=apollo_candidates,
                    search_engine=self.search_engine,
                    company_name=company_info.clean_name,
                    max_to_unmask=self.max_leads_per_role * 2,
                )

                for cand in unmasked:
                    full_name = cand.get("name", "")
                    fname = cand.get("first_name", "")
                    lname = cand.get("last_name", "")

                    if not fname or not lname or "*" in lname:
                        fname, lname = LeadExtractor.split_name(full_name)

                    if fname and lname and "*" not in lname:
                        name_key = f"{fname.lower()} {lname.lower()}"
                        url = cand.get("linkedin_url")
                        if name_key not in seen_names and (not url or url not in seen_urls):
                            title = cand.get("title", "")
                            role_cat = LeadExtractor.categorize_role(title)

                            # Candidate must strictly match requested departments or target roles
                            if departments:
                                matches_req = LeadExtractor.matches_departments(title, departments)
                            else:
                                matches_req = role_cat in target_roles

                            if matches_req:
                                lead_rec = LeadRecord(
                                    full_name=f"{fname} {lname}",
                                    first_name=fname,
                                    last_name=lname,
                                    job_title=title or "Decision Maker",
                                    role_category=role_cat,
                                    location=cand.get("location") or location,
                                    linkedin_url=url,
                                    company_name=company_info.clean_name,
                                    domain=company_info.domain,
                                )
                                extracted_leads.append(lead_rec)
                                seen_names.add(name_key)
                                if url:
                                    seen_urls.add(url)

                # Check if Apollo satisfied requested personas
                if departments:
                    if len(extracted_leads) >= min(self.max_leads_per_role, 1):
                        logger.info(f"Apollo satisfied requested department personas ({len(extracted_leads)} leads). Skipping broad search dorks.")
                        skip_search_dorks = True
                else:
                    apollo_c_suite = sum(1 for l in extracted_leads if l.role_category == RoleCategory.C_SUITE)
                    apollo_hr = sum(1 for l in extracted_leads if l.role_category == RoleCategory.HR_TALENT)

                    c_suite_ok = (RoleCategory.C_SUITE not in target_roles) or (apollo_c_suite >= min(self.max_leads_per_role, 1))
                    hr_ok = (RoleCategory.HR_TALENT not in target_roles) or (apollo_hr >= min(self.max_leads_per_role, 1))

                    if c_suite_ok and hr_ok and len(extracted_leads) >= len(target_roles):
                        logger.info(f"Apollo satisfied requested personas ({apollo_c_suite} C-Suite, {apollo_hr} HR, total: {len(extracted_leads)}). Skipping broad search dorks.")
                        skip_search_dorks = True

        # Step 3: Query Search Engine with Role-Specific Dorks (if needed)
        raw_search_items = []
        if not skip_search_dorks:
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
                    clean_slug = raw_slug.replace("-", " ").replace("_", " ").strip()
                    slug_words = [w for w in clean_slug.split() if w.lower() not in {"pvt", "ltd", "inc", "llc", "corp", "company", "official"}]
                    if slug_words:
                        slug_title = " ".join(slug_words).title()
                        if slug_title.lower() not in [s.lower() for s in search_terms]:
                            search_terms.append(slug_title)

                    # Universal compound unhyphenated slug separation (e.g. upmanplacements -> Upman Placements)
                    if domain_sld and raw_slug.startswith(domain_sld) and len(raw_slug) > len(domain_sld):
                        remainder = raw_slug[len(domain_sld):].strip()
                        remainder_words = [w for w in remainder.split() if w.lower() not in {"pvt", "ltd", "inc", "llc", "corp", "company", "official"}]
                        if remainder_words:
                            compound_title = f"{domain_sld} {' '.join(remainder_words)}".title()
                            if compound_title.lower() not in [s.lower() for s in search_terms]:
                                search_terms.append(compound_title)

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

            # Deduplicate search terms case-insensitively and prioritize high-signal descriptive terms
            unique_terms = []
            seen_lower = set()
            for t in search_terms:
                t_clean = t.strip()
                if t_clean.lower() not in seen_lower:
                    seen_lower.add(t_clean.lower())
                    unique_terms.append(t_clean)

            # Prioritize multi-word descriptive trade names over single-word acronyms
            unique_terms.sort(key=lambda s: len(s.split()), reverse=True)

            # Execute queries per target role and term (up to 3 unique terms, case-normalized)
            seen_query_terms = set()
            for idx, term in enumerate(unique_terms[:3]):
                t_clean = term.strip()
                if t_clean.lower() in seen_query_terms:
                    continue
                seen_query_terms.add(t_clean.lower())

                # Adaptive Saturation Gate: If primary high-signal trade name already yielded sufficient
                # verified leads, skip secondary low-signal acronym loops to maximize throughput
                if idx > 0 and len(raw_search_items) >= 12:
                    interim_leads = LeadExtractor.extract_leads(
                        search_results=raw_search_items,
                        company_name=company_info.clean_name,
                        domain=company_info.domain,
                        target_roles=target_roles,
                        location=location,
                    )
                    if len(interim_leads) >= 5:
                        logger.info(
                            f"Adaptive Saturation Gate: {len(interim_leads)} verified leads identified from '{unique_terms[0]}'. "
                            f"Skipping redundant secondary term loops."
                        )
                        break

                loc_suffix = ""
                if location:
                    loc_clean = location.strip()
                    if loc_clean.lower() in ["pan india", "pan-india", "all india"]:
                        loc_suffix = "India"
                    else:
                        loc_suffix = loc_clean

                term_q = t_clean

                # Step 3a: Query base company employee pool to capture all indexed staff
                base_dork = f"site:linkedin.com/in {term_q} {loc_suffix}".strip()
                base_results = self.search_engine.query(base_dork, max_results=self.max_leads_per_role)
                if base_results:
                    raw_search_items.extend(base_results)

                c_kws = ["CEO", "Founder", "Director"] if idx == 0 else ["CEO", "Founder"]
                hr_kws = ["HR", "Recruiting", "Recruiter", "Talent", "People", "Hiring"] if idx == 0 else ["HR", "Recruiter", "Talent"]

                if RoleCategory.C_SUITE in target_roles:
                    for role_kw in c_kws:
                        dork = f"site:linkedin.com/in {term_q} {role_kw}"
                        results = self.search_engine.query(dork, max_results=self.max_leads_per_role)
                        if results:
                            raw_search_items.extend(results)

                if RoleCategory.HR_TALENT in target_roles:
                    for role_kw in hr_kws:
                        dork = f"site:linkedin.com/in {term_q} {role_kw} {loc_suffix}".strip()
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
