"""OCDS Award model — represents an award decision in a contracting process."""

from __future__ import annotations

from pydantic import BaseModel, Field

from zxbyd.models.common import Period, Value
from zxbyd.models.item import Item
from zxbyd.models.party import OrganizationReference


class Award(BaseModel):
    """An award made to a supplier as part of a contracting process.

    Maps to OCDS Award section. There can be multiple awards per tender.
    """
    model_config = {'populate_by_name': True}

    id: str = Field(default="", description="Award identifier (unique within the process)")
    title: str | None = None
    description: str | None = None
    status: str | None = None
    date: str | None = None
    value: Value | None = None
    suppliers: list[OrganizationReference] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)
    contract_period: Period | None = Field(default=None, alias="contractPeriod")
