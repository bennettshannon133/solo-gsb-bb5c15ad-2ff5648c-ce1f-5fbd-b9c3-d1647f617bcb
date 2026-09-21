"""Pydantic v2 请求/响应模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["pending", "confirmed", "doubtful"]
RelType = Literal["supports", "refutes", "derived_from"]
EvidenceKind = Literal["source", "transcript"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Assertion ----------

class AssertionCreate(BaseModel):
    claim: str = Field(min_length=1, max=2000)
    topic: str = Field(min_length=1, max=200)
    status: Status = "pending"
    note: str = ""


class AssertionUpdate(BaseModel):
    claim: Optional[str] = Field(default=None, min_length=1, max=2000)
    topic: Optional[str] = Field(default=None, min_length=1, max=200)
    status: Optional[Status] = None
    note: Optional[str] = None


class Assertion(ORMModel):
    id: int
    claim: str
    topic: str
    status: Status
    note: str
    created_at: datetime
    updated_at: datetime


# ---------- Source ----------

class SourceCreate(BaseModel):
    title: str = Field(min_length=1, max=300)
    publisher: str = ""
    doc_date: str = ""
    url: str = ""
    content: str = ""


class SourceUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max=300)
    publisher: Optional[str] = None
    doc_date: Optional[str] = None
    url: Optional[str] = None
    content: Optional[str] = None


class Source(ORMModel):
    id: int
    title: str
    publisher: str
    doc_date: str
    url: str
    content: str
    created_at: datetime


# ---------- Transcript ----------

class TranscriptCreate(BaseModel):
    speaker: str = Field(min_length=1, max=200)
    interviewed: str = ""
    recorded_at: str = ""
    snippet: str = Field(min_length=1)


class TranscriptUpdate(BaseModel):
    speaker: Optional[str] = Field(default=None, min_length=1, max=200)
    interviewed: Optional[str] = None
    recorded_at: Optional[str] = None
    snippet: Optional[str] = Field(default=None, min_length=1)


class Transcript(ORMModel):
    id: int
    speaker: str
    interviewed: str
    recorded_at: str
    snippet: str
    created_at: datetime


# ---------- Evidence link ----------

class EvidenceCreate(BaseModel):
    kind: EvidenceKind
    ref_id: int
    quote: str = ""


class Evidence(ORMModel):
    id: int
    assertion_id: int
    kind: EvidenceKind
    ref_id: int
    quote: str
    created_at: datetime


# ---------- Assertion relation ----------

class RelationCreate(BaseModel):
    src_id: int
    dst_id: int
    rel_type: RelType
    rationale: str = ""


class Relation(ORMModel):
    id: int
    src_id: int
    dst_id: int
    rel_type: RelType
    rationale: str
    created_at: datetime
