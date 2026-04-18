import logging

logger = logging.getLogger(__name__)


class EmailService:
    """
    MVP stub: logs emails to stdout instead of sending real SMTP.
    Replace smtp_enabled=true in .env and implement _send_smtp() for production.
    """

    def __init__(self, smtp_enabled: bool = False, base_url: str = "http://localhost:8000"):
        self._smtp_enabled = smtp_enabled
        self._base_url = base_url

    async def send_verification_email(self, to_email: str, full_name: str, token: str) -> None:
        link = f"{self._base_url}/verify-email?token={token}"
        logger.info(
            "[EMAIL STUB] Verification email → %s | link: %s",
            to_email,
            link,
        )

    async def send_approval_notification(self, to_email: str, full_name: str) -> None:
        logger.info(
            "[EMAIL STUB] Approval notification → %s (%s)",
            to_email,
            full_name,
        )

    async def send_password_reset_email(self, to_email: str, full_name: str, token: str) -> None:
        link = f"{self._base_url}/reset-password?token={token}"
        logger.info(
            "[EMAIL STUB] Password reset → %s | link: %s",
            to_email,
            link,
        )
