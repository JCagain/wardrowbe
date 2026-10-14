from datetime import date
from unittest.mock import patch

import httpx
import pytest

from app.services.weather_service import (
    RECORD_CONDITIONS,
    DayWeather,
    WeatherService,
    record_condition_for_code,
)

TODAY = date(2026, 10, 14)


def _resp(json_data: dict, status_code: int = 200, url: str = "https://x/forecast") -> httpx.Response:
    return httpx.Response(status_code, json=json_data, request=httpx.Request("GET", url))


DAILY = {
    "daily": {
        "time": ["2026-10-10"],
        "temperature_2m_max": [24.5],
        "temperature_2m_min": [16.0],
        "weather_code": [61],
    }
}


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "sunny"), (1, "sunny"), (2, "partly_cloudy"), (3, "cloudy"),
        (45, "foggy"), (48, "foggy"), (51, "drizzle"), (55, "drizzle"),
        (56, "sleet"), (67, "sleet"), (61, "rain"), (63, "rain"), (80, "rain"), (81, "rain"),
        (65, "heavy_rain"), (82, "heavy_rain"), (71, "snow"), (77, "snow"), (86, "snow"),
        (95, "thunderstorm"), (99, "thunderstorm"), (1234, None),
    ],
)
def test_record_condition_for_code(code, expected):
    assert record_condition_for_code(code) == expected


def test_every_mapped_condition_is_in_closed_set():
    for code in range(0, 100):
        cond = record_condition_for_code(code)
        assert cond is None or cond in RECORD_CONDITIONS


@pytest.mark.asyncio
async def test_recent_past_uses_forecast_endpoint_with_date_range():
    with patch("httpx.AsyncClient.get", return_value=_resp(DAILY)) as get:
        result = await WeatherService().get_weather_for_date(30.27, 120.15, date(2026, 10, 10), TODAY)
    assert result == DayWeather(temp_high=24.5, temp_low=16.0, condition="rain")
    url = get.call_args.args[0]
    params = get.call_args.kwargs["params"]
    assert url.endswith("/forecast")
    assert params["start_date"] == "2026-10-10"
    assert params["end_date"] == "2026-10-10"


@pytest.mark.asyncio
async def test_old_date_uses_archive_endpoint():
    with patch("httpx.AsyncClient.get", return_value=_resp(DAILY)) as get:
        await WeatherService().get_weather_for_date(30.27, 120.15, date(2025, 1, 5), TODAY)
    assert get.call_args.args[0].endswith("/archive")


@pytest.mark.asyncio
async def test_far_future_returns_none_without_request():
    with patch("httpx.AsyncClient.get") as get:
        result = await WeatherService().get_weather_for_date(30.27, 120.15, date(2026, 11, 30), TODAY)
    assert result is None
    get.assert_not_called()


@pytest.mark.asyncio
async def test_http_error_returns_none():
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("boom")):
        result = await WeatherService().get_weather_for_date(30.27, 120.15, date(2026, 10, 10), TODAY)
    assert result is None


@pytest.mark.asyncio
async def test_all_null_values_return_none():
    empty = {"daily": {"time": ["2026-10-10"], "temperature_2m_max": [None],
                       "temperature_2m_min": [None], "weather_code": [None]}}
    with patch("httpx.AsyncClient.get", return_value=_resp(empty)):
        result = await WeatherService().get_weather_for_date(30.27, 120.15, date(2026, 10, 10), TODAY)
    assert result is None


def test_day_weather_to_dict():
    assert DayWeather(20.0, None, "sunny").to_dict() == {
        "temp_high": 20.0, "temp_low": None, "condition": "sunny",
    }


@pytest.mark.asyncio
async def test_non_dict_json_body_returns_none():
    with patch("httpx.AsyncClient.get", return_value=_resp([1, 2, 3])):
        result = await WeatherService().get_weather_for_date(30.27, 120.15, date(2026, 10, 10), TODAY)
    assert result is None


@pytest.mark.asyncio
async def test_non_numeric_weather_code_gives_none_condition():
    body = {"daily": {"temperature_2m_max": [20.0], "temperature_2m_min": [10.0], "weather_code": ["abc"]}}
    with patch("httpx.AsyncClient.get", return_value=_resp(body)):
        result = await WeatherService().get_weather_for_date(30.27, 120.15, date(2026, 10, 10), TODAY)
    assert result == DayWeather(temp_high=20.0, temp_low=10.0, condition=None)
