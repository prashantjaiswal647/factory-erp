from services.briefing_translations import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES


COST_SPIKE_TRANSLATIONS = {
    "en": {
        "title": "⚠ Cost Spike Alert",
        "cost_per_cup": "Cost Per Cup",
        "seven_day_average": "7 Day Average",
        "increase": "Increase",
        "primary_driver": "Primary Driver",
        "drivers": {
            "Material Cost": "Material Cost",
            "Labour Cost": "Labour Cost",
            "Electricity Cost": "Electricity Cost",
            "Overhead Cost": "Overhead Cost",
        },
    },
    "hi": {
        "title": "⚠ लागत बढ़ने की चेतावनी",
        "cost_per_cup": "प्रति कप लागत",
        "seven_day_average": "7 दिन का औसत",
        "increase": "वृद्धि",
        "primary_driver": "मुख्य कारण",
        "drivers": {
            "Material Cost": "सामग्री लागत",
            "Labour Cost": "श्रम लागत",
            "Electricity Cost": "बिजली लागत",
            "Overhead Cost": "ओवरहेड लागत",
        },
    },
    "hinglish": {
        "title": "⚠ Cost Spike Alert",
        "cost_per_cup": "Cost Per Cup",
        "seven_day_average": "7 Din ka Average",
        "increase": "Badhotri",
        "primary_driver": "Mukhya Karan",
        "drivers": {
            "Material Cost": "Material Cost",
            "Labour Cost": "Labour Cost",
            "Electricity Cost": "Electricity Cost",
            "Overhead Cost": "Overhead Cost",
        },
    },
}


def cost_spike_translations_for(language: str | None) -> dict:
    resolved = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    return COST_SPIKE_TRANSLATIONS[resolved]
