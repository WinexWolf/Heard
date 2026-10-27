from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

IssueType = Literal["missing_name", "missing_alt", "missing_label", "vague_link", "repeated_control",
                    "error_not_announced", "label_in_name", "missing_state", "div_button", "modal_dialog",
                    "tab_widget", "heading_skip", "other"]


class Finding(BaseModel):
    id: str
    t_start: float
    t_end: float
    announced_text: str
    visible_text_or_description: str
    issue_type: IssueType
    severity: Literal["low", "medium", "high", "critical"]
    wcag_guess: str
    evidence: str


class FindingList(BaseModel):
    findings: list[Finding] = Field(default_factory=list)


class Edit(BaseModel):
    file: str
    old_str: str
    new_str: str


class PatchResult(BaseModel):
    edits: list[Edit]
    rationale: str = ""


class Citation(BaseModel):
    title: str
    url: str
