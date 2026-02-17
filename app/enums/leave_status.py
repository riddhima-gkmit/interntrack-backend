"""Leave request status: pending, approved, rejected, or cancelled. Used in leave model and approval flow."""

from enum import StrEnum

class LeaveStatus(StrEnum):
    """Status of a leave request (workflow: pending → approved/rejected; user can cancel pending)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
