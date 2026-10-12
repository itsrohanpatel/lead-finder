"""Dedicated OSINT (Zero-Config) Scraper for Prospector-AI.

Discovers decision-makers (C-Suite & HR) via passive LinkedIn search indexing
(Yahoo/DuckDuckGo) with zero API keys, zero rate limits, and 100% free operation.

Usage:
    python scrape_osint.py sarvam.ai
    python scrape_osint.py stripe.com --roles c_suite hr_talent
    python scrape_osint.py --file companies.txt --output osint_leads.csv
"""

import argparse
import csv
import json
import os
import sys
import time
from typing import List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from prospector.models import RoleCategory, ProspectorResult
from prospector.pipeline import ProspectorPipeline
from prospector.cli import render_results_table

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(safe_box=True)


def parse_targets(input_arg: Optional[str], file_arg: Optional[str]) -> List[str]:
    """Extract list of target domains or company names."""
    targets = []
    if file_arg and os.path.exists(file_arg):
        with open(file_arg, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "\t" in line:
                        line = line.split("\t")[0].strip()
                    elif "," in line:
                        line = line.split(",")[0].strip()
                    targets.append(line)
    elif input_arg:
        targets.append(input_arg.strip())
    return targets


def export_leads_to_csv(leads_list: list, output_path: str, append: bool = False):
    """Write lead records into a CSV file."""
    file_exists = os.path.exists(output_path) and append
    mode = "a" if append else "w"
    with open(output_path, mode, newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "Company",
                "Domain",
                "Mail Provider",
                "Category",
                "Full Name",
                "First Name",
                "Last Name",
                "Job Title",
                "Location",
                "Best Email",
                "Confidence",
                "Alternative Emails",
                "LinkedIn Profile",
            ])
        for lead in leads_list:
            alt_emails = "; ".join([p.email for p in lead.permutations[1:4]]) if len(lead.permutations) > 1 else ""
            writer.writerow([
                lead.company_name or "",
                lead.domain or "",
                lead.mail_provider or "",
                lead.role_category.value if hasattr(lead.role_category, "value") else str(lead.role_category),
                lead.full_name,
                lead.first_name,
                lead.last_name,
                lead.job_title,
                lead.location or "",
                lead.best_email,
                f"{lead.confidence_score}%",
                alt_emails,
                lead.linkedin_url or "",
            ])


def main():
    parser = argparse.ArgumentParser(
        description="Zero-Config OSINT Scraper (Prospector-AI): 100% Free passive discovery without API keys"
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Target company domain or name (e.g. sarvam.ai or stripe.com)",
    )
    parser.add_argument(
        "--file",
        "-f",
        default=None,
        help="Path to file containing company domains or names (one per line)",
    )
    parser.add_argument(
        "--roles",
        "-r",
        nargs="+",
        choices=["c_suite", "hr_talent", "tech_lead", "product"],
        default=["c_suite", "hr_talent"],
        help="Target roles to discover (default: c_suite hr_talent)",
    )
    parser.add_argument(
        "--location",
        "-l",
        default=None,
        help="Optional location constraint (e.g. India, USA, London)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Path to export leads (CSV or JSON)",
    )
    parser.add_argument(
        "--max-leads",
        type=int,
        default=5,
        help="Maximum leads per role category (default: 5)",
    )
    parser.add_argument(
        "--no-smtp",
        action="store_true",
        default=True,
        help="Disable TCP port 25 SMTP verification (recommended for speed)",
    )

    args = parser.parse_args()

    targets = parse_targets(args.target, args.file)
    if not targets:
        console.print("[yellow]Please specify a target domain or file. Examples:[/yellow]")
        console.print("  python scrape_osint.py sarvam.ai")
        console.print("  python scrape_osint.py --file companies.txt --output leads.csv")
        sys.exit(1)

    target_roles = [RoleCategory(r) for r in args.roles]

    # Initialize pure OSINT pipeline with apollo_provider=None (guarantees zero external API dependency)
    pipeline = ProspectorPipeline(
        apollo_provider=None,
        check_smtp=not args.no_smtp,
        max_leads_per_role=args.max_leads,
    )

    all_leads = []
    start_total = time.time()

    console.print(f"[bold green]Starting Pure OSINT Scraper for {len(targets)} target(s)...[/bold green]")
    console.print("[dim]Backend: Zero-Config DuckDuckGo/Yahoo | API Keys Required: 0 | Cost: $0.00[/dim]\n")

    for idx, domain in enumerate(targets, 1):
        console.print(f"[{idx}/{len(targets)}] Searching OSINT indexes for [bold]{domain}[/bold]...")
        try:
            result = pipeline.run(
                domain,
                location=args.location,
                target_roles=target_roles,
            )
            render_results_table(result)
            all_leads.extend(result.leads)

            # Defensive file writing per company if CSV output is requested
            if args.output and args.output.endswith(".csv"):
                export_leads_to_csv(result.leads, args.output, append=True)

        except Exception as e:
            console.print(f"[red]Error scraping {domain}: {e}[/red]")

    elapsed = round(time.time() - start_total, 2)
    console.print(f"\n[bold green]OSINT Run Complete: Found {len(all_leads)} leads across {len(targets)} company(s) in {elapsed}s.[/bold green]")

    if args.output:
        if args.output.endswith(".json"):
            data = [
                {
                    "company": l.company_name,
                    "domain": l.domain,
                    "name": l.full_name,
                    "title": l.job_title,
                    "email": l.best_email,
                    "confidence": l.confidence_score,
                    "linkedin": l.linkedin_url,
                }
                for l in all_leads
            ]
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        console.print(f"[cyan]Results saved to: {args.output}[/cyan]")


if __name__ == "__main__":
    main()
