"""OCDS Tender model — represents the tender stage of a contracting process."""

from __future__ import annotations

from pydantic import BaseModel, Field

from zxbyd.models.common import Period, Value, Classification
from zxbyd.models.item import Item
from zxbyd.models.party import OrganizationReference


class Tender(BaseModel):
    """The tender stage — announcement of intent to procure goods/services/works.

    Maps to OCDS Tender section. Core fields used by zxbyd are required,
    with optional fields available for richer data.
    """
    model_config = {'populate_by_name': True}

    id: str = Field(default="", description="Tender ID (often PhilGEPS solicitation number)")
    title: str = Field(default="", description="Title of the tender")
    description: str | None = Field(default=None, description="Detailed description of the tender")
    status: str | None = Field(default=None, description="Current status (active, cancelled, complete, etc.)")
    procuring_entity: OrganizationReference | None = Field(
        default=None, alias="procuringEntity",
        description="The entity managing the procurement",
    )
    items: list[Item] = Field(default_factory=list, description="Goods/services being procured")
    value: Value | None = Field(default=None, description="ABC — Approved Budget for the Contract")
    min_value: Value | None = Field(default=None, alias="minValue")
    procurement_method: str | None = Field(default=None, alias="procurementMethod")
    procurement_method_details: str | None = Field(default=None, alias="procurementMethodDetails")
    main_procurement_category: str | None = Field(default=None, alias="mainProcurementCategory")
    award_criteria: str | None = Field(default=None, alias="awardCriteria")
    submission_method: list[str] = Field(default_factory=list, alias="submissionMethod")
    tender_period: Period | None = Field(default=None, alias="tenderPeriod")
    award_period: Period | None = Field(default=None, alias="awardPeriod")
    contract_period: Period | None = Field(default=None, alias="contractPeriod")
    number_of_tenderers: int | None = Field(default=None, alias="numberOfTenderers")
    tenderers: list[OrganizationReference] = Field(default_factory=list)


class Planning(BaseModel):
    """Information from the planning phase — budget, rationale, project."""
    model_config = {'populate_by_name': True}

    rationale: str | None = None
    budget: Value | None = None
    project: str | None = None
    project_id: str | None = Field(default=None, alias="projectID")
