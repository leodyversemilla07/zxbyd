"""OCDS Organization and Party models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from zxbyd.models.common import Address, ContactPoint, Identifier


class OrganizationReference(BaseModel):
    """A lightweight reference to an organization by name and id.

    Used in tender.procuringEntity, award.suppliers, etc.
    The actual organization details live in Release.parties[].
    """
    name: str | None = None
    id: str | None = None


class Organization(BaseModel):
    """A full organization record as used in Release.parties[]."""
    model_config = {'populate_by_name': True}

    name: str | None = None
    id: str = Field(default="", description="Cross-reference ID used within the release")
    identifier: Identifier | None = None
    additional_identifiers: list[Identifier] = Field(
        default_factory=list, alias="additionalIdentifiers"
    )
    address: Address | None = None
    contact_point: ContactPoint | None = Field(default=None, alias="contactPoint")
    roles: list[str] = Field(default_factory=list)
    details: dict | None = None


class Party(Organization):
    """Alias for Organization — used for semantic clarity in the parties context."""
    pass
