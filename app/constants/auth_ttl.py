"""TTLs in seconds for OTP and cooldowns."""

OTP_TTL = 600  # 10 minutes — OTP validity.
OTP_COOLDOWN = 60  # 1 minute between OTP sends; cooldown after OTP_MAX_SENDS.
RESEND_WAIT_SECONDS = 60  # Minimum seconds before resend allowed (e.g. verify email).
