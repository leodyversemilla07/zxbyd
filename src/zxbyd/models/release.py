"""OCDS Release and ReleasePackage — the top-level data structures.

A Release represents a single event in a contracting process.
A ReleasePackage wraps one or more releases with metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from zxbyd.models.common import Value, Period
from zxbyd.models.party import Organization, OrganizationReference
from zxbyd.models.tender import Tender, Planning
from zxbyd.models.award import Award
from zxbyd.models.contract import Contract


class Publisher(BaseModel):
    """Information about the publisher of this data package."""
    name: str = "zxbyd"
    scheme: str | None = None
    uid: str | None = None
    uri: str | None = None


class Release(BaseModel):
    """A single release in an OCDS contracting process.

    Represents one event (tender notice, award, contract signing, etc.)
    in the lifecycle of a procurement.
    """
    model_config = {'populate_by_name': True}

    ocid: str = Field(default="", description="Open Contracting ID — globally unique identifier")
    id: str = Field(default="", description="Release ID — unique within the contracting process")
    date: str = Field(default="", description="Date this release was published")
    tag: list[str] = Field(default_factory=list, description="Release tag(s) from the OCDS codelist")
    initiation_type: str = Field(default="tender", alias="initiationType")

    # Core sections
    parties: list[Organization] = Field(default_factory=list)
    buyer: OrganizationReference | None = None

    # Procurement stages
    planning: Planning | None = None
    tender: Tender | None = None
    awards: list[Award] = Field(default_factory=list)
    contracts: list[Contract] = Field(default_factory=list)

    # Metadata
    language: str = "en"

    # ── Helper: extract ABC from tender value ─────────────────────
    @property
    def abc(self) -> float | None:
        """Approved Budget for the Contract, extracted from tender.value."""
        if self.tender and self.tender.value:
            return self.tender.value.amount
        return None

    # ── Helper: find procuring entity name ────────────────────────
    @property
    def agency_name(self) -> str:
        """Best-effort procuring entity name."""
        if self.tender and self.tender.procuring_entity:
            return self.tender.procuring_entity.name or ""
        return ""

    # ── Helper: serialization ─────────────────────────────────────
    def model_dump_simple(self) -> dict:
        """Backward-compatible flat dict for command display."""
        return {
            "ref_no": self.ocid.split("-")[-1] if "-" in self.ocid else self.ocid,
            "ocid": self.ocid,
            "title": self.tender.title if self.tender else "",
            "agency": self.agency_name,
            "category": (
                self.tender.main_procurement_category
                if self.tender and self.tender.main_procurement_category
                else ""
            ),
            "abc": self.abc,
            "mode": (
                self.tender.procurement_method_details or self.tender.procurement_method or ""
                if self.tender else ""
            ),
            "area_of_delivery": "",
            "published_date": (
                self.tender.tender_period.start_date
                if self.tender and self.tender.tender_period
                else ""
            ),
            "closing_date": (
                self.tender.tender_period.end_date
                if self.tender and self.tender.tender_period
                else ""
            ),
            "description": self.tender.description if self.tender else "",
            "status": self.tender.status if self.tender else "",
            "solicitation_number": self.tender.id if self.tender else "",
            "documents": "",
        }

    @classmethod
    def from_philgeps_dict(cls, data: dict) -> "Release":
        """Build an OCDS Release from a raw PhilGEPS notice dict.

        This is the primary adapter between the scraper and the OCDS model.
        """
        ref_no = data.get("ref_no", "")
        ocid = f"ocds-zxbyd-{ref_no}" if ref_no else ""

        # Build the procuring entity
        agency_name = data.get("agency", "")
        procuring_entity = None
        parties = []

        if agency_name:
            pe_id = f"PH-GEPS-{agency_name.replace(' ', '-')[:30]}"
            procuring_entity = OrganizationReference(name=agency_name, id=pe_id)
            parties.append(Organization(
                id=pe_id,
                name=agency_name,
                roles=["procuringEntity"],
            ))

        # Build tender
        abc_raw = data.get("abc")
        tender_value = Value(
            amount=float(abc_raw) if abc_raw else 0.0,
            currency="PHP",
        ) if abc_raw else None

        tender = Tender(
            id=data.get("solicitation_number", "") or ref_no,
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=data.get("status", ""),
            procuring_entity=procuring_entity,
            value=tender_value,
            procurement_method_details=data.get("mode", ""),
            tender_period=Period(
                start_date=data.get("published_date", ""),
                end_date=data.get("closing_date", ""),
            ),
        )

        # Determine tag
        tag = ["tender"]
        if data.get("status", "").lower() in ("awarded", "closed"):
            tag = ["tender", "award"]

        return cls(
            ocid=ocid,
            id=ref_no,
            date=data.get("published_date", datetime.now(timezone.utc).isoformat()),
            tag=tag,
            initiation_type="tender",
            parties=parties,
            tender=tender,
        )


class ReleasePackage(BaseModel):
    """A package containing one or more OCDS releases."""
    model_config = {'populate_by_name': True}

    uri: str = ""
    version: str = "1.1"
    published_date: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        alias="publishedDate",
    )
    publisher: Publisher = Field(default_factory=Publisher)
    releases: list[Release] = Field(default_factory=list)
    license: str | None = None
    publication_policy: str | None = Field(default=None, alias="publicationPolicy")
