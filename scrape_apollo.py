"""Dedicated Apollo Scraper for Prospector-AI.

Queries Apollo.io for company employee rosters, filters by department and seniority,
automatically unmasks obfuscated last names using passive OSINT, and verifies email
deliverability with MX records.

Usage:
    python scrape_apollo.py sarvam.ai
    python scrape_apollo.py sarvam.ai --departments c_suite,hr --seniorities founder,head
    python scrape_apollo.py --file companies.txt --output apollo_leads.csv
"""

import argparse
import csv
import json
import os
import sys
import time
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from prospector.models import RoleCategory, ProspectorResult
from prospector.pipeline import ProspectorPipeline
from prospector.apollo_provider import ApolloProvider
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
        description="Apollo Scraper (Prospector-AI): Extract verified rosters & unmask full names"
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Target company domain (e.g. sarvam.ai or stripe.com)",
    )
    parser.add_argument(
        "--file",
        "-f",
        default=None,
        help="Path to file containing company domains (one per line)",
    )
    parser.add_argument(
        "--apollo-key",
        default=None,
        help="Apollo API key (default: read from APOLLO_API_KEY env var / .env)",
    )
    parser.add_argument(
        "--departments",
        "-d",
        default="c_suite,hr",
        help="Comma-separated departments (e.g. c_suite,hr,engineering,sales)",
    )
    parser.add_argument(
        "--seniorities",
        "-s",
        default="founder,c_suite,head,manager",
        help="Comma-separated seniorities (e.g. founder,c_suite,head,manager)",
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
        default=10,
        help="Maximum leads to retrieve per company (default: 10)",
    )
    parser.add_argument(
        "--no-smtp",
        action="store_true",
        default=True,
        help="Disable TCP port 25 SMTP verification (recommended for speed)",
    )

    args = parser.parse_args()

    apollo_key = args.apollo_key or os.getenv("APOLLO_API_KEY")
    if not apollo_key:
        console.print(Panel(
            "[bold red]Error: No Apollo API key provided![/bold red]\n\n"
            "You can provide your key in any of these ways:\n"
            "1. Create a [bold cyan].env[/bold cyan] file in this directory with:\n"
            "   [green]APOLLO_API_KEY=your_key_here[/green]\n"
            "2. Pass it via command line argument:\n"
            "   [yellow]python scrape_apollo.py sarvam.ai --apollo-key your_key_here[/yellow]\n"
            "3. Or set it in your system environment:\n"
            "   [dim]set APOLLO_API_KEY=your_key_here[/dim]",
            title="Apollo Authentication Required",
            border_style="red"
        ))
        sys.exit(1)

    targets = parse_targets(args.target, args.file)
    if not targets:
        console.print("[yellow]Please specify a target domain or file. Examples:[/yellow]")
        console.print("  python scrape_apollo.py sarvam.ai")
        console.print("  python scrape_apollo.py --file companies.txt --output leads.csv")
        sys.exit(1)

    deps = [d.strip() for d in args.departments.split(",") if d.strip()]
    sens = [s.strip() for s in args.seniorities.split(",") if s.strip()]

    apollo_provider = ApolloProvider(api_key=apollo_key)
    pipeline = ProspectorPipeline(
        apollo_provider=apollo_provider,
        check_smtp=not args.no_smtp,
        max_leads_per_role=args.max_leads,
    )

    all_leads = []
    start_total = time.time()

    console.print(f"[bold cyan]Starting Apollo Scraper for {len(targets)} target(s)...[/bold cyan]")
    console.print(f"[dim]Departments: {deps} | Seniorities: {sens}[/dim]\n")

    for idx, domain in enumerate(targets, 1):
        console.print(f"[{idx}/{len(targets)}] Scraping Apollo roster for [bold]{domain}[/bold]...")
        try:
            result = pipeline.run(
                domain,
                departments=deps,
                seniorities=sens,
            )
            render_results_table(result)
            all_leads.extend(result.leads)

            # Defensive file writing per company if CSV output is requested
            if args.output and args.output.endswith(".csv"):
                export_leads_to_csv(result.leads, args.output, append=True)

        except Exception as e:
            console.print(f"[red]Error scraping {domain}: {e}[/red]")

    elapsed = round(time.time() - start_total, 2)
    console.print(f"\n[bold green]Apollo Run Complete: Found {len(all_leads)} leads across {len(targets)} company(s) in {elapsed}s.[/bold green]")

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
