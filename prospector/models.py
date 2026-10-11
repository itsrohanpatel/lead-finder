"""Core data models for Prospector-AI."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RoleCategory(str, Enum):
    """Classification of target decision-maker roles."""
    C_SUITE = "c_suite"
    HR_TALENT = "hr_talent"
    TECH_LEAD = "tech_lead"
    PRODUCT = "product"
    OTHER = "other"


class CompanyInfo(BaseModel):
    """Resolved company metadata."""
    raw_input: str
    clean_name: str
    domain: Optional[str] = None
    linkedin_company_url: Optional[str] = None
    location_hint: Optional[str] = None
    direct_website_leads: List[dict] = Field(default_factory=list)


class EmailPermutation(BaseModel):
    """An email variant with verification metrics."""
    email: str
    pattern_name: str
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    is_catch_all: bool = False
    smtp_verified: Optional[bool] = None
    publicly_indexed: Optional[bool] = None
    verification_status: str = "unverified"  # "valid", "catch_all", "undeliverable", "likely"


class LeadRecord(BaseModel):
    """An individual discovered executive or talent lead."""
    full_name: str
    first_name: str
    last_name: str
    job_title: str
    role_category: RoleCategory
    linkedin_url: Optional[str] = None
    company_name: str
    domain: Optional[str] = None
    location: Optional[str] = None
    best_email: Optional[str] = None
    email_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    permutations: List[EmailPermutation] = Field(default_factory=list)
    verification_notes: List[str] = Field(default_factory=list)


class MXInfo(BaseModel):
    """Mail exchange records and server fingerprint."""
    domain: str
    has_mx: bool
    mx_records: List[str] = Field(default_factory=list)
    provider: str = "Unknown"  # "Google Workspace", "Microsoft 365", etc.
    is_catch_all: Optional[bool] = None


class ProspectorResult(BaseModel):
    """Complete prospecting execution summary."""
    company: CompanyInfo
    mx_info: Optional[MXInfo] = None
    leads: List[LeadRecord] = Field(default_factory=list)
    c_suite_count: int = 0
    hr_count: int = 0
    tech_count: int = 0
    product_count: int = 0
    total_leads: int = 0
    execution_time_sec: float = 0.0
