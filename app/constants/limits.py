"""OTP rate limits: verify attempts and send count before cooldown."""

OTP_MAX_ATTEMPTS = 5  # Max failed OTP verify attempts before lockout.
OTP_MAX_SENDS = 3  # Max OTP sends to same email before cooldown.
