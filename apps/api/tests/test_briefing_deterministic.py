from services.briefing_service import build_briefing, render_morning_briefing_message
from tests.briefing_test_utils import BRIEFING_DATE, make_briefing_db, seed_two_factories


def _sanitize_for_comparison(res):
    import copy
    r = copy.deepcopy(res)
    if "ai_observability" in r and r["ai_observability"] is not None:
        r["ai_observability"]["generation_time"] = 0
        r["ai_observability"]["cache_hit"] = False
    if "snapshot" in r:
        for sec in ("cost", "profit", "wastage"):
            if sec in r["snapshot"] and r["snapshot"][sec] is not None:
                if isinstance(r["snapshot"][sec], dict):
                    if "computed_at" in r["snapshot"][sec]:
                        r["snapshot"][sec]["computed_at"] = ""
                    if "created_at" in r["snapshot"][sec]:
                        r["snapshot"][sec]["created_at"] = ""
    return r


def test_briefing_is_deterministic_and_matches_required_format():
    engine, db = make_briefing_db()
    try:
        owner, _ = seed_two_factories(db)
        first = build_briefing(db, owner.factory_id, BRIEFING_DATE, owner.full_name, "en")
        second = build_briefing(db, owner.factory_id, BRIEFING_DATE, owner.full_name, "en")

        assert _sanitize_for_comparison(first) == _sanitize_for_comparison(second)
        assert first["message_text"] == render_morning_briefing_message(first["snapshot"], "Owner A", "en")
        assert first["message_text"] == (
            "Good Morning Owner A\n\n"
            "Production Yesterday\n"
            "Produced: 70\n"
            "Target: 100\n"
            "Gap: 30\n\n"
            "Workers\n"
            "Present: 1\n"
            "Absent: 1\n\n"
            "💵 Sales Yesterday\n"
            "Invoices: 1\n"
            "Sales: ₹12,000.00\n"
            "Collections: ₹2,500.00\n"
            "Outstanding: ₹125,000.00\n\n"
            "🏭 Factory Health\n"
            "Score: 48/100\n"
            "Status: CRITICAL\n"
            "Biggest Strength: Cost\n"
            "Biggest Risk: Attendance\n\n"
            "💰 Profit Intelligence\n"
            "Revenue: ₹12,000\n"
            "Cost: ₹0\n"
            "Profit: ₹12,000\n"
            "Margin: 100.0%\n"
            "Risk: Collections\n\n"
            "⚠ Risks\n\n"
            "Critical:\n"
            "Low Stock: Bottom Roll\n"
            "2 days left\n\n"
            "Warning:\n"
            "Outstanding Alert: Alpha Buyer\n"
            "₹125,000.00\n\n"
            "Info:\n"
            "Low Stock: Blank Stock\n"
            "7 days left\n\n"
            "* Munshi AI"
        )
        assert [item["severity"] for item in first["risk_items"]] == ["critical", "warning", "info"]
        assert first["snapshot"]["sales"] == {
            "invoice_count": 1,
            "amount": 12000,
            "collections_received": 2500,
            "outstanding_amount": 125000,
        }
    finally:
        db.close()
        engine.dispose()


def test_hindi_rendering_is_byte_for_byte_deterministic():
    engine, db = make_briefing_db()
    try:
        owner, _ = seed_two_factories(db)
        result = build_briefing(db, owner.factory_id, BRIEFING_DATE, owner.full_name, "hi")
        expected = (
            "सुप्रभात Owner A जी\n\n"
            "कल का उत्पादन\n"
            "उत्पादन: 70\n"
            "लक्ष्य: 100\n"
            "अंतर: 30\n\n"
            "कर्मचारी\n"
            "उपस्थित: 1\n"
            "अनुपस्थित: 1\n\n"
            "💵 कल की बिक्री\n"
            "चालान: 1\n"
            "बिक्री: ₹12,000.00\n"
            "प्राप्त भुगतान: ₹2,500.00\n"
            "बकाया राशि: ₹125,000.00\n\n"
            "🏭 फैक्ट्री स्वास्थ्य\n"
            "स्कोर: 48/100\n"
            "स्थिति: CRITICAL\n"
            "सबसे बड़ी ताकत: Cost\n"
            "सबसे बड़ा जोखिम: Attendance\n\n"
            "💰 लाभ जानकारी\n"
            "राजस्व: ₹12,000\n"
            "लागत: ₹0\n"
            "लाभ: ₹12,000\n"
            "मार्जिन: 100.0%\n"
            "जोखिम: Collections\n\n"
            "⚠ ध्यान देने योग्य बातें\n\n"
            "अत्यावश्यक:\n"
            "कम स्टॉक: बॉटम रोल\n"
            "2 दिन शेष\n\n"
            "चेतावनी:\n"
            "बकाया चेतावनी: Alpha Buyer\n"
            "₹125,000.00\n\n"
            "जानकारी:\n"
            "कम स्टॉक: ब्लैंक स्टॉक\n"
            "7 दिन शेष\n\n"
            "* Munshi AI"
        )
        assert result["language"] == "hi"
        assert result["message_text"].encode("utf-8") == expected.encode("utf-8")
    finally:
        db.close()
        engine.dispose()


