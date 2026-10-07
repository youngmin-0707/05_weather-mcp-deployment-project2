"""
시나리오
수강생이 도시·날짜·Cloud LLM을 선택해 Weather Agent를 실행합니다. 화면은 최종 답변뿐
아니라 실제 호출한 MCP Tool 이름과 Open-Meteo 결과를 함께 보여 주어 근거를 확인합니다.
"""

import os
import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
st.set_page_config(page_title="Weather MCP Agent", page_icon="🌦️", layout="wide")
st.sidebar.title("학습 메뉴")
page = st.sidebar.radio("이동", ["Weather Agent", "구조 이해", "Health Check"])
st.title("Weather MCP Deployment Project OK")




if page == "Weather Agent":
    city = st.text_input("도시", "서울")
    day_label = st.radio("날짜", ["내일", "오늘"], horizontal=True)
    provider = st.selectbox("Cloud LLM", ["openai", "gemini"])
    if st.button("실제 날씨 조회", type="primary", use_container_width=True):
        try:
            response = requests.post(f"{BACKEND_URL}/api/weather", json={"city": city, "day": "tomorrow" if day_label == "내일" else "today", "provider": provider}, timeout=90)
            response.raise_for_status()
            result = response.json()
            st.success(result["answer"])
            st.caption(f"{result['provider']} · {result['model']} · MCP Tool: {result['tool']}")
            with st.expander("실제 Open-Meteo Tool Result", expanded=True):
                st.json(result["tool_result"])
        except requests.RequestException as error:
            detail = error.response.text if error.response is not None else str(error)
            st.error(f"Backend 요청 실패: {detail}")
elif page == "구조 이해":
    st.code("Browser → Frontend → Backend Agent → Weather MCP → Open-Meteo\n                                  └→ OpenAI 또는 Gemini")
    st.info("MCP 8010은 Docker 내부에서만 사용하며 Host에는 공개하지 않습니다.")
else:
    try:
        response = requests.get(f"{BACKEND_URL}/health/ready", timeout=5)
        response.raise_for_status()
        st.success("Backend와 Weather MCP가 준비되었습니다.")
        st.json(response.json())
    except requests.RequestException as error:
        st.error(f"Readiness 실패: {error}")
