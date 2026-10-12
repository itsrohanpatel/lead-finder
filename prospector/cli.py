"""Rich CLI interface for Prospector-AI."""

import argparse
import csv
import json
import os
import sys
import re
import time
import logging
from typing import List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from prospector.models import RoleCategory, ProspectorResult
from prospector.pipeline import ProspectorPipeline
from prospector.apollo_provider import ApolloProvider

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
    counts_str = f"Found {result.total_leads} Prospects ({result.c_suite_count} C-Suite, {result.hr_count} HR/Talent) in {result.execution_time_sec}s"
    header_text.append(counts_str, style="green")

    console.print(Panel(header_text, title="Prospector-AI Lead Discovery", border_style="blue"))

    if not result.leads:
        console.print("[yellow]No leads matching criteria found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Category", style="dim", width=12)
    table.add_column("Full Name", style="bold white", width=18)
    table.add_column("Job Title", style="cyan", width=28)
    table.add_column("Location", style="yellow", width=16)
    table.add_column("Verified / Best Email", style="bold green", width=30)
    table.add_column("Confidence", justify="right", width=10)
    table.add_column("LinkedIn Profile", style="blue", overflow="fold")

    for lead in result.leads:
        if lead.role_category == RoleCategory.C_SUITE:
            cat_badge = "[bold red]C-Suite[/bold red]"
        elif lead.role_category == RoleCategory.HR_TALENT:
            cat_badge = "[bold blue]HR/Talent[/bold blue]"
        elif lead.role_category == RoleCategory.TECH_LEAD:
            cat_badge = "[bold yellow]Tech/Eng[/bold yellow]"
        elif lead.role_category == RoleCategory.PRODUCT:
            cat_badge = "[bold magenta]Product[/bold magenta]"
        else:
            cat_badge = "[dim]Other[/dim]"

        conf_pct = f"{int(lead.email_confidence * 100)}%"
        conf_color = "green" if lead.email_confidence >= 0.7 else ("yellow" if lead.email_confidence >= 0.4 else "red")
        best_email_str = lead.best_email or "[dim]No pattern[/dim]"
        loc_str = lead.location or "[dim]N/A[/dim]"

        table.add_row(
            cat_badge,
            lead.full_name,
            lead.job_title,
            loc_str,
            best_email_str,
            f"[{conf_color}]{conf_pct}[/{conf_color}]",
            lead.linkedin_url or "[dim]Website[/dim]",
        )

    console.print(table)


