"""Application message constants."""

INTERNAL_ERROR = "An unexpected error occurred. Please try again later."

# Auth
AUTH_INVALID_CREDENTIALS = "Invalid email or password"
AUTH_INACTIVE = "Account is inactive"
AUTH_UNVERIFIED = "Email not verified"
AUTH_ADMIN_DEACTIVATED = "This account was deleted by an admin. Please contact your admin."
OTP_INVALID = "Invalid or expired OTP"
OTP_RATE_LIMITED = "Too many attempts. Please try again later."
OTP_SENT = "OTP sent successfully"
LOGIN_OTP_SENT = "If this email is registered, a login OTP has been sent."

# Users
USER_CANNOT_UPDATE_SELF = "You cannot update your own profile using this endpoint. Use the profile (me) endpoint instead."
USER_USE_ME_ENDPOINT = "You cannot use this endpoint. Use the profile (me) endpoint to view your details."

# Comments (intern permission messages)
INTERN_CAN_ONLY_DELETE_OWN_COMMENT = "Intern can only delete own comment."
INTERN_CAN_ONLY_UPDATE_OWN_COMMENT = "Intern can only update own comment."

# Rate limit (Redis key prefix; full key is ratelimit:public:{client_ip})
RATE_LIMIT_KEY_PREFIX = "ratelimit:public"
