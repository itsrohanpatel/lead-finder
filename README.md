# 🎯 Prospector-AI

> **100% Free, Zero-Config, Serverless B2B Lead Generation & Decision-Maker Discovery Engine**  
> Discovers working **C-Suite executives (CEO, CTO, COO, CFO)** and **HR / Talent Acquisition leaders** from any company domain, name, or LinkedIn URL, verifies deliverability, and generates ranked email permutations.

---

## 📑 Table of Contents
1. [Why Prospector-AI? (Root-Level Research & Red Flags of Existing Tools)](#-why-prospector-ai)
2. [Key Architecture & Features](#-key-architecture--features)
3. [Quick Start](#-quick-start)
4. [CLI Usage & Formats (Table, CSV, JSON)](#-cli-usage--formats)
5. [Personal REST API (FastAPI)](#-personal-rest-api)
6. [Serverless Automation with GitHub Actions](#-serverless-automation-with-github-actions)
7. [Email Deliverability & Outbound Lead Gen Guide](#-email-deliverability--outbound-guide)
8. [Testing & Quality Assurance](#-testing--quality-assurance)

---

## 🔍 Why Prospector-AI?

### Evaluation of Existing Tools & Critical Red Flags
When B2B growth marketers and lead generation specialists search for tools to find executives and talent acquisition leads, they encounter commercial walled gardens or broken open-source scrapers. Here is what root-level research reveals:

| Category | Existing Tools | How They Work | Critical Red Flags & Why They Fail |
| :--- | :--- | :--- | :--- |
| **Commercial APIs** | Apollo.io, ZoomInfo, Hunter.io, Lusha | Proprietary scraped databases | **Cost & Paywalls:** Free tiers cap at 25-50 credits/month. Commercial subscriptions cost $50 to $300+/month. Databases are often stale (showing executives who left 6 months ago). |
| **Direct LinkedIn Scrapers** | `joeyism/linkedin_scraper`, `cullenwatson/StaffSpy` | Headless browsers (Selenium/Playwright) logging into LinkedIn accounts | **Account Bans & Checkpoints:** LinkedIn actively detects browser fingerprints, headless user-agents, and session cookies. Scraping accounts get banned or hit with SMS CAPTCHA within 10-50 profile views. |
| **Raw SMTP Checkers** | `MailPermute`, `MailScout` | Raw TCP socket connection on Port 25 to send `RCPT TO` | **Port 25 Blocks & Catch-All Traps:** Cloud providers (AWS, GCP, Vercel) block Port 25. Furthermore, Google Workspace and Microsoft 365 frequently run **Catch-All** configurations that return `250 OK` for bogus emails, causing massive false positives and high bounce rates if sent blindly. |

### How Prospector-AI Solves Every Single Red Flag:
1. **Passive OSINT Dorking (Zero LinkedIn Login / Zero Bans):** Queries search engine indexes (`site:linkedin.com/in ("CEO" OR "Founder") "at {company}"`) via DuckDuckGo (`ddgs`). LinkedIn servers are **never contacted directly**. No account needed, no cookies needed, zero risk of account ban.
2. **Multi-Signal Deliverability Matrix:** Combines DNS MX record verification, mail host fingerprinting (Google Workspace vs. Microsoft 365 vs. Zoho), high-entropy catch-all detection, statistical corporate pattern priors, and graceful socket fallback.
3. **100% Free & Serverless:** Runs completely free on your local machine, on a free serverless container (Hugging Face Spaces, Render), or via **GitHub Actions** (2,000 free runner minutes/month).

---

## 🚀 Key Architecture & Features

```
Input: domain (stripe.com), name ("Stripe"), or LinkedIn URL
  │
  ├── 1. Company Resolver: Normalizes company name, domain, and LinkedIn slug
  │
  ├── 2. Passive OSINT Harvester: Executes targeted search engine dorks for C-Suite & HR/TA
  │
  ├── 3. Lead Extractor: Parses title, cleans name, classifies into C_SUITE or HR_TALENT
  │
  ├── 4. MX Resolver & Fingerprinter: Queries DNS for MX records and detects mail provider
  │
  ├── 5. Catch-All & Deliverability Engine: Probes mailbox responses and handles port 25 filtering
  │
  └── 6. Email Permutator: Generates first.last, flast, first@domain with statistical confidence
        │
        └── Output: Terminal Table, CSV export, JSON export, or REST API response
```

---

## 💻 Quick Start

### 1. Installation
Clone this repository and install requirements:
```bash
git clone https://github.com/your-username/prospector-ai.git
cd prospector-ai
pip install -r requirements.txt
```

### 2. Run Instant Prospecting via CLI
```bash
# Find C-Suite and HR leaders for Stripe
python -m prospector.cli stripe.com

# Target only C-Suite executives
python -m prospector.cli stripe.com --roles c-suite

# Target only HR & Talent Acquisition professionals
python -m prospector.cli stripe.com --roles hr
```

---

## 📊 CLI Usage & Formats

### Output Formats:
#### 1. Rich Terminal Table (Default)
```bash
python -m prospector.cli stripe.com --roles c-suite --no-smtp
```
Outputs a colored table displaying:
- **Category:** C-Suite vs. HR/Talent badge
- **Full Name:** Clean person name
- **Job Title:** Verified role (e.g., Stripe CEO, President, Managing Director)
- **Verified / Best Email:** Generated high-probability email (e.g., `patrick.collison@stripe.com`)
- **Confidence Score:** Statistical deliverability rating
- **LinkedIn Profile:** Direct public profile link

#### 2. CSV Export (Ready for Outbound Spreadsheets)
```bash
python -m prospector.cli stripe.com --format csv --output stripe_leads.csv
```
Generates a structured spreadsheet containing:
`Company, Domain, Full Name, First Name, Last Name, Role Category, Job Title, Best Email, Email Confidence, LinkedIn URL, Mail Provider, Catch All`

#### 3. JSON Export (For Integrations & Webhooks)
```bash
python -m prospector.cli stripe.com --format json --output stripe_leads.json
```

---

## 🌐 Personal REST API

You can spin up your own local or hosted REST API powered by FastAPI:

```bash
uvicorn prospector.api:app --reload --port 8000
```
Interactive Swagger documentation is available at: `http://localhost:8000/docs`

### Sample Request:
```bash
curl -X POST "http://localhost:8000/api/prospect" \
  -H "Content-Type: application/json" \
  -d '{
    "company": "stripe.com",
    "roles": ["c_suite", "hr_talent"],
    "check_smtp": false,
    "max_leads": 10
  }'
```

---

## ⚡ Serverless Automation with GitHub Actions

You don't need to host any server. This repository includes a pre-configured GitHub Actions workflow in [`.github/workflows/prospector_action.yml`](file:///d:/Codinf%20projets/Prospector-ai/.github/workflows/prospector_action.yml).

### Option A: Trigger from GitHub UI
1. Go to your GitHub repository -> **Actions** tab.
2. Select **Prospector-AI Serverless Lead Harvester**.
3. Click **Run workflow**, enter the target company (e.g., `stripe.com`), choose roles, and click **Run**.
4. Once completed, download the enriched CSV/JSON directly from the **Artifacts** section!

### Option B: Trigger Programmatically via GitHub API (Personal Cloud API)
Trigger an automated prospecting job from anywhere with a single `curl` command using a GitHub Personal Access Token (PAT):

```bash
curl -X POST \
  -H "Accept: application/vnd.github.v3+json" \
  -H "Authorization: token YOUR_GITHUB_PAT" \
  https://api.github.com/repos/YOUR_USERNAME/Prospector-ai/actions/workflows/prospector_action.yml/dispatches \
  -d '{
    "ref": "main",
    "inputs": {
      "company": "stripe.com",
      "roles": "all",
      "output_format": "csv"
    }
  }'
```

---

## ✉️ Email Deliverability & Outbound Guide

As a lead generation professional sending cold emails:
1. **Beware of Catch-All Domains:** Prospector-AI automatically detects if a domain has catch-all enabled. On catch-all domains, `first.last@company.com` is almost always the corporate convention, but keep your sending volume gradual.
2. **Setup Domain Authentication:** Ensure your sending domain has active **SPF**, **DKIM**, and **DMARC** records before launching outreach.
3. **Warmup & Inboxes:** Send no more than 30-50 cold emails per mailbox per day.
4. **Role Angles:**
   - **For C-Suite (CEO/CTO/CFO):** Keep emails under 75 words. Focus on bottom-line impact, ROI, efficiency, or risk mitigation.
   - **For HR & Talent Acquisition:** Focus on time-to-hire, candidate pipeline quality, recruiter productivity, or candidate experience.

---

## 🧪 Testing & Quality Assurance

Prospector-AI includes a comprehensive unit and integration test suite:
```bash
python -m pytest
```
- Total tests: **21 passing tests** covering URL/company resolution, email permutation generation, mocked DNS & SMTP deliverability checks, lead parsing/deduplication, pipeline integration, and FastAPI endpoints.
