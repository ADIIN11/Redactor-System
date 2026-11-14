from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    x0: float = Field(..., ge=0.0, le=1.0, description="Normalized left X coordinate (0.0 to 1.0)")
    y0: float = Field(..., ge=0.0, le=1.0, description="Normalized top Y coordinate (0.0 to 1.0)")
    x1: float = Field(..., ge=0.0, le=1.0, description="Normalized right X coordinate (0.0 to 1.0)")
    y1: float = Field(..., ge=0.0, le=1.0, description="Normalized bottom Y coordinate (0.0 to 1.0)")


class DetectedEntity(BaseModel):
    id: str
    page: int = Field(default=1, ge=1)
    line_number: int = Field(default=1, ge=1)
    entity_type: str = Field(
        ...,
        description="Entity code such as IN_AADHAAR, IN_PAN, IN_IFSC, BANK_ACCOUNT, CREDIT_CARD, PHONE_NUMBER, EMAIL_ADDRESS, PERSON, LOCATION, CUSTOM_BOX",
    )
    category: Literal["GOV_ID", "FINANCIAL", "CONTACT_PII", "CUSTOM_BOX"]
    text_preview: str = Field(
        ...,
        description="Sanitized preview string; always '[Aadhaar Redacted]' for national IDs",
    )
    start_char: int = Field(default=0, ge=0)
    end_char: int = Field(default=0, ge=0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    validator_passed: str = Field(
        default="Contextual NER",
        description="Validation method e.g. Verhoeff Checksum, Luhn Mod-10 Verified, Tax Entity Structure Verified",
    )
    bbox: Optional[BoundingBox] = None
    selected_for_redaction: bool = True


class AnalyzeResponse(BaseModel):
    document_id: str
    filename: str
    file_type: Literal["txt", "pdf", "image"]
    sha256_original: str
    page_count: int
    page_previews_b64: List[str] = Field(default_factory=list)
    raw_text_lines: List[str] = Field(default_factory=list)
    entities: List[DetectedEntity] = Field(default_factory=list)
    risk_summary: Dict[str, int] = Field(default_factory=dict)


class RedactCloneRequest(BaseModel):
    document_id: str
    redaction_mode: Literal["cia_blackout", "partial_mask", "entity_tag"] = "cia_blackout"
    add_declassified_stamp: bool = True
    entities: List[DetectedEntity]


class AuditCertificate(BaseModel):
    document_id: str
    original_filename: str
    redacted_filename: str
    sha256_original: str
    sha256_redacted: str
    redaction_mode: str
    zero_leak_flattened: bool
    total_redacted_count: int
    category_breakdown: Dict[str, int]
    timestamp_utc: str


class RedactCloneResponse(BaseModel):
    redacted_filename: str
    mime_type: str
    file_b64: str
    audit_certificate: AuditCertificate