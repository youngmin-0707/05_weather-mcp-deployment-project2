FROM python:3.12-slim
WORKDIR /app
COPY requirements/runtime.txt requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip && python -m pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
CMD ["streamlit", "run", "src/app.py", "--server.address=0.0.0.0", "--server.port=8501"]

