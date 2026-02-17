"""Generic message response schema for endpoints that return only a message (no data payload)."""

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Response body with a single message string. Used e.g. for change-password, invite sent, or other success messages."""

    message: str
