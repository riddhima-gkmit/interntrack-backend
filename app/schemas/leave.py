"""Leave request schemas: create (type, dates, reason) and update (optional fields). Tenant admin sends user_id via header."""

from datetime import UTC, datetime

from pydantic import BaseModel, field_validator, model_validator

from app.enums import LeaveStatus, LeaveType


def _utc_date(d: datetime):
    """Return the date part in UTC for comparison with today. Naive datetime uses .date() as-is (no timezone assumed)."""
    if d.tzinfo is not None:
        return d.astimezone(UTC).date()
    return d.date()


class LeaveCreateSchema(BaseModel):
    """Request leave. INTERN/MENTOR: leave for self; TENANT_ADMIN: pass user_id header to create on behalf. reason optional."""

    leave_type: LeaveType
    start_date: datetime
    end_date: datetime
    reason: str | None = None  # Optional note.

    @field_validator("leave_type", mode="before")
    @classmethod
    def normalize_leave_type(cls, v):
        """Accept leave_type in any casing (e.g. VACATION, vacation)."""
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @model_validator(mode="after")
    def dates_not_in_past(self):
        """start_date and end_date must not be in the past."""
        today = datetime.now(UTC).date()
        start_past = _utc_date(self.start_date) < today
        end_past = _utc_date(self.end_date) < today
        if start_past and end_past:
            raise ValueError("start_date and end_date cannot be in the past")
        if start_past:
            raise ValueError("start_date cannot be in the past")
        if end_past:
            raise ValueError("end_date cannot be in the past")
        return self

    @model_validator(mode="after")
    def end_date_not_before_start_date(self):
        """end_date must be on or after start_date (same-day leave allowed)."""
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class LeaveUpdateSchema(BaseModel):
    """Update leave (PATCH): all fields optional. Only provided fields are updated. status used for approve/reject by admin."""

    status: LeaveStatus | None = None  # e.g. approved, rejected; admin only.
    leave_type: LeaveType | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None

    # mode="before" so we normalize before enum validation; empty string -> None (omit field in update).
    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v):
        """Accept status in any casing; empty string or null -> None."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator("leave_type", mode="before")
    @classmethod
    def normalize_leave_type(cls, v):
        """Accept leave_type in any casing; empty string or null -> None."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @model_validator(mode="after")
    def dates_not_in_past(self):
        """Provided start_date and end_date must not be in the past."""
        today = datetime.now(UTC).date()
        if self.start_date is not None and _utc_date(self.start_date) < today:
            raise ValueError("start_date cannot be in the past")
        if self.end_date is not None and _utc_date(self.end_date) < today:
            raise ValueError("end_date cannot be in the past")
        return self

    @model_validator(mode="after")
    def end_date_not_before_start_date(self):
        """If both start_date and end_date are provided, end_date must be on or after start_date."""
        if self.start_date is not None and self.end_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date")
        return self
