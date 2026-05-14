import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt as _bcrypt
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.models.user import EmailToken, EmailTokenType, RefreshToken, User, UserStatus
from app.domain.schemas.auth import (
    LoginRequest,
    RegisterRequest,
)
from app.exceptions import (
    AccountNotActiveError,
    ConflictError,
    InvalidCredentialsError,
    InvalidStateError,
    ResourceNotFoundError,
)
from app.infrastructure.email.email_service import EmailService
from app.infrastructure.logging import security_log
from app.infrastructure.repositories.user_repo import (
    EmailTokenRepository,
    RefreshTokenRepository,
    SQLUserRepository,
)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        email_service: EmailService,
    ) -> None:
        self._db = db
        self._settings = settings
        self._email = email_service
        self._users = SQLUserRepository(db)
        self._email_tokens = EmailTokenRepository(db)
        self._refresh_tokens = RefreshTokenRepository(db)

    # ── Register ──────────────────────────────────────────────────────────────

    async def register(self, data: RegisterRequest) -> User:
        email = data.email.lower().strip()
        existing = await self._users.get_by_email(email)
        if existing:
            raise ConflictError(f"An account with email {email} already exists")

        user = User(
            id=uuid.uuid4(),
            email=email,
            full_name=data.full_name,
            password_hash=_hash_password(data.password),
        )
        user = await self._users.save(user)

        token_str = secrets.token_urlsafe(32)
        email_token = EmailToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=_hash_token(token_str),
            type=EmailTokenType.VERIFICATION,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        await self._email_tokens.save(email_token)
        await self._email.send_verification_email(user.email, user.full_name, token_str)

        return user

    # ── Verify email ──────────────────────────────────────────────────────────

    async def verify_email(self, token: str) -> User:
        email_token = await self._email_tokens.get_by_token_hash(_hash_token(token))
        if not email_token:
            raise ResourceNotFoundError("Verification token is invalid or expired")
        if email_token.used:
            raise InvalidStateError("Verification token has already been used")
        if _as_utc(email_token.expires_at) < datetime.now(UTC):
            raise InvalidStateError("Verification token has expired")
        if email_token.type != EmailTokenType.VERIFICATION:
            raise InvalidStateError("Invalid token type")

        user = await self._users.get_by_id(email_token.user_id)
        if not user:
            raise ResourceNotFoundError("User not found")

        user.email_verified = True
        email_token.used = True
        await self._db.flush()
        return user

    # ── Resend verification ───────────────────────────────────────────────────

    async def resend_verification(self, email: str) -> None:
        user = await self._users.get_by_email(email.lower().strip())
        if not user:
            # Don't leak whether email exists
            return
        if user.email_verified:
            return

        token_str = secrets.token_urlsafe(32)
        email_token = EmailToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=_hash_token(token_str),
            type=EmailTokenType.VERIFICATION,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        await self._email_tokens.save(email_token)
        await self._email.send_verification_email(user.email, user.full_name, token_str)

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(
        self,
        data: LoginRequest,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[str, str]:
        """Returns (access_token, refresh_token_raw)."""
        user = await self._users.get_by_email(data.email.lower().strip())
        if not user or not user.password_hash:
            security_log.log_login_failure(email=data.email.lower().strip(), reason="invalid_credentials", ip_address=ip_address)
            raise InvalidCredentialsError("Invalid email or password")
        if not _verify_password(data.password, user.password_hash):
            security_log.log_login_failure(email=data.email.lower().strip(), reason="invalid_password", ip_address=ip_address)
            raise InvalidCredentialsError("Invalid email or password")

        if user.status == UserStatus.PENDING:
            raise AccountNotActiveError("Account is awaiting admin approval")
        if user.status == UserStatus.SUSPENDED:
            raise AccountNotActiveError("Account has been suspended")

        access_token = self._issue_access_token(user)
        refresh_token_raw, refresh_token_hash = self._generate_refresh_token()

        rt = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=refresh_token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=self._settings.refresh_token_expire_days),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self._refresh_tokens.save(rt)

        security_log.log_login_success(user_id=user.id, email=user.email, ip_address=ip_address)
        return access_token, refresh_token_raw

    # ── Refresh ───────────────────────────────────────────────────────────────

    async def refresh_access_token(self, refresh_token_raw: str) -> tuple[str, str]:
        """Returns (access_token, new_refresh_token_raw). Rotates the refresh token."""
        token_hash = _hash_token(refresh_token_raw)

        # Reuse detection: if the token exists but is revoked, a stolen token is being replayed
        any_rt = await self._refresh_tokens.get_by_hash_any(token_hash)
        if any_rt is not None and any_rt.revoked:
            await self._refresh_tokens.revoke_all_for_user(any_rt.user_id)
            security_log.log_token_reuse_detected(user_id=any_rt.user_id)
            raise InvalidCredentialsError("Refresh token reuse detected — all sessions revoked")

        rt = await self._refresh_tokens.get_by_hash(token_hash)
        if not rt:
            security_log.log_refresh_failure(reason="invalid_token")
            raise InvalidCredentialsError("Invalid or revoked refresh token")
        if _as_utc(rt.expires_at) < datetime.now(UTC):
            security_log.log_refresh_failure(reason="token_expired")
            raise InvalidCredentialsError("Refresh token has expired")

        user = await self._users.get_by_id(rt.user_id)
        if not user or user.status != UserStatus.ACTIVE:
            raise AccountNotActiveError("Account is not active")

        # Rotate: mark old token revoked, issue a new one
        rt.revoked = True
        await self._db.flush()

        new_raw, new_hash = self._generate_refresh_token()
        new_rt = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=new_hash,
            expires_at=datetime.now(UTC) + timedelta(days=self._settings.refresh_token_expire_days),
            user_agent=rt.user_agent,
            ip_address=rt.ip_address,
        )
        await self._refresh_tokens.save(new_rt)

        return self._issue_access_token(user), new_raw

    # ── Logout ────────────────────────────────────────────────────────────────

    async def logout(self, refresh_token_raw: str) -> None:
        token_hash = _hash_token(refresh_token_raw)
        await self._refresh_tokens.delete_by_hash(token_hash)

    # ── Forgot / reset password (stub — deferred per backlog) ─────────────────

    async def forgot_password(self, email: str) -> None:
        user = await self._users.get_by_email(email.lower().strip())
        if not user:
            return  # Silent — don't leak existence

        token_str = secrets.token_urlsafe(32)
        email_token = EmailToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=_hash_token(token_str),
            type=EmailTokenType.PASSWORD_RESET,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        await self._email_tokens.save(email_token)
        await self._email.send_password_reset_email(user.email, user.full_name, token_str)

    async def reset_password(self, token: str, new_password: str) -> None:
        email_token = await self._email_tokens.get_by_token_hash(_hash_token(token))
        if not email_token:
            raise ResourceNotFoundError("Password reset token is invalid or expired")
        if email_token.used:
            raise InvalidStateError("Token has already been used")
        if _as_utc(email_token.expires_at) < datetime.now(UTC):
            raise InvalidStateError("Token has expired")
        if email_token.type != EmailTokenType.PASSWORD_RESET:
            raise InvalidStateError("Invalid token type")

        user = await self._users.get_by_id(email_token.user_id)
        if not user:
            raise ResourceNotFoundError("User not found")

        user.password_hash = _hash_password(new_password)
        email_token.used = True
        await self._db.flush()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _issue_access_token(self, user: User) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value,
            "status": user.status.value,
            "iat": now,
            "exp": now + timedelta(minutes=self._settings.access_token_expire_minutes),
        }
        return jwt.encode(
            payload,
            self._settings.secret_key,
            algorithm=self._settings.jwt_algorithm,
        )

    def _generate_refresh_token(self) -> tuple[str, str]:
        raw = secrets.token_urlsafe(64)
        hashed = _hash_token(raw)
        return raw, hashed
