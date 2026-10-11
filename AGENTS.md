# Prospector-AI — Agent Rules & Operational Invariants

This file documents critical operational policies, regex safeguards, and verification invariants learned from real-world prospecting runs. All agents working on Prospector-AI must adhere to these rules.

---

## 1. Two-Tier Reporting Policy (Mandatory)

Whenever executing lead discovery for a company or domain:
1. **Tier 1 (Direct Code Output)**:
   - Output the direct tabular data produced by the code first (Full Name, Role Category, Extracted Job Title, Location, Best Email, Confidence Score, Mail Provider, LinkedIn URL).
   - Never mix unverified manual impressions directly into the programmatic output table.
2. **Tier 2 (OSINT & Delivery Verification)**:
   - Provide explicit, separate analysis of the extracted leads.
   - Categorize leads into **Verified Core Team** (confirmed current employment and location) vs. **SERP False Positives / Disqualified** (unrelated entities, keyword overlap from foreign domains, etc.).
   - Review mail server deliverability (e.g. Google Workspace, Microsoft 365, Zoho, or cPanel/Exim).

---

## 2. Company Name & Domain Resolution Invariants

* **Marketing Title Tag Stripping**:
  - Many SMEs have title tags like `"Branding Agency, Digital Marketing, Website & App Development in Ahmedabad – India"`.
  - Geographic terms (`india`, `usa`, `uk`, `global`, etc.) must always be included in `GENERIC_TERMS` in [`prospector/company_resolver.py`](file:///d:/Codinf%20projets/Prospector-ai/prospector/company_resolver.py) to prevent companies from being named `"India"`.
* **LinkedIn URL Fallback**:
  - When site title tags consist solely of generic keywords, derive the clean trade name from the official LinkedIn company slug (e.g., `linkedin.com/company/kumbh-design-inc` $\rightarrow$ `"Kumbh Design Inc"`).
* **Domain Brand Token Enforcement**:
  - Extract the domain Second-Level Domain (SLD) tokens to anchor extracted employer candidates, preventing common names from matching unrelated international conglomerates.

---

## 3. Metadata & Author Extraction Invariants

* **Reading-Time & Numeric Metadata Disqualification**:
  - CMS engines (WordPress, Webflow) emit `<meta name="twitter:data1" content="14 minutes">` for estimated reading time.
  - Never parse `twitter:data1` or arbitrary metadata as author names.
  - Reject any candidate author name containing numerical digits or time-related tokens (`"minute"`, `"read"`, `"time"`).

---

## 4. Headline & Role Parsing Invariants

* **Preposition Scoping**:
  - `at`, `@`, and `for` **always** introduce the entity/employer regardless of the preceding role (e.g., `Director at Acme`).
  - Negative lookbehinds (`(?<!\bhead\s)(?<!\bdirector\s)(?<!\bvp\s)`) must **only** constrain the preposition `\bof\b` to prevent capturing functional departments (e.g., `Director of Sales` capturing `Sales` as the company).
* **Multi-Segment & Pipe-Separated Headlines**:
  - Headlines like `Name | HR at Company | Human resources` must not capture the trailing sub-role (`"Human resources"`) as the employer name.
  - Always validate subsequent pipe fragments against `role_words` (`human`, `resources`, `assistant`, `accounting`, `admin`, `people`, `staff`, `operations`).
* **Trailing Geographic/City Invariant**:
  - Multi-segment headlines frequently terminate with a city or location (e.g., `Name - HR Manager(Group) - Kolkata`).
  - Never treat known city or location tokens (`LOCATION_WORDS`) as an employer candidate in Pattern 2 or Pattern 3 unless explicit entity indicators (`pvt`, `ltd`, `inc`) are present. Otherwise, the extractor will reject valid employees for not matching the company brand.


---

## 5. Batch Processing Guidelines

* **Defensive File Handling**:
  - Never hold a long-running CSV handle open across a 30+ company batch run (a user opening the file in Excel will crash the job with `PermissionError`).
  - Open, append, and flush per company.
* **Per-Target Exception Isolation**:
  - Wrap each company in a try-except block so DNS failures, network socket resets, or unreachable hosts log an error and continue the batch.
  - Maintain a live `summary.json` updated after each domain to guarantee zero data loss.

---

## 6. Live Browser Verification & Authentication Invariants

* **Session Preservation over Headless Tools**:
  - When inspecting social platforms with strict authentication/anti-bot protection (LinkedIn, Twitter/X), **always use `browser_subagent`** in the user's active browser session.
  - Never use headless MCP devtools (`chrome-devtools-mcp`) for authenticated platforms, as they lack login cookies and hit login authwalls.

---

## 7. Brand vs. Registered Entity Search Expansion

* **Industry & Corporate Suffix Generation**:
  - Consumer/D2C brand domains (e.g. `kisah.in`) often register entities under expanded trade names (e.g., `[Brand] Apparels`, `[Brand] Technologies`, `[Brand] Retail`).
  - Search dorks should leverage the company's verified LinkedIn slug and title variations to surface profiles where employees listed the formal corporate entity.

---

## 8. Search Engine Dorking Fidelity & Operator Invariants

* **Bing Search Dork Degradation**:
  - Never route passive LinkedIn OSINT dorks (`site:linkedin.com/in`) through Bing's public web endpoint without browser JS rendering, as Bing drops `site:` filters under headless requests and returns unrelated top-level domains.
* **Yahoo Backend Primacy**:
  - Maintain the Yahoo search backend (`ddgs.ENGINES['text'] = {'yahoo': ...}`) as the primary zero-config engine for passive LinkedIn indexing due to its strict adherence to `site:` scoping and rich snippet metadata.


