"""Pydantic 请求模型与枚举。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# 断言状态流转：待核查 -> 已确认 / 存疑（可互相流转）
Status = Literal["pending", "confirmed", "doubtful"]
# 证据关系类型：支持 / 反驳 / 派生自
RelType = Literal["supports", "refutes", "derives"]
# 来源类型：文档 / 逐字稿
SourceKind = Literal["document", "transcript"]

STATUS_LABELS = {"pending": "待核查", "confirmed": "已确认", "doubtful": "存疑"}
REL_LABELS = {"supports": "支持", "refutes": "反驳", "derives": "派生自"}
KIND_LABELS = {"document": "文档", "transcript": "逐字稿"}


class TopicIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""


class SourceIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: SourceKind = "document"
    publisher: str = ""
    url: str = ""
    excerpt: str = ""


class ClaimIn(BaseModel):
    text: str = Field(min_length=1)
    topic_id: Optional[int] = None
    source_id: Optional[int] = None
    notes: str = ""


class ClaimUpdate(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1)
    topic_id: Optional[int] = None
    source_id: Optional[int] = None
    status: Optional[Status] = None
    notes: Optional[str] = None


class StatusIn(BaseModel):
    status: Status


class RelationIn(BaseModel):
    from_claim_id: int
    to_claim_id: int
    type: RelType
    note: str = ""
