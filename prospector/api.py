"""FastAPI personal REST API for Prospector-AI."""

from typing import List, Optional
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel, Field

from prospector.models import RoleCategory, ProspectorResult
from prospector.pipeline import ProspectorPipeline

app = FastAPI(
    title="Prospector-AI API",
    description="Personal Serverless API for C-Suite & HR Talent Lead Discovery",
    version="1.0.0",
)


class ProspectRequest(BaseModel):
    company: str = Field(..., description="Company domain (e.g. stripe.com), name, or LinkedIn URL")
    roles: List[RoleCategory] = Field(
        default=[RoleCategory.C_SUITE, RoleCategory.HR_TALENT],
        description="Target decision maker roles",
    )
    check_smtp: bool = Field(default=False, description="Enable raw SMTP socket check (set false if port 25 blocked)")
    max_leads: int = Field(default=10, ge=1, le=50, description="Max leads per category")


@app.get("/")
def root():
    return {
        "service": "Prospector-AI",
        "status": "online",
        "description": "Zero-Cost Serverless B2B Lead Generation API",
        "docs_url": "/docs",
    }


@app.post("/api/prospect", response_model=ProspectorResult)
def prospect_endpoint(req: ProspectRequest):
    """Enrich and discover C-suite and HR decision makers for a given target company."""
    try:
        pipeline = ProspectorPipeline(check_smtp=req.check_smtp, max_leads_per_role=req.max_leads)
        result = pipeline.run(company_input=req.company, target_roles=req.roles)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Prospecting failed: {str(exc)}")


@app.get("/api/prospect", response_model=ProspectorResult)
def prospect_get_endpoint(
    company: str = Query(..., description="Domain, company name, or LinkedIn URL"),
    role: Optional[str] = Query("all", description="'c_suite', 'hr_talent', or 'all'"),
    check_smtp: bool = Query(False, description="Enable raw SMTP socket check"),
    max_leads: int = Query(10, description="Max leads per category"),
):
    """Quick GET endpoint for curl or browser testing."""
    if role == "c_suite":
        roles = [RoleCategory.C_SUITE]
    elif role == "hr_talent":
        roles = [RoleCategory.HR_TALENT]
    else:
        roles = [RoleCategory.C_SUITE, RoleCategory.HR_TALENT]

    pipeline = ProspectorPipeline(check_smtp=check_smtp, max_leads_per_role=max_leads)
    return pipeline.run(company_input=company, target_roles=roles)
