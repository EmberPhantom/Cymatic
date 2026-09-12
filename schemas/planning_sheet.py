"""Shared Planning Sheet Schemas (Python/Pydantic)

The planning agent's frozen output: a reviewed, versioned source of truth
that the generation agent consumes. Typed dimensions/colors/materials so the
questionnaire UI and the architect share one contract (no free-form soup).
"""
import re
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


Domain = Literal["real_estate", "heritage"]
LengthUnit = Literal["mm", "cm", "m"]


class Dimension(BaseModel):
    value: float = Field(gt=0)
    unit: LengthUnit = "m"


class SpaceSize(BaseModel):
    width: Optional[Dimension] = None
    depth: Optional[Dimension] = None
    height: Optional[Dimension] = None


_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class Color(BaseModel):
    hex: str
    name: Optional[str] = None

    @field_validator("hex", mode="before")
    @classmethod
    def _normalize_hex(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if re.fullmatch(r"[0-9a-fA-F]{6}", v):
                v = "#" + v
            if re.fullmatch(r"[0-9a-fA-F]{3}", v):
                v = "#" + "".join(c * 2 for c in v)
        if not isinstance(v, str) or not _HEX_COLOR.match(v):
            raise ValueError(f"Color.hex must be #rrggbb, got {v!r}")
        return v.lower()


class Material(BaseModel):
    name: str
    finish: Optional[str] = None
    palette: List[Color] = []


class SpaceLighting(BaseModel):
    preset: Optional[str] = None
    notes: Optional[str] = None


class PlanSpace(BaseModel):
    id: str
    kind: Literal["room", "poi"] = "room"
    name: str
    size: SpaceSize = Field(default_factory=SpaceSize)
    colors: List[Color] = []
    materials: List[Material] = []
    lighting: SpaceLighting = Field(default_factory=SpaceLighting)
    features: List[str] = []


class ResearchRef(BaseModel):
    title: str
    source: str
    url: Optional[str] = None
    snippet: Optional[str] = None


class PlanningSheet(BaseModel):
    objective: str
    domain: Domain
    version: str = "1.0.0"
    spaces: List[PlanSpace] = []
    style: Dict[str, str] = {}
    constraints: Dict[str, Any] = {}
    open_questions: List[str] = []
    research_refs: List[ResearchRef] = []
    analyser_mode: str = "llm"

    @field_validator("version", mode="before")
    @classmethod
    def _coerce_version(cls, v):
        return str(v)
