"""Common OCDS data types — Value, Period, Address, ContactPoint, Identifier, Classification."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Value(BaseModel):
    """A monetary value with currency."""
    amount: float = 0.0
    currency: str = "PHP"

    def __str__(self) -> str:
        return f"PHP {self.amount:,.2f}"


class Period(BaseModel):
    """A time period with start and end dates."""
    start_date: str | None = Field(default=None, description="Start date of the period")
    end_date: str | None = Field(default=None, description="End date of the period")
    duration_in_days: int | None = Field(default=None, description="Duration in days")


class Address(BaseModel):
    """A physical address."""
    street_address: str | None = None
    locality: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country_name: str | None = "Philippines"


class ContactPoint(BaseModel):
    """Contact information for an organization."""
    name: str | None = None
    email: str | None = None
    telephone: str | None = None
    fax: str | None = None
    url: str | None = None


class Identifier(BaseModel):
    """An organization identifier from a recognized scheme."""
    model_config = {'populate_by_name': True}

    scheme: str = Field(default="", description="The identifier scheme (e.g., 'PH-GEPS', 'PH-BIR')")
    id: str = Field(default="", description="The identifier value")
    legal_name: str | None = Field(default=None, alias="legalName")
    uri: str | None = None


class Classification(BaseModel):
    """A classification from a recognized scheme (e.g., UNSPSC, PhilGEPS category)."""
    scheme: str | None = Field(default=None, description="The classification scheme")
    id: str | None = Field(default=None, description="The classification code")
    description: str | None = Field(default=None, description="Human-readable description")
    uri: str | None = None
