"""Pydantic models for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional


class QueryRequest(BaseModel):
    """Request model for agent query endpoint."""

    tenant_id: str = Field(..., description="Tenant ID (e.g., '1', '10', '89')")
    prompt: str = Field(..., min_length=1, description="User prompt/query")
    skill: Optional[str] = Field(None, description="Skill name to use (e.g., 'invoice-field-recommender')")
    language: str = Field(default="中文", description="Response language")
    session_id: Optional[str] = Field(None, description="Session ID for resuming conversation")
    country_code: Optional[str] = Field(None, description="Country code for context (e.g., 'MY', 'DE')")

    class Config:
        json_schema_extra = {
            "example": {
                "tenant_id": "1",
                "prompt": "推荐unitCode for 咖啡机",
                "skill": "invoice-field-recommender",
                "language": "中文",
                "session_id": None,
                "country_code": "MY"
            }
        }
