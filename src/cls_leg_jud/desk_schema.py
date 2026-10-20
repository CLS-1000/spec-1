"""Desk schemas and store-row translation for Legislative & Judicial Desk v2.1.

Defines DeskRecord, DeskStatement, DeskBeneficiarySignal, CycleConfig,
and from_store_row() with automated fallback to bridge_generic_row.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DeskStatement(BaseModel):
    speaker: str = Field(..., description="Entity or official making the statement or holding.")
    text: str = Field(..., description="Verbatim quote, ruling text, or formal disclosure.")
    verified: bool = Field(default=False, description="Verification status of statement source.")
    context: str = Field(default="", description="Citation or docket context.")


class DeskBeneficiarySignal(BaseModel):
    entity: str = Field(..., description="Target party, client, foreign principal, or litigant.")
    jurisdiction: str = Field(default="US", description="Target state, district, or ISO country code.")
    relationship: str = Field(..., description="Role: foreign_principal, lobbying_client, litigant, sponsor.")
    amount: float = Field(default=0.0, description="Financial backing or reported lobbying value.")


class DeskRecord(BaseModel):
    record_id: str = Field(..., description="Unique immutable trace ID.")
    domain: str = Field(..., description="Domain label matching spec1_labels specification.")
    timestamp: datetime = Field(..., description="UTC timestamp of the record action.")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score.")
    gate_results: Dict[str, Any] = Field(default_factory=dict, description="Parsed gate filter evaluations.")
    statements: List[DeskStatement] = Field(default_factory=list, description="Extracted statements for Section 6.")
    beneficiary_signals: List[DeskBeneficiarySignal] = Field(default_factory=list, description="Beneficiary entities.")
    raw_metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw underlying store payload.")


class CycleConfig(BaseModel):
    window_hours: int = Field(default=72, description="Drop records older than cutoff.")
    min_confidence: float = Field(default=0.70, description="Minimum confidence threshold.")
    enforce_gates: bool = Field(default=True, description="Enforce passed evaluation flag on gate_results.")
    target_domains: List[str] = Field(
        default=[
            "fara.filing",
            "congress.vote",
            "congress.lda",
            "judicial.ruling",
            "state_leg.bill",
        ],
        description="Active domain whitelist for briefing cycle.",
    )


def from_store_row(row: Dict[str, Any]) -> Optional[DeskRecord]:
    """Translate raw store record to DeskRecord.

    Attempts direct schema validation first. If domain is missing, malformed,
    or native adapter fields are detected, falls back to bridge_generic_row.
    """
    if not isinstance(row, dict):
        return None

    # Fallback to bridge module if domain is absent or row contains raw adapter fields
    if not row.get("domain") or "registration_number" in row or "filing_uuid" in row or "pacer_doc_id" in row:
        try:
            from cls_leg_jud.bridges.adapters import bridge_generic_row
            return bridge_generic_row(row)
        except Exception as err:
            logger.debug("bridge_generic_row failed on fallback: %s", err)

    # Direct parse attempt
    try:
        raw_ts = row.get("timestamp")
        if isinstance(raw_ts, str):
            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            ts = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        elif isinstance(raw_ts, datetime):
            ts = raw_ts if raw_ts.tzinfo else raw_ts.replace(tzinfo=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        raw_conf = row.get("confidence", 0.0)
        try:
            confidence = float(raw_conf)
        except (ValueError, TypeError):
            confidence = 0.0

        return DeskRecord(
            record_id=str(row.get("id") or row.get("record_id") or ""),
            domain=str(row.get("domain")),
            timestamp=ts,
            confidence=confidence,
            gate_results=row.get("gate_results") if isinstance(row.get("gate_results"), dict) else {},
            statements=row.get("statements", []),
            beneficiary_signals=row.get("beneficiary_signals", []),
            raw_metadata=row,
        )
    except Exception:
        # Final attempt through bridge before dropping
        try:
            from cls_leg_jud.bridges.adapters import bridge_generic_row
            return bridge_generic_row(row)
        except Exception:
            return None
