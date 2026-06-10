"""Tests for Telegram webhook management and self-service."""
import pytest
from unittest.mock import patch, MagicMock
import httpx
import os


@pytest.fixture
def mock_httpx_post(monkeypatch):
    """Mock httpx.post for testing webhook registration."""
    async def mock_post(*args, **kwargs):
        # Check if it's a getWebhookInfo or setWebhook call
        url = args[0] if args else (kwargs.get('url', ''))
        
        if 'getWebhookInfo' in url:
            # Return configured webhook
            return MagicMock(
                json=lambda: {
                    "ok": True,
                    "result": {
                        "url": "https://munshiai.co.in/api/integrations/telegram/webhook",
                        "pending_update_count": 0,
                        "last_error_date": None,
                        "last_error_message": "",
                    }
                }
            )
        elif 'setWebhook' in url:
            # Return successful registration
            return MagicMock(
                json=lambda: {
                    "ok": True,
                    "result": True
                }
            )
        return MagicMock(json=lambda: {"ok": False, "description": "Unknown"})
    
    import httpx
    monkeypatch.setattr(httpx.AsyncClient, 'get', mock_post)
    monkeypatch.setattr(httpx.AsyncClient, 'post', mock_post)


def test_auto_register_webhook_env_vars_configured(monkeypatch, mock_httpx_post):
    """Test that webhook gets registered when env vars are configured."""
    from services.telegram_webhook_manager import get_webhook_config, register_webhook
    
    # Set up env vars
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "TestBot")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.setenv("PUBLIC_API_ORIGIN", "https://munshiai.co.in")
    
    token, username, secret, expected_url = get_webhook_config()
    
    assert token == "123456:test-token"
    assert username == "TestBot"
    assert secret == "webhook-secret"
    assert expected_url == "https://munshiai.co.in/api/integrations/telegram/webhook"


def test_register_webhook_success(monkeypatch, mock_httpx_post):
    """Test successful webhook registration."""
    from services.telegram_webhook_manager import register_webhook
    
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    
    success, message = register_webhook()
    
    assert success is True
    assert "successfully" in message.lower()


def test_register_webhook_missing_token(monkeypatch):
    """Test webhook registration fails without token."""
    from services.telegram_webhook_manager import register_webhook, get_webhook_config
    
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    # Don't set TELEGRAM_BOT_TOKEN
    
    token, username, secret, expected_url = get_webhook_config()
    
    assert token is False
    assert username == "MunshiHermesAi_Bot"
    assert secret == "webhook-secret"
    
    success, message = register_webhook()
    assert success is False
    assert "not configured" in message.lower()


def test_get_webhook_status_not_configured(monkeypatch):
    """Test webhook status when not configured."""
    from services.telegram_webhook_manager import get_webhook_status
    
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    
    status = get_webhook_status()
    
    assert status["configured"] is False
    assert status["last_error_message"] == "TELEGRAM_BOT_TOKEN not configured"
    assert status["expected_url"] == "https://munshiai.co.in/api/integrations/telegram/webhook"


def test_endpoint_register_webhook_success(admin_client, monkeypatch):
    """Test Super Admin can register webhook via endpoint."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    
    response = admin_client.post(
        "/api/integrations/telegram/register-webhook",
        json={"use_default": True}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "successfully" in data["message"].lower()
    assert "webhook" in data["webhook_url"]


def test_endpoint_register_webhook_missing_creds(admin_client, monkeypatch):
    """Test Super Admin gets error when missing credentials."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    
    response = admin_client.post(
        "/api/integrations/telegram/register-webhook",
        json={"use_default": True}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "not configured" in data["message"].lower()


def test_endpoint_register_webhook_supervisor_rejected(
    supervisor_client, monkeypatch
):
    """Test regular users cannot register webhook."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    
    response = supervisor_client.post(
        "/api/integrations/telegram/register-webhook",
        json={"use_default": True}
    )
    
    assert response.status_code == 403


def test_webhook_configured_in_status_endpoint(owner_client, monkeypatch):
    """Test webhook configuration status appears in user status."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    
    with patch('routers.integrations.get_webhook_status') as mock_status:
        mock_status.return_value = {
            "configured": True,
            "url": "https://munshiai.co.in/api/integrations/telegram/webhook",
            "has_pending_updates": False,
            "max_pending_updates": 0,
            "last_error_date": None,
            "last_error_message": "",
            "expected_url": "https://munshiai.co.in/api/integrations/telegram/webhook",
        }
        
        response = owner_client.get("/api/integrations/telegram/status")
    
    assert response.status_code == 200
    data = response.json()
    assert "webhook_configured" in data
    assert data["webhook_configured"] is True


def test_diagnostic_endpoint_includes_webhook_info(
    super_admin_client, monkeypatch, mock_httpx_post
):
    """Test diagnostics endpoint returns webhook configuration info."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    
    response = super_admin_client.get("/api/integrations/telegram/diagnostics")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check required fields
    required_fields = [
        "bot_token_configured",
        "webhook_secret_configured",
        "expected_webhook_url",
        "webhook_configured",
        "webhook_url",
        "pending_update_count",
        "last_error_message",
    ]
    
    for field in required_fields:
        assert field in data, f"Missing field: {field}"
    
    # Check values
    assert data["bot_token_configured"] is True
    assert data["webhook_secret_configured"] is True
    assert data["webhook_configured"] is True
    assert "bot" in data["telegram_bot_username"]
