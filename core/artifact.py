"""Artifact and Claim Ledger schema module for Bioauto 5.0."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class EvidenceRef:
    kind: str  # "artifact" | "citation"
    ref: str
    span: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "ref": self.ref, "span": self.span}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRef":
        return cls(kind=data["kind"], ref=data["ref"], span=data.get("span"))


@dataclass
class ClaimRecord:
    statement: str
    claim_type: str  # "observation" | "literature" | "hypothesis"
    population_context: str
    endpoint: str
    direction: str  # "up" | "down" | "none" | "null"
    claim_id: str = field(default_factory=lambda: f"c-{uuid.uuid4()}")
    schema_version: str = "0.1"
    effect: dict[str, Any] | None = None
    evidence: list[EvidenceRef] = field(default_factory=list)
    validation_status: str = "not-testable"  # "supported" | "contradicted" | "inconclusive" | "not-testable"
    validation_scope: str = "none"  # "independent-study" | "internal-robustness-only" | "none"
    produced_by: dict[str, Any] = field(default_factory=dict)
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        """Enforce D3 rules and RFC invariants upon instantiation."""
        if not self.population_context or not self.endpoint:
            self.validation_status = "not-testable"
        self.validate_rules()

    def validate_rules(self) -> None:
        """Validate D3 rules for Claim Record."""
        # Single-sample observations cannot claim supported independent-study
        if self.validation_scope == "none" and self.validation_status == "supported":
            raise ValueError("Claim with validation_scope='none' cannot have validation_status='supported'")
        if self.validation_status not in ["supported", "contradicted", "inconclusive", "not-testable"]:
            raise ValueError(f"Invalid validation_status: '{self.validation_status}'")
        if self.validation_scope not in ["independent-study", "internal-robustness-only", "none"]:
            raise ValueError(f"Invalid validation_scope: '{self.validation_scope}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "schema_version": self.schema_version,
            "statement": self.statement,
            "claim_type": self.claim_type,
            "population_context": self.population_context,
            "endpoint": self.endpoint,
            "direction": self.direction,
            "effect": self.effect,
            "evidence": [e.to_dict() for e in self.evidence],
            "validation_status": self.validation_status,
            "validation_scope": self.validation_scope,
            "produced_by": self.produced_by,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClaimRecord":
        evidence = [EvidenceRef.from_dict(e) for e in data.get("evidence", [])]
        rec = cls(
            claim_id=data.get("claim_id", f"c-{uuid.uuid4()}"),
            schema_version=data.get("schema_version", "0.1"),
            statement=data["statement"],
            claim_type=data.get("claim_type", "hypothesis"),
            population_context=data.get("population_context", ""),
            endpoint=data.get("endpoint", ""),
            direction=data.get("direction", "none"),
            effect=data.get("effect"),
            evidence=evidence,
            validation_status=data.get("validation_status", "not-testable"),
            validation_scope=data.get("validation_scope", "none"),
            produced_by=data.get("produced_by", {}),
            created=data.get("created", datetime.now(timezone.utc).isoformat()),
        )
        return rec
