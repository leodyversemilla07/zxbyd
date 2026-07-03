"""OCDS Item and Unit models — representing goods/services procured."""

from __future__ import annotations

from pydantic import BaseModel, Field

from zxbyd.models.common import Classification, Value


class Unit(BaseModel):
    """A unit of measure for an item."""
    name: str | None = Field(default=None, description="Unit name (e.g., 'Piece', 'Lot', 'Unit')")
    value: Value | None = None


class Item(BaseModel):
    """A good, service, or work to be procured.

    Maps to OCDS Item schema with id, description, classification, unit, quantity.
    """
    id: str = Field(default="", description="Identifier for this item within the release")
    description: str = Field(default="", description="Description of the item")
    classification: Classification | None = None
    unit: Unit | None = None
    quantity: int | float | None = None
