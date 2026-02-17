"""Comment schemas: create (message) and update (message). Task and tenant come from URL/deps, not body."""

from pydantic import BaseModel


class CommentCreateSchema(BaseModel):
    """Create comment. Message required; task_id from URL, author from current_user, tenant from JWT."""

    message: str


class CommentUpdateSchema(BaseModel):
    """Update comment. Only message is editable (task, user, tenant are fixed). Used for PATCH."""

    message: str
