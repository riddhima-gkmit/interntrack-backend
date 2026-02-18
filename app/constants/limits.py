"""OTP rate limits: verify attempts and send count before cooldown."""

OTP_MAX_ATTEMPTS = 5  # Max failed OTP verify attempts before lockout.
OTP_MAX_SENDS = 3  # Max OTP sends to same email before cooldown.

# Public API rate limit (unauthenticated endpoints: auth, tenant register)
# Fixed window: max requests per client per window.
RATE_LIMIT_PUBLIC_REQUESTS = 10  # Max requests per window per client (IP)
RATE_LIMIT_PUBLIC_WINDOW_SEC = 60  # Window duration in seconds
