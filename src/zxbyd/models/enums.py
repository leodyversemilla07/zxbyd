"""OCDS codelists and domain enums."""

from __future__ import annotations

from enum import Enum


class Confidence(str, Enum):
    """Confidence level for analysis findings."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReleaseTag(str, Enum):
    """OCDS release tag codelist — indicates the stage of a contracting process."""
    PLANNING = "planning"
    TENDER = "tender"
    TENDER_AMENDMENT = "tenderAmendment"
    TENDER_CANCELLATION = "tenderCancellation"
    TENDER_UPDATE = "tenderUpdate"
    AWARD = "award"
    AWARD_UPDATE = "awardUpdate"
    CONTRACT = "contract"
    CONTRACT_UPDATE = "contractUpdate"
    CONTRACT_AMENDMENT = "contractAmendment"
    IMPLEMENTATION = "implementation"
    IMPLEMENTATION_UPDATE = "implementationUpdate"
    COMPILED = "compiled"


class InitiationType(str, Enum):
    """OCDS initiation type — how the contracting process was started."""
    TENDER = "tender"
    DIRECT = "direct"
    OTHER = "other"


class TenderStatus(str, Enum):
    """OCDS tender status codelist."""
    PLANNING = "planning"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    COMPLETE = "complete"
    WITHDRAWN = "withdrawn"


class AwardStatus(str, Enum):
    """OCDS award status codelist."""
    PENDING = "pending"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    UNSUCCESSFUL = "unsuccessful"
    WITHDRAWN = "withdrawn"


class ContractStatus(str, Enum):
    """OCDS contract status codelist."""
    PENDING = "pending"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"
    COMPLETE = "complete"


class ProcurementMethod(str, Enum):
    """OCDS procurement method codelist (simplified for PH context)."""
    OPEN = "open"
    SELECTIVE = "selective"
    LIMITED = "limited"
    DIRECT = "direct"
    NEGOTIATED = "negotiated"
    OTHER = "other"


class PartyRole(str, Enum):
    """OCDS party role codelist."""
    BUYER = "buyer"
    PROCURING_ENTITY = "procuringEntity"
    SUPPLIER = "supplier"
    TENDERER = "tenderer"
    PAYER = "payer"
    ADMINISTRATOR = "administrator"


class ProcurementCategory(str, Enum):
    """OCDS procurement category codelist."""
    GOODS = "goods"
    WORKS = "works"
    SERVICES = "services"
    CONSULTING_SERVICES = "consultingServices"