def test_hinglish_rendering_is_byte_for_byte_deterministic():
    engine, db = make_briefing_db()
    try:
        owner, _ = seed_two_factories(db)
        first = build_briefing(db, owner.factory_id, BRIEFING_DATE, owner.full_name, "hinglish")
        second = build_briefing(db, owner.factory_id, BRIEFING_DATE, owner.full_name, "hinglish")
        expected = (
            "Good Morning Owner A Ji\n\n"
            "Kal ka Production\n"
            "Produced: 70\n"
            "Target: 100\n"
            "Gap: 30\n\n"
            "Workers\n"
            "Present: 1\n"
            "Absent: 1\n\n"
            "💵 Sales Yesterday\n"
            "Invoices: 1\n"
            "Sales: ₹12,000.00\n"
            "Collections: ₹2,500.00\n"
            "Outstanding: ₹125,000.00\n\n"
            "🏭 Factory Health\n"
            "Score: 48/100\n"
            "Status: CRITICAL\n"
            "Sabse Badi Takat: Cost\n"
            "Sabse Bada Risk: Attendance\n\n"
            "💰 Profit Intelligence\n"
            "Revenue: ₹12,000\n"
            "Cost: ₹0\n"
            "Profit: ₹12,000\n"
            "Margin: 100.0%\n"
            "Risk: Collections\n\n"
            "⚠ Dhyan Dene Yogya Baatein\n\n"
            "Critical:\n"
            "Low Stock: Bottom Roll\n"
            "2 din baki\n\n"
            "Warning:\n"
            "Outstanding Alert: Alpha Buyer\n"
            "₹125,000.00\n\n"
            "Info:\n"
            "Low Stock: Blank Stock\n"
            "7 din baki\n\n"
            "* Munshi AI"
        )
        assert _sanitize_for_comparison(first) == _sanitize_for_comparison(second)
        assert first["language"] == "hinglish"
        assert first["message_text"].encode("utf-8") == expected.encode("utf-8")
    finally:
        db.close()
        engine.dispose()


def test_low_stock_and_outstanding_risks_are_detected_and_ordered():
    engine, db = make_briefing_db()
    try:
        owner, _ = seed_two_factories(db)
        result = build_briefing(db, owner.factory_id, BRIEFING_DATE, owner.full_name)

        assert result["risk_items"] == [
            {
                "severity": "critical",
                "type": "low_stock",
                "label": "Bottom Roll",
                "days_left": 2,
                "message": "Bottom Roll 2 days left",
            },
            {
                "severity": "warning",
                "type": "outstanding",
                "label": "Alpha Buyer",
                "pending_amount": 125000,
                "message": "Alpha Buyer outstanding payment",
            },
            {
                "severity": "info",
                "type": "low_stock",
                "label": "Blank Stock",
                "days_left": 7,
                "message": "Blank Stock 7 days left",
            },
        ]
    finally:
        db.close()
        engine.dispose()


def test_factory_a_never_uses_factory_b_sales_or_risks():
    engine, db = make_briefing_db()
    try:
        owner_a, _ = seed_two_factories(db)
        result = build_briefing(db, owner_a.factory_id, BRIEFING_DATE, owner_a.full_name)

        assert result["snapshot"]["sales"]["amount"] == 12000
        assert result["snapshot"]["sales"]["invoice_count"] == 1
        assert "654,321" not in result["message_text"]
        assert "Secret Beta Buyer" not in result["message_text"]
        assert all(item["label"] != "Secret Beta Buyer" for item in result["risk_items"])
    finally:
        db.close()
        engine.dispose()
