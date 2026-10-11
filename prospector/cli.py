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
    counts_str = f"Found {result.total_leads} Prospects ({result.c_suite_count} C-Suite, {result.hr_count} HR/Talent"
    if result.tech_count > 0:
        counts_str += f", {result.tech_count} Tech"
    if result.product_count > 0:
        counts_str += f", {result.product_count} Product"
    counts_str += f") in {result.execution_time_sec}s"
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
        choices=["all", "c-suite", "hr", "tech", "product"],
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
    elif args.roles == "tech":
        roles = [RoleCategory.TECH_LEAD]
    elif args.roles == "product":
        roles = [RoleCategory.PRODUCT]
    else:
        roles = [RoleCategory.C_SUITE, RoleCategory.HR_TALENT, RoleCategory.TECH_LEAD, RoleCategory.PRODUCT]

    pipeline = ProspectorPipeline(check_smtp=not args.no_smtp, max_leads_per_role=args.max_leads)
    result = pipeline.run(args.company, target_roles=roles, location=args.location)

    # Always render results table in console for immediate terminal visibility
    render_results_table(result)

    if args.format == "csv":
        out_path = args.output or f"{result.company.clean_name.lower()}_leads.csv"
        export_csv([result], out_path)
    elif args.format == "json":
        out_path = args.output or f"{result.company.clean_name.lower()}_leads.json"
        export_json([result], out_path)

    # Write GitHub Flavored Markdown summary if requested or running in GitHub Actions
    summary_target = args.summary_file or os.getenv("GITHUB_STEP_SUMMARY")
    if summary_target:
        try:
            summary_content = generate_markdown_summary(result)
            with open(summary_target, "a", encoding="utf-8") as f:
                f.write(summary_content + "\n")
            console.print(f"[bold green][+] Appended Markdown summary to:[/bold green] {summary_target}")
        except Exception as e:
            logging.warning(f"Failed writing markdown summary to {summary_target}: {e}")


if __name__ == "__main__":
    main()
