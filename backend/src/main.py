"""
시나리오
사용자가 도시·날짜·Cloud LLM을 선택하면 Weather Agent가 MCP get_weather Tool을 먼저
호출합니다. Agent는 Tool Result를 근거로 OpenAI 또는 Gemini에게 옷차림 설명을 요청합니다.
MCP가 실패하거나 선택한 Provider Key가 없으면 성공 응답으로 숨기지 않고 오류를 반환합니다.
"""



import json
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from google import genai
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openai import OpenAI
from pydantic import BaseModel, Field
import psycopg
from redis.asyncio import Redis

MCP_URL = os.getenv("WEATHER_MCP_URL", "http://127.0.0.1:8010/mcp")
app = FastAPI(title="Weather MCP Agent", version="1.0.0")

class WeatherRequest(BaseModel):
    city: str = Field(min_length=1, max_length=60)
    day: Literal["today", "tomorrow"] = "tomorrow"
    provider: Literal["openai", "gemini"] = "openai"

@asynccontextmanager
async def mcp_session():
    async with streamable_http_client(MCP_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session

async def call_weather_tool(city: str, day: str) -> dict:
    async with mcp_session() as session:
        result = await session.call_tool("get_weather", {"city": city, "day": day})
        text = "\n".join(item.text for item in result.content if hasattr(item, "text"))
        if result.isError:
            raise RuntimeError(text or "Weather MCP Tool 호출 실패")
        return json.loads(text)

def generate_answer(provider: str, weather: dict) -> tuple[str, str]:
    prompt = "다음 실제 날씨 데이터만 근거로 한국어 3문장 이내의 날씨와 옷차림을 설명하세요. 데이터를 만들지 마세요.\n" + json.dumps(weather, ensure_ascii=False)
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY를 설정하세요.")
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        response = OpenAI().responses.create(model=model, input=prompt)
        return response.output_text, model
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY를 설정하세요.")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text or "응답 내용이 없습니다.", model

@app.get("/health/live")
def live() -> dict:
    return {"status": "ok", "service": "backend"}

@app.get("/health/ready")
async def ready() -> dict:
    try:
        async with mcp_session() as session:
            tools = [tool.name for tool in (await session.list_tools()).tools]
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Weather MCP 연결 실패: {error}") from error
    return {"status": "ok", "mcp": MCP_URL, "tools": tools}


async def check_redis(url: str) -> dict:
    client = Redis.from_url(url, socket_connect_timeout=5, socket_timeout=5)
    try:
        await client.ping()
        return {"status": "connected", "check": "PING"}
    finally:
        await client.aclose()


async def check_database(url: str) -> dict:
    async with await psycopg.AsyncConnection.connect(url, connect_timeout=5) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT 1")
            row = await cursor.fetchone()
    if row != (1,):
        raise RuntimeError("PostgreSQL SELECT 1 returned an unexpected result")
    return {"status": "connected", "check": "SELECT 1"}


@app.get("/health/dependencies")
async def dependencies() -> dict:
    redis_url = os.getenv("REDIS_URL")
    database_url = os.getenv("DATABASE_URL")
    if not redis_url or not database_url:
        raise HTTPException(status_code=503, detail="REDIS_URL and DATABASE_URL are required")
    result = {}
    for name, check, url in (
        ("redis", check_redis, redis_url),
        ("database", check_database, database_url),
    ):
        try:
            result[name] = await check(url)
        except Exception as error:
            result[name] = {"status": "failed", "error": type(error).__name__}
    if any(item["status"] != "connected" for item in result.values()):
        raise HTTPException(status_code=503, detail=result)
    return result

@app.post("/api/weather")
async def weather_agent(payload: WeatherRequest) -> dict:
    try:
        tool_result = await call_weather_tool(payload.city, payload.day)
        if not tool_result.get("success"):
            raise ValueError(f"날씨 조회 실패: {tool_result}")
        answer, model = generate_answer(payload.provider, tool_result)
        return {"answer": answer, "provider": payload.provider, "model": model, "tool": "get_weather", "tool_result": tool_result}
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
