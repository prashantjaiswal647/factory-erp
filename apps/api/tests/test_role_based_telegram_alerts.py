from types import SimpleNamespace
from unittest.mock import patch

from models import Factory
from services.telegram_delivery import (
    get_owner_telegram_targets,
    get_sub_owner_telegram_targets,
    send_owner_action_alert,
)


def test_owner_targets_use_legacy_factory_fallback():
    db = SimpleNamespace()
    binding_query = SimpleNamespace(filter=lambda *args: SimpleNamespace(all=lambda: []))
    factory_query = SimpleNamespace(filter=lambda *args: SimpleNamespace(first=lambda: Factory(id=1, name="A", telegram_chat_id="legacy-owner")))
    db.query = lambda model: binding_query if model.__name__ == "TelegramUserBinding" else factory_query

    assert get_owner_telegram_targets(db, 1) == ["legacy-owner"]


def test_sub_owner_action_alert_goes_to_owner_only():
    factory = Factory(id=1, name="Factory A")
    actor = SimpleNamespace(
        id=12,
        factory_id=1,
        role="Sub-Owner",
        full_name="Sub Owner",
        username="sub-owner",
    )
    db = SimpleNamespace()
    db.query = lambda model: SimpleNamespace(filter=lambda *args: SimpleNamespace(first=lambda: factory))

    with patch("services.telegram_delivery.get_owner_telegram_targets", return_value=["owner-chat"]), patch(
        "services.telegram_delivery.send_message_to_targets", return_value=1
    ) as sender:
        assert send_owner_action_alert(db, 1, actor, "UPDATED", "Inventory", 10, "Stock updated") == 1
        assert sender.call_args.args[2] == ["owner-chat"]


def test_owner_action_does_not_alert_sub_owner():
    actor = SimpleNamespace(factory_id=1, role="Owner")
    assert send_owner_action_alert(SimpleNamespace(), 1, actor, "UPDATED", "Inventory", 10, "Stock updated") == 0
