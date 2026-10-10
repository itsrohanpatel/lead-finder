"""Rich CLI interface for Prospector-AI."""

import argparse
import csv
import json
import sys
import logging
from typing import List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from prospector.models import RoleCategory, ProspectorResult
from prospector.pipeline import ProspectorPipeline

# Reconfigure Windows stdout to UTF-8 if needed to avoid charmap encoding errors
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(safe_box=True)


def render_results_table(result: ProspectorResult) -> None:
    """Render leads into an aesthetic, color-coded terminal table."""
    company_name = result.company.clean_name
    domain = result.company.domain or "N/A"
    provider = result.mx_info.provider if result.mx_info else "Unknown"

    header_text = Text()
    header_text.append(f"Company: {company_name} | Domain: {domain} | Mail Provider: {provider}\n", style="bold cyan")
    header_text.append(f"Found {result.total_leads} Prospects ({result.c_suite_count} C-Suite, {result.hr_count} HR/Talent) in {result.execution_time_sec}s", style="green")

    console.print(Panel(header_text, title="Prospector-AI Lead Discovery", border_style="blue"))

    if not result.leads:
        console.print("[yellow]No leads matching criteria found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Category", style="dim", width=12)
    table.add_column("Full Name", style="bold white", width=20)
    table.add_column("Job Title", style="cyan", width=30)
    table.add_column("Verified / Best Email", style="bold green", width=32)
    table.add_column("Confidence", justify="right", width=12)
    table.add_column("LinkedIn Profile", style="blue", overflow="fold")

    for lead in result.leads:
        cat_badge = "[bold red]C-Suite[/bold red]" if lead.role_category == RoleCategory.C_SUITE else "[bold blue]HR/Talent[/bold blue]"
        conf_pct = f"{int(lead.email_confidence * 100)}%"
        conf_color = "green" if lead.email_confidence >= 0.7 else ("yellow" if lead.email_confidence >= 0.4 else "red")
        best_email_str = lead.best_email or "[dim]No pattern[/dim]"

        table.add_row(
            cat_badge,
            lead.full_name,
            lead.job_title,
            best_email_str,
            f"[{conf_color}]{conf_pct}[/{conf_color}]",
            lead.linkedin_url or "[dim]Website[/dim]",
        )

    console.print(table)


def export_csv(results: List[ProspectorResult], filepath: str) -> None:
    """Export leads across all processed companies to CSV."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Company",
            "Domain",
            "Full Name",
            "First Name",
            "Last Name",
            "Role Category",
            "Job Title",
            "Best Email",
            "Email Confidence",
            "LinkedIn URL",
            "Mail Provider",
            "Catch All",
        ])
        for r in results:
            provider = r.mx_info.provider if r.mx_info else ""
            is_catch_all = r.mx_info.is_catch_all if r.mx_info else False
            for lead in r.leads:
                writer.writerow([
                    r.company.clean_name,
                    r.company.domain or "",
                    lead.full_name,
                    lead.first_name,
                    lead.last_name,
                    lead.role_category.value,
                    lead.job_title,
                    lead.best_email or "",
                    f"{lead.email_confidence:.2f}",
                    lead.linkedin_url,
                    provider,
                    "Yes" if is_catch_all else "No",
                ])
    console.print(f"[bold green][+] Exported leads to CSV:[/bold green] {filepath}")


def export_json(results: List[ProspectorResult], filepath: str) -> None:
    """Export leads to JSON."""
    data = [r.model_dump() for r in results]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    console.print(f"[bold green][+] Exported leads to JSON:[/bold green] {filepath}")


def main() -> None:
    """Entry point for CLI execution."""
    parser = argparse.ArgumentParser(
        description="Prospector-AI: Free Serverless Lead Discovery for C-Suite & HR Talent"
    )
    parser.add_argument(
        "company",
        help="Target company domain (e.g. stripe.com), name ('Stripe'), or LinkedIn URL",
    )
    parser.add_argument(
        "--roles",
        choices=["all", "c-suite", "hr"],
        default="all",
        help="Filter target personas (default: all)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "csv", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path when format is csv or json",
    )
    parser.add_argument(
        "--no-smtp",
        action="store_true",
        help="Disable raw SMTP socket verification (useful in environments where port 25 is blocked)",
    )
    parser.add_argument(
        "--max-leads",
        type=int,
        default=10,
        help="Max leads per role category (default: 10)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Resolve roles
    if args.roles == "c-suite":
        roles = [RoleCategory.C_SUITE]
    elif args.roles == "hr":
        roles = [RoleCategory.HR_TALENT]
    else:
        roles = [RoleCategory.C_SUITE, RoleCategory.HR_TALENT]

    pipeline = ProspectorPipeline(check_smtp=not args.no_smtp, max_leads_per_role=args.max_leads)
    result = pipeline.run(args.company, target_roles=roles)

    if args.format == "table":
        render_results_table(result)
    elif args.format == "csv":
        out_path = args.output or f"{result.company.clean_name.lower()}_leads.csv"
        export_csv([result], out_path)
    elif args.format == "json":
        out_path = args.output or f"{result.company.clean_name.lower()}_leads.json"
        export_json([result], out_path)


if __name__ == "__main__":
    main()
