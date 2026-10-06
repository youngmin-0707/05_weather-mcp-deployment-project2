from unittest.mock import Mock

import main


def test_get_weather_uses_forecast(monkeypatch):
    geo = Mock()
    geo.json.return_value = {"results": [{"name": "Seoul", "latitude": 37.5, "longitude": 127.0}]}
    forecast = Mock()
    forecast.json.return_value = {"daily": {
        "time": ["2026-10-02", "2026-10-03"],
        "temperature_2m_max": [20, 21],
        "temperature_2m_min": [10, 11],
        "precipitation_probability_max": [0, 30],
        "weather_code": [0, 3],
    }}
    client = Mock()
    client.get.side_effect = [geo, forecast]
    context = Mock()
    context.__enter__ = Mock(return_value=client)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(main.httpx, "Client", lambda **_: context)

    result = main.get_weather("Seoul", "tomorrow")

    assert result["success"] is True
    assert result["date"] == "2026-10-03"
    assert result["temperature_max"] == 21
    assert client.get.call_count == 2
