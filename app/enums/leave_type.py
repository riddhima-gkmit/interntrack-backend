"""Leave request type: sick, vacation, personal, or other. Used in leave model and API."""

from enum import StrEnum

class LeaveType(StrEnum):
    """Type of leave requested by the user."""

    SICK = "sick"
    VACATION = "vacation"
    PERSONAL = "personal"
    OTHER = "other"
