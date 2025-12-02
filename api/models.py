"""Pydantic models for request/response validation."""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional


class QueryRequest(BaseModel):
    """Request model for agent query endpoint."""

    tenant_id: str = Field(..., description="Tenant ID (e.g., '1', '10', '89')")
    prompt: str = Field(..., min_length=1, description="User prompt/query")
    skill: Optional[str] = Field(None, description="Skill name to use (e.g., 'invoice-field-recommender')")
    language: Optional[str] = Field(None, description="Response language (required for new sessions)")
    session_id: Optional[str] = Field(None, description="Session ID for resuming conversation")
    country_code: Optional[str] = Field(None, description="Country code for context (e.g., 'MY', 'DE') (required for new sessions)")
    context: Optional[str] = Field(None, description="Invoice data in UBL 2.1 format")

    @field_validator('tenant_id')
    @classmethod
    def tenant_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('tenant_id cannot be empty')
        return v.strip()

    @field_validator('prompt')
    @classmethod
    def prompt_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('prompt cannot be empty')
        return v.strip()

    @field_validator('language')
    @classmethod
    def language_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError('language cannot be empty string')
        return v.strip() if v else None

    @field_validator('country_code')
    @classmethod
    def country_code_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError('country_code cannot be empty string')
        return v.strip() if v else None

    @model_validator(mode='after')
    def validate_new_session_requirements(self):
        """Require country_code and language for new sessions only."""
        if not self.session_id:  # New session
            if not self.country_code:
                raise ValueError('country_code is required for new sessions')
            if not self.language:
                raise ValueError('language is required for new sessions')
        return self

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "summary": "New session",
                    "description": "Starting a new conversation (requires language and country_code)",
                    "value": {
                        "tenant_id": "1",
                        "prompt": "推荐unitCode for 咖啡机",
                        "skill": "invoice-field-recommender",
                        "language": "中文",
                        "session_id": None,
                        "country_code": "MY",
                        "context": "<Invoice>...</Invoice>"
                    }
                },
                {
                    "summary": "Continuation session",
                    "description": "Resuming an existing conversation (language and country_code optional)",
                    "value": {
                        "tenant_id": "1",
                        "prompt": "继续前面的对话",
                        "session_id": "abc-123-def"
                    }
                }
            ]
        }