def generate_markdown_summary(result: ProspectorResult) -> str:
    """Generate a GitHub Flavored Markdown summary table for the result."""
    company_name = result.company.clean_name
    domain = result.company.domain or "N/A"
    provider = result.mx_info.provider if result.mx_info else "Unknown"
    catch_all = "Yes" if (result.mx_info and result.mx_info.is_catch_all) else "No"

    lines = [
        "### 🎯 Prospector-AI Lead Discovery Summary",
        "",
        f"- **Company**: {company_name}",
        f"- **Domain**: `{domain}`",
        f"- **Mail Server / Provider**: `{provider}` (Catch-All: {catch_all})",
        f"- **Total Prospects**: **{result.total_leads}** ({result.c_suite_count} C-Suite, {result.hr_count} HR/Talent, {result.tech_count} Tech, {result.product_count} Product) in {result.execution_time_sec}s",
        "",
    ]

    if not result.leads:
        lines.append("> ⚠️ **No leads matching the specified criteria were discovered.**")
        return "\n".join(lines) + "\n"

    lines.extend([
        "#### 👥 Discovered Prospects",
        "",
        "| Category | Full Name | Job Title | Location | Best Email | Confidence | LinkedIn |",
        "| :--- | :--- | :--- | :--- | :--- | :---: | :--- |",
    ])

    for lead in result.leads:
        cat_badge = {
            RoleCategory.C_SUITE: "🔴 **C-Suite**",
            RoleCategory.HR_TALENT: "🔵 **HR/Talent**",
            RoleCategory.TECH_LEAD: "🟡 **Tech/Eng**",
            RoleCategory.PRODUCT: "🟣 **Product**",
        }.get(lead.role_category, "⚪ **Other**")

        conf_pct = f"{int(lead.email_confidence * 100)}%"
        email_str = f"`{lead.best_email}`" if lead.best_email else "*N/A*"
        loc_str = lead.location or "*N/A*"
        li_link = f"[Profile]({lead.linkedin_url})" if lead.linkedin_url else "*Website*"

        lines.append(
            f"| {cat_badge} | **{lead.full_name}** | {lead.job_title} | {loc_str} | {email_str} | {conf_pct} | {li_link} |"
        )

    lines.append("")
    return "\n".join(lines)


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
            "Location",
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
                    lead.location or "",
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
        "--location",
        "-l",
        help="Filter leads by target geographic location (e.g. 'India', 'Bengaluru', 'Dubai', 'USA')",
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
        "--summary-file",
        help="Optional path to write GitHub Flavored Markdown summary (auto-detects GITHUB_STEP_SUMMARY)",
    )
    parser.add_argument(
        "--serper-key",
        help="Optional Serper.dev API key for Google SERP acceleration",
    )
    parser.add_argument(
        "--google-api-key",
        help="Optional Google Cloud API key for Custom Search JSON API",
    )
    parser.add_argument(
        "--google-cse-id",
        help="Optional Google Programmable Search Engine ID (cx)",
    )
    parser.add_argument(
        "--apify-token",
        help="Optional Apify API token for Google Search Scraper Actor fallback",
    )
    parser.add_argument(
        "--apollo-key",
        help="Optional Apollo.io API key for free direct B2B employee roster discovery",
    )
    parser.add_argument(
        "--departments",
        help="Optional comma-separated list of departments to target (e.g. c_suite,human_resources,engineering_technical,sales,marketing)",
    )
    parser.add_argument(
        "--seniorities",
        help="Optional comma-separated list of seniorities to target (e.g. founder,c_suite,owner,head,director,vp,manager)",
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

    departments = [d.strip().strip("'\"") for d in re.split(r"[,;]+", args.departments) if d.strip().strip("'\"")] if args.departments else None
    seniorities = [s.strip().strip("'\"") for s in re.split(r"[,;]+", args.seniorities) if s.strip().strip("'\"")] if args.seniorities else None

    # Resolve roles
    if args.roles == "c-suite":
        roles = [RoleCategory.C_SUITE]
    elif args.roles == "hr":
        roles = [RoleCategory.HR_TALENT]
    elif departments:
        roles = []
        dep_set = set(ApolloProvider.resolve_departments(departments)) if departments else set()
        if "c_suite" in dep_set:
            roles.append(RoleCategory.C_SUITE)
        if "human_resources" in dep_set:
            roles.append(RoleCategory.HR_TALENT)
        if "engineering_technical" in dep_set:
            roles.append(RoleCategory.TECH_LEAD)
        if "product" in dep_set:
            roles.append(RoleCategory.PRODUCT)
        if not roles:
            roles = [RoleCategory.OTHER]
    else:
        roles = [RoleCategory.C_SUITE, RoleCategory.HR_TALENT]

    # Parse company target(s) - supports comma, semicolon, or newline delimited domains
    raw_targets = [t.strip() for t in re.split(r"[,;\n\r]+", args.company) if t.strip()]
    if not raw_targets:
        console.print("[red]No valid target companies or domains provided.[/red]")
        return

    from prospector.search_engine import SearchEngine
    search_engine = SearchEngine(
        serper_api_key=args.serper_key,
        google_api_key=args.google_api_key,
        google_cse_id=args.google_cse_id,
        apify_api_token=args.apify_token,
    )
    pipeline = ProspectorPipeline(
        search_engine=search_engine,
        check_smtp=not args.no_smtp,
        max_leads_per_role=args.max_leads,
        apollo_api_key=args.apollo_key,
    )
    all_results: List[ProspectorResult] = []

    for idx, target in enumerate(raw_targets):
        if idx > 0:
            import time
            time.sleep(1.5)  # Polite pacing between multiple domains

        try:
            result = pipeline.run(
                target,
                target_roles=roles,
                location=args.location,
                departments=departments,
                seniorities=seniorities,
            )
            all_results.append(result)
            render_results_table(result)
        except Exception as e:
            logging.error(f"Error processing target '{target}': {e}")
            console.print(f"[bold red][!] Error processing {target}:[/bold red] {e}")

    if not all_results:
        return

    primary_name = all_results[0].company.clean_name.lower().replace(" ", "_") if all_results else "prospects"
    if args.format == "csv":
        out_path = args.output or (f"batch_leads.csv" if len(all_results) > 1 else f"{primary_name}_leads.csv")
        export_csv(all_results, out_path)
    elif args.format == "json":
        out_path = args.output or (f"batch_leads.json" if len(all_results) > 1 else f"{primary_name}_leads.json")
        export_json(all_results, out_path)

    # Write GitHub Flavored Markdown summary if requested or running in GitHub Actions
    summary_target = args.summary_file or os.getenv("GITHUB_STEP_SUMMARY")
    if summary_target:
        try:
            with open(summary_target, "a", encoding="utf-8") as f:
                for res in all_results:
                    summary_content = generate_markdown_summary(res)
                    f.write(summary_content + "\n\n")
            console.print(f"[bold green][+] Appended Markdown summary to:[/bold green] {summary_target}")
        except Exception as e:
            logging.warning(f"Failed writing markdown summary to {summary_target}: {e}")


if __name__ == "__main__":
    main()
