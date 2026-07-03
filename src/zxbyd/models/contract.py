"""OCDS Contract model — represents a signed contract."""

from __future__ import annotations

from pydantic import BaseModel, Field

from zxbyd.models.common import Period, Value
from zxbyd.models.item import Item


class Contract(BaseModel):
    """A signed contract following an award.

    Maps to OCDS Contract section. Every contract references an award.
    """
    model_config = {'populate_by_name': True}

    id: str = Field(default="", description="Contract identifier (unique within the process)")
    award_id: str = Field(default="", alias="awardID", description="Reference to the related award")
    title: str | None = None
    description: str | None = None
    status: str | None = None
    period: Period | None = None
    value: Value | None = None
    items: list[Item] = Field(default_factory=list)
    date_signed: str | None = Field(default=None, alias="dateSigned")
