"""Telegram webhook automatic registration and management."""
import os
import httpx
import logging
from typing import Optional, TypedDict
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class WebhookStatus(TypedDict):
    configured: bool
    url: str
    has_pending_updates: bool
    max_pending_updates: int
    last_error_date: Optional[int]
    last_error_message: str
    expected_url: str


def get_webhook_config() -> tuple[bool, str, str, str]:
    """Get webhook configuration from environment.
    
    Returns:
        Tuple of (token_configured, username, secret, expected_url)
    """
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    username = (os.getenv("TELEGRAM_BOT_USERNAME") or "MunshiHermesAi_Bot").strip().lstrip("@")
    secret = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    public_origin = os.getenv("PUBLIC_API_ORIGIN", "https://munshiai.co.in").rstrip("/")
    expected_url = f"{public_origin}/api/integrations/telegram/webhook"
    
    return bool(token), username, secret, expected_url


def get_webhook_status() -> WebhookStatus:
    """Get current webhook configuration status from Telegram.
    
    Returns:
        WebhookStatus dict with configuration details
    """
    token, username, secret, expected_url = get_webhook_config()
    
    if not token:
        return {
            "configured": False,
            "url": "",
            "has_pending_updates": False,
            "max_pending_updates": 0,
            "last_error_date": None,
            "last_error_message": "TELEGRAM_BOT_TOKEN not configured",
            "expected_url": expected_url,
        }
    
    if not secret:
        return {
            "configured": False,
            "url": expected_url,
            "has_pending_updates": False,
            "max_pending_updates": 0,
            "last_error_date": None,
            "last_error_message": "TELEGRAM_WEBHOOK_SECRET not configured",
            "expected_url": expected_url,
        }
    
    try:
        async def fetch_webhook_info() -> WebhookStatus:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.telegram.org/bot{token}/getWebhookInfo"
                )
                data = response.json()
                
                if not data.get("ok"):
                    return {
                        "configured": False,
                        "url": expected_url,
                        "has_pending_updates": False,
                        "max_pending_updates": 0,
                        "last_error_date": None,
                        "last_error_message": f"getWebhookInfo failed: {data.get('description', 'Unknown error')}",
                        "expected_url": expected_url,
                    }
                
                result = data.get("result", {})
                return {
                    "configured": True,
                    "url": result.get("url", ""),
                    "has_pending_updates": result.get("has_sensitive_updates", False) or False,  # Not accurate, Telegram doesn't provide this
                    "max_pending_updates": result.get("pending_update_count", 0),
                    "last_error_date": result.get("last_error_date"),
                    "last_error_message": result.get("last_error_message", ""),
                    "expected_url": expected_url,
                }
        
        import asyncio
        status = asyncio.run(fetch_webhook_info())
        logger.info(f"Webhook status check: configured={status['configured']}, url={status['url']}")
        return status
        
    except httpx.RequestError as exc:
        logger.error(f"Failed to check webhook status: {exc}")
        return {
            "configured": False,
            "url": expected_url,
            "has_pending_updates": False,
            "max_pending_updates": 0,
            "last_error_date": None,
            "last_error_message": f"Network error: {str(exc)}",
            "expected_url": expected_url,
        }


def register_webhook() -> tuple[bool, str]:
    """Register webhook with Telegram.
    
    Returns:
        Tuple of (success, message)
    """
    token, username, secret, expected_url = get_webhook_config()
    
    if not token:
        return False, "TELEGRAM_BOT_TOKEN not configured"
    
    if not secret:
        return False, "TELEGRAM_WEBHOOK_SECRET not configured"
    
    try:
        async def register() -> tuple[bool, str]:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/setWebhook",
                    json={
                        "url": expected_url,
                        "secret_token": secret,
                    }
                )
                data = response.json()
                
                if not data.get("ok"):
                    return False, f"setWebhook failed: {data.get('description', 'Unknown error')}"
                
                logger.info(f"Webhook successfully registered: {expected_url}")
                return True, f"Webhook registered successfully at {expected_url}"
        
        success, message = asyncio.run(register())
        return success, message
        
    except httpx.RequestError as exc:
        logger.error(f"Failed to register webhook: {exc}")
        return False, f"Network error while registering webhook: {str(exc)}"
    except Exception as exc:
        logger.error(f"Unexpected error registering webhook: {exc}")
        return False, f"Unexpected error: {str(exc)}"


def auto_register_webhook() -> None:
    """Auto-register webhook on API startup.
    
    This is called automatically when the FastAPI app starts up.
    Only logs results, doesn't raise exceptions.
    """
    try:
        success, message = register_webhook()
        if success:
            logger.info(f"✅ Telegram webhook auto-registered: {message}")
        else:
            logger.warning(f"⚠️ Telegram webhook registration: {message}")
    except Exception as exc:
        logger.error(f"❌ Failed to auto-register webhook: {exc}")
