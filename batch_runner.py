"""Batch runner for Prospector-AI.

Processes lists of domains or company names from a file or command-line arguments,
extracting verified leads and exporting them incrementally to CSV and JSON.
"""

import os
import sys
import csv
import json
import time
import argparse
import logging
from typing import List, Tuple, Optional

from prospector.pipeline import ProspectorPipeline
from prospector.models import RoleCategory

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("batch_runner")


def parse_input_file(filepath: str) -> List[Tuple[str, Optional[str]]]:
    """Parse company targets from a text file, CSV, or line-delimited list."""
    items: List[Tuple[str, Optional[str]]] = []
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Batch input file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Support TSV/CSV format: "Name,URL" or "Name\tURL"
            if "\t" in line:
                parts = line.split("\t", 1)
                items.append((parts[0].strip(), parts[1].strip()))
            elif "," in line:
                parts = line.split(",", 1)
                items.append((parts[0].strip(), parts[1].strip()))
            else:
                items.append((line, None))

    return items


def main():
    parser = argparse.ArgumentParser(
        description="Prospector-AI Batch Runner: Discover decision-makers for multiple companies"
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        default=None,
        help="Path to file containing company domains or names (one per line, or CSV/TSV)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="batch_prospects.csv",
        help="Output CSV file path (default: batch_prospects.csv)",
    )
    parser.add_argument(
        "--summary",
        "-s",
        default="batch_summary.json",
        help="Output JSON summary path (default: batch_summary.json)",
    )
    parser.add_argument(
        "--roles",
        nargs="+",
        choices=["c_suite", "hr_talent", "tech_lead", "product"],
        default=["c_suite", "hr_talent"],
        help="Target roles to discover (default: c_suite hr_talent)",
    )
    parser.add_argument(
        "--check-smtp",
        action="store_true",
        help="Enable TCP port 25 SMTP handshake verification (default: False for batch)",
    )
    parser.add_argument(
        "--max-leads",
        type=int,
        default=5,
        help="Maximum leads per role category (default: 5)",
    )

    args = parser.parse_args()

    if not args.input_file:
        print("Usage: python batch_runner.py <targets.txt> [--output results.csv] [--roles c_suite hr_talent]")
        print("Example targets.txt format:")
        print("  stripe.com")
        print("  kumbhdesign.com")
        print("  Decentro\thttps://decentro.tech")
        return

    items = parse_input_file(args.input_file)
    if not items:
        print(f"No valid targets found in {args.input_file}")
        return

    # Deduplicate targets while preserving order
    seen = set()
    deduped_items = []
    for name, url in items:
        key = (url or name).lower().strip()
        if key not in seen:
            seen.add(key)
            deduped_items.append((name, url))

    # Convert role strings to RoleCategory enum
    target_roles = [RoleCategory(r) for r in args.roles]

    # Initialize CSV header if not already present
    csv_exists = os.path.exists(args.output)
    if not csv_exists:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Company Input",
                "Resolved Company",
                "Domain",
                "Mail Provider",
                "Category",
                "Full Name",
                "Job Title",
                "Location",
                "Best Email",
                "Confidence",
                "Alternative Emails",
                "LinkedIn Profile",
                "Catch All",
            ])

    pipeline = ProspectorPipeline(check_smtp=args.check_smtp, max_leads_per_role=args.max_leads)
    total_leads_count = 0
    results_summary = []

    print(f"=== Starting Prospector Batch Run for {len(deduped_items)} Companies ===", flush=True)
    print(f"Output CSV: {args.output}", flush=True)
    start_all = time.time()

    for idx, (company_name, company_url) in enumerate(deduped_items, 1):
        target_input = company_url if company_url else company_name
        print(f"\n[{idx}/{len(deduped_items)}] Processing: {company_name} ({target_input})...", flush=True)

        try:
            res = pipeline.run(
                target_input,
                company_name_hint=company_name if company_url else None,
                target_roles=target_roles,
            )
            leads_found = len(res.leads)
            total_leads_count += leads_found
            provider = res.mx_info.provider if res.mx_info else "Unknown"
            catch_all = "Yes" if (res.mx_info and res.mx_info.is_catch_all) else "No"

            print(f"    -> Resolved: {res.company.clean_name} ({res.company.domain or 'No domain'}) | Provider: {provider} | Leads: {leads_found}", flush=True)
            for l in res.leads:
                print(f"       * [{l.role_category.value}] {l.full_name} ({l.job_title}) [{l.location or 'N/A'}] -> {l.best_email}", flush=True)

            # Defensive file handling: open, append, close per company
            with open(args.output, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for l in res.leads:
                    alt_emails = "; ".join([p.email for p in l.permutations[1:4]]) if len(l.permutations) > 1 else ""
                    writer.writerow([
                        company_name,
                        res.company.clean_name,
                        res.company.domain or "",
                        provider,
                        l.role_category.value,
                        l.full_name,
                        l.job_title,
                        l.location or "",
                        l.best_email or "",
                        f"{int(l.email_confidence * 100)}%",
                        alt_emails,
                        l.linkedin_url or "",
                        catch_all,
                    ])

            results_summary.append({
                "company_input": company_name,
                "resolved_name": res.company.clean_name,
                "domain": res.company.domain,
                "provider": provider,
                "leads_count": leads_found,
                "leads": [
                    {
                        "name": l.full_name,
                        "title": l.job_title,
                        "category": l.role_category.value,
                        "location": l.location,
                        "email": l.best_email,
                        "confidence": l.email_confidence,
                        "linkedin": l.linkedin_url,
                    }
                    for l in res.leads
                ],
            })

        except Exception as exc:
            logger.error(f"Error processing {company_name}: {exc}")
            print(f"    -> Error: {exc}", flush=True)
            results_summary.append({
                "company_input": company_name,
                "error": str(exc),
                "leads_count": 0,
                "leads": [],
            })

        # Save live summary
        with open(args.summary, "w", encoding="utf-8") as f:
            json.dump(results_summary, f, indent=2)

        time.sleep(0.5)

    total_time = round(time.time() - start_all, 2)
    print(f"\n=== Batch Run Complete! ===", flush=True)
    print(f"Total Companies Processed: {len(deduped_items)}", flush=True)
    print(f"Total Leads Discovered: {total_leads_count}", flush=True)
    print(f"Total Time: {total_time}s", flush=True)
    print(f"CSV saved to: {args.output}", flush=True)
    print(f"Summary saved to: {args.summary}", flush=True)


if __name__ == "__main__":
    main()
