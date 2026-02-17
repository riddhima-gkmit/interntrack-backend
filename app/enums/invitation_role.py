"""Role offered by an invitation. Only MENTOR and INTERN can be invited (used in invitation model and POST /users/invite/)."""

from enum import StrEnum

class InvitationRole(StrEnum):
    """Role the invitee will get when they accept the invitation. Only MENTOR and INTERN."""

    MENTOR = "mentor"
    INTERN = "intern"
