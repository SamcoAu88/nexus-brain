"""
Brisbane Weather + Smart Postie Guard

Uses Open-Meteo (free, no API key) for Boondall/Brisbane conditions and
assesses rider-safety risks for a motorcycle postie: rain, wind gusts,
UV and extreme temperatures.
"""

import logging
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Boondall, Brisbane QLD
LATITUDE = -27.3436
LONGITUDE = 153.0592

# Rider-safety thresholds for a motorcycle postie
RAIN_PROB_WARN = 50        # % chance of rain
WIND_WARN_KMH = 30         # sustained wind
GUST_WARN_KMH = 40         # gusts — the real bike killer
UV_WARN = 8                # QLD sun is brutal
HEAT_WARN_C = 35
COLD_WARN_C = 5


def get_today_weather() -> Optional[Dict]:
    """
    Fetch today's forecast for Boondall from Open-Meteo.

    Returns dict with temp_min/max, rain_prob, wind_max, gusts_max, uv_max,
    and rain_hours (delivery-window hours with >=40% rain chance), or None.
    """
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "daily": (
                    "temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max,wind_speed_10m_max,"
                    "wind_gusts_10m_max,uv_index_max"
                ),
                "hourly": "precipitation_probability",
                "timezone": "Australia/Brisbane",
                "forecast_days": 1,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        daily = data["daily"]
        weather = {
            "temp_max": daily["temperature_2m_max"][0],
            "temp_min": daily["temperature_2m_min"][0],
            "rain_prob": daily["precipitation_probability_max"][0] or 0,
            "wind_max": daily["wind_speed_10m_max"][0] or 0,
            "gusts_max": daily["wind_gusts_10m_max"][0] or 0,
            "uv_max": daily["uv_index_max"][0] or 0,
        }

        # Which delivery-window hours (6:00–18:00) have >=40% rain chance?
        hourly_probs = data.get("hourly", {}).get("precipitation_probability", [])
        rain_hours = [
            h for h in range(6, min(19, len(hourly_probs)))
            if (hourly_probs[h] or 0) >= 40
        ]
        weather["rain_hours"] = rain_hours

        logger.info(
            f"🌤 Boondall today: {weather['temp_min']}–{weather['temp_max']}°C, "
            f"rain {weather['rain_prob']}%, gusts {weather['gusts_max']} km/h, UV {weather['uv_max']}"
        )
        return weather

    except Exception as e:
        logger.error(f"Weather fetch failed: {e}")
        return None


def assess_postie_risk(weather: Dict) -> List[str]:
    """Smart Postie Guard: rider-safety warnings from today's conditions."""
    warnings = []

    if weather["rain_prob"] >= RAIN_PROB_WARN:
        hours = weather.get("rain_hours", [])
        window = f" (worst around {hours[0]}:00–{hours[-1] + 1}:00)" if hours else ""
        warnings.append(
            f"🌧 Rain risk {weather['rain_prob']}%{window} — wet roads, brake early, "
            "watch painted lines and manhole covers"
        )

    if weather["gusts_max"] >= GUST_WARN_KMH:
        warnings.append(
            f"💨 Wind gusts up to {weather['gusts_max']:.0f} km/h — grip firm, "
            "expect side-blasts between houses and on open stretches"
        )
    elif weather["wind_max"] >= WIND_WARN_KMH:
        warnings.append(
            f"💨 Sustained wind {weather['wind_max']:.0f} km/h — stay loose on the bars"
        )

    if weather["uv_max"] >= UV_WARN:
        warnings.append(
            f"☀️ UV index {weather['uv_max']:.0f} (extreme) — sunscreen on neck and "
            "hands before you head out, reapply at lunch"
        )

    if weather["temp_max"] >= HEAT_WARN_C:
        warnings.append(
            f"🥵 {weather['temp_max']:.0f}°C peak — hydrate every stop, heat fatigue "
            "sneaks up fast in the vest"
        )

    if weather["temp_min"] <= COLD_WARN_C:
        warnings.append(
            f"🥶 {weather['temp_min']:.0f}°C early — cold tyres for the first 10 mins, "
            "gentle on corners"
        )

    return warnings
