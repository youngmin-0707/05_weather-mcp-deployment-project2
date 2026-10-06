"""
시나리오
사용자가 선택한 도시의 실제 날씨를 Open-Meteo에서 조회하는 MCP Tool Server입니다.
Backend만 Docker 내부 주소 weather-mcp:8010으로 접근하며 Host에는 8010을 공개하지 않습니다.
도시를 좌표로 변환한 뒤 오늘 또는 내일의 최고·최저 기온과 강수 확률을 반환합니다.
"""

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse

mcp = FastMCP("weather-tools", host="0.0.0.0", port=8010, stateless_http=True, json_response=True)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def get_weather(city: str, day: str = "tomorrow") -> dict:
    """도시 이름과 today 또는 tomorrow를 받아 실제 일별 날씨를 반환합니다."""
    if day not in {"today", "tomorrow"}:
        raise ValueError("day는 today 또는 tomorrow여야 합니다.")
    with httpx.Client(timeout=15) as client:
        geo = client.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1, "language": "ko", "format": "json"})
        geo.raise_for_status()
        places = geo.json().get("results", [])
        if not places:
            return {"success": False, "error": "CITY_NOT_FOUND", "city": city}
        place = places[0]
        forecast = client.get("https://api.open-meteo.com/v1/forecast", params={"latitude": place["latitude"], "longitude": place["longitude"], "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code", "timezone": "auto", "forecast_days": 2})
        forecast.raise_for_status()
    daily = forecast.json()["daily"]
    index = 0 if day == "today" else 1
    return {"success": True, "city": place["name"], "country": place.get("country"), "date": daily["time"][index], "temperature_max": daily["temperature_2m_max"][index], "temperature_min": daily["temperature_2m_min"][index], "precipitation_probability": daily["precipitation_probability_max"][index], "weather_code": daily["weather_code"][index], "source": "Open-Meteo"}

@mcp.custom_route("/health", methods=["GET"])
async def health(_request):
    return JSONResponse({"status": "ok", "service": "weather-mcp"})

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
