from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from google.genai import types
from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    content: str
    input_tokens: int
    output_tokens: int
    metering_metadata: dict[str, int] | None = None


class AzureGenerateContentConfig(BaseModel):
    system_instruction: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    top_p: float | None = None
    top_k: int | None = None
    seed: int | None = None
    response_schema: dict[str, Any] | None = None

    instructions: str | None = None
    reasoning: dict[str, str] | None = None
    metadata: dict[str, str] | None = None
    parallel_tool_calls: bool | None = None
    service_tier: Literal["auto", "default", "flex", "scale", "priority"] | None = None
    store: bool | None = None
    stream_options: dict[str, Any] | None = None
    tool_choice: dict[str, Any] | str | None = None
    tools: list[dict[str, Any]] | None = None
    top_logprobs: int | None = None
    truncation: Literal["auto", "disabled"] | None = None
    user: str | None = None
    background: bool | None = None
    max_tool_calls: int | None = None
    prompt_cache_key: str | None = None
    prompt_cache_retention: Literal["in-memory", "24h"] | None = None
    safety_identifier: str | None = None


GenerateContentConfig = types.GenerateContentConfig | AzureGenerateContentConfig | None


class OCRConfigBase(BaseModel):
    """Base configuration for OCR extraction."""

    min_ocr_confidence: int = Field(
        default=0, ge=0, le=100, description="Minimum confidence threshold (0-100)"
    )


class AzureDocumentIntelligenceConfig(OCRConfigBase):
    """Azure Document Intelligence-specific configuration."""

    model_id: str = Field(
        default="prebuilt-layout", description="Document Intelligence model ID to use"
    )
    locale: str | None = Field(default=None, description="Locale for the document (e.g., 'en-US')")
    pages: str | None = Field(default=None, description="Page range to analyze (e.g., '1-5')")


OCRConfig = OCRConfigBase


class WordElement(BaseModel):
    id: int
    text: str
    conf: Decimal
    box: list[Decimal]


class TableCell(BaseModel):
    row: int
    col: int
    row_span: int
    col_span: int
    kind: str | None = None
    text: str
    box: list[Decimal] | None = None


class TableElement(BaseModel):
    rows: int
    cols: int
    cells: list[TableCell]
    box: list[Decimal] | None = None


class FigureElement(BaseModel):
    caption: str | None = None
    box: list[Decimal] | None = None


class OcrPageElement(BaseModel):
    page: int
    page_width: Decimal
    page_height: Decimal
    words: list[WordElement] = Field(default_factory=list)
    tables: list[TableElement] = Field(default_factory=list)
    figures: list[FigureElement] = Field(default_factory=list)


class OcrResponse(BaseModel):
    no_pages: int
    raw_ocr: dict[str, Any]
    page_elements: list[OcrPageElement]
    duration: Decimal = Decimal("0.0")

    @property
    def text(self) -> str:
        all_words: list[str] = []
        for page in self.page_elements:
            all_words.extend(word.text for word in page.words)
        return " ".join(all_words)

    @property
    def total_words(self) -> int:
        return sum(len(page.words) for page in self.page_elements)

    @property
    def total_tables(self) -> int:
        return sum(len(page.tables) for page in self.page_elements)

    @property
    def total_figures(self) -> int:
        return sum(len(page.figures) for page in self.page_elements)


class Capability(str, Enum):
    CHAT = "chat"
    OCR = "ocr"


class SecretCredentialInfo(BaseModel):
    api_key: str
    api_endpoint: str | None = None
    api_version: str | None = None


class ModelBasicInfo(BaseModel):
    provider: str
    model_name: str
    secret: SecretCredentialInfo


class UserInfo(BaseModel):
    id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    salutation: str | None = None
    status: str
    telephone_number: str | None = None
    preferred_language: str | None = None


class OrganisationInfo(BaseModel):
    id: str
    name: str
    country: str | None = None
    city: str | None = None
    status: str
    type: str
