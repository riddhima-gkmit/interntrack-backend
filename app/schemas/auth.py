"""Request/response schemas for auth: register, login, OTP, forgot-password, refresh. Validation errors surface as 422."""

from pydantic import BaseModel, EmailStr, field_validator

from app.utils.validators import first_name_not_empty, password_strength


class RegisterSchema(BaseModel):
    """Self signup (e.g. /tenants/{id}/register). Validators: first_name non-empty, password strength, confirm_password must match."""

    username: str
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    confirm_password: str

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        return first_name_not_empty(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return password_strength(v)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v


class VerifyEmailSchema(BaseModel):
    """Verify email after register using OTP sent to email."""

    email: EmailStr
    otp: str


class ResendVerificationSchema(BaseModel):
    """Request a new verification OTP for the given email."""

    email: EmailStr


class LoginSchema(BaseModel):
    """Email + password. Used for direct login or as step 1 of login-OTP flow."""

    email: EmailStr
    password: str


class VerifyLoginOTPSchema(BaseModel):
    """Step 2 of login-OTP: email + OTP sent after step 1; returns tokens."""

    email: EmailStr
    otp: str


class ForgotPasswordSchema(BaseModel):
    """Request password-reset OTP for the given email."""

    email: EmailStr


class ForgotPasswordConfirmSchema(BaseModel):
    """Confirm reset with OTP + new password. Same strength and match validators as register."""

    email: EmailStr
    otp: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return password_strength(v)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v


class RefreshSchema(BaseModel):
    """Refresh token in body (no Bearer header). Used by POST /auth/refresh."""

    refresh: str


class InviteRegisterSchema(BaseModel):
    """Complete registration with invite token; email comes from invite so not in body. Same validators as RegisterSchema for name/password."""

    username: str
    first_name: str
    last_name: str
    password: str
    confirm_password: str

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        return first_name_not_empty(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return password_strength(v)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v
