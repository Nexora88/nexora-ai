"""
Nexora AI — Hava durumu (Open-Meteo, key yok)
Kart + ajan mesajı için structured data.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"

WMO = {
    0: "Açık",
    1: "Çoğunlukla açık",
    2: "Parçalı bulutlu",
    3: "Kapalı",
    45: "Sis",
    48: "Kırağılı sis",
    51: "Hafif çise",
    61: "Yağmur",
    63: "Orta yağmur",
    65: "Şiddetli yağmur",
    71: "Kar",
    80: "Sağanak",
    95: "Gök gürültülü",
}


async def geocode(city: str, lang: str = "tr") -> Optional[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            GEOCODE,
            params={"name": city, "count": 1, "language": lang, "format": "json"},
        )
        r.raise_for_status()
        results = (r.json() or {}).get("results") or []
        if not results:
            return None
        x = results[0]
        return {
            "name": x.get("name"),
            "country": x.get("country"),
            "lat": x.get("latitude"),
            "lon": x.get("longitude"),
            "timezone": x.get("timezone"),
        }


async def forecast(lat: float, lon: float, timezone: str = "auto") -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            FORECAST,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "timezone": timezone or "auto",
                "forecast_days": 3,
            },
        )
        r.raise_for_status()
        return r.json()


async def weather_card(city: str) -> Dict[str, Any]:
    place = await geocode(city)
    if not place:
        return {"ok": False, "error": f"Şehir bulunamadı: {city}"}

    data = await forecast(place["lat"], place["lon"], place.get("timezone") or "auto")
    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    code = int(cur.get("weather_code") or 0)

    card = {
        "ok": True,
        "city": place["name"],
        "country": place.get("country"),
        "temp_c": cur.get("temperature_2m"),
        "humidity": cur.get("relative_humidity_2m"),
        "wind_kmh": cur.get("wind_speed_10m"),
        "condition": WMO.get(code, f"Kod {code}"),
        "weather_code": code,
        "daily": [],
    }
    times = daily.get("time") or []
    for i, day in enumerate(times[:3]):
        card["daily"].append(
            {
                "date": day,
                "max": (daily.get("temperature_2m_max") or [None])[i],
                "min": (daily.get("temperature_2m_min") or [None])[i],
                "condition": WMO.get(
                    int((daily.get("weather_code") or [0])[i] or 0), "—"
                ),
            }
        )

    # Ajan tarzı kısa mesaj
    card["agent_message"] = (
        f"Nexora Hava · {card['city']}: şu an {card['temp_c']}°C, {card['condition']}. "
        f"Nem %{card['humidity']}, rüzgar {card['wind_kmh']} km/h."
    )
    return card
