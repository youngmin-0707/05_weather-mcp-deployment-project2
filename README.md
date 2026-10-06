# Weather MCP deployment

브라우저 → Frontend(Streamlit 8501) → Backend(FastAPI 8000) → Weather MCP(8010) → Open-Meteo 순서로 동작합니다. Backend는 선택한 LLM을 호출합니다. 배포 시 세 서비스는 서로 다른 EC2에서 실행됩니다.

## 폴더 구조

GitHub 참조 저장소의 서비스별 구조를 적용했습니다. 각 서비스는 다음 경로를 사용합니다.

```text
backend/, frontend/, mcp_server/
├─ config/        .env, .env.example, .env.docker, .env.docker.example
├─ deploy/        compose.yml, Dockerfile, Dockerfile.dockerignore
├─ requirements/  runtime.txt, test.txt
├─ src/           애플리케이션 코드
├─ tests/         서비스 테스트
└─ .venv/         로컬 가상환경 (Git 제외)
```

`config/.env`는 로컬 Python 실행용입니다. Compose는 `config/.env.docker`를 읽고, Backend는 `config/.env`도 함께 읽습니다. 실제 `.env`와 `.env.docker`는 Git에서 제외됩니다. 예시 파일을 복사한 뒤 현재 실행 위치에서 접근 가능한 주소와 API 키를 설정하세요. 기존 로컬 `.env` 값은 각 `config/`로 이동했습니다.

## 로컬 Python 실행 (PowerShell)

각 명령은 프로젝트 루트에서 별도 터미널로 실행합니다. Python 3.12를 사용하고, 최초 한 번 각 `.venv`에 `requirements/runtime.txt`를 설치하세요.

```powershell
cd mcp_server
.\.venv\Scripts\python.exe -m pip install -r requirements/runtime.txt
.\.venv\Scripts\python.exe -m src.server
```

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements/runtime.txt
Get-Content config/.env | ForEach-Object { if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') } }
.\.venv\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
.\.venv\Scripts\python.exe -m pip install -r requirements/runtime.txt
Get-Content config/.env | ForEach-Object { if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') } }
.\.venv\Scripts\python.exe -m streamlit run src/app.py --server.address 127.0.0.1 --server.port 8501
```

서비스를 MCP → Backend → Frontend 순서로 시작합니다. `WEATHER_MCP_URL`과 `BACKEND_URL`은 실행 환경에서 실제로 접근 가능한 주소로 설정합니다.

## Docker Compose 실행

Compose 파일은 서비스별로 독립 실행됩니다. 로컬 Docker Desktop에서 세 Compose를 동시에 실행하려면 Backend의 `config/.env.docker`에 `WEATHER_MCP_URL=http://host.docker.internal:8010/mcp`, Frontend의 `config/.env.docker`에 `BACKEND_URL=http://host.docker.internal:8000`을 설정합니다.

```powershell
docker compose -f mcp_server/deploy/compose.yml config --quiet
docker compose -f backend/deploy/compose.yml config --quiet
docker compose -f frontend/deploy/compose.yml config --quiet

docker compose -f mcp_server/deploy/compose.yml up -d --build
docker compose -f backend/deploy/compose.yml up -d --build
docker compose -f frontend/deploy/compose.yml up -d --build
```

접속 주소는 `http://127.0.0.1:8501`입니다. 실행 상태는 다음과 같이 확인합니다.

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Invoke-WebRequest http://127.0.0.1:8501/_stcore/health
```

## CI

`.github/workflows/`의 세 워크플로가 해당 서비스 변경 시 `requirements/test.txt` 설치, Python 문법·테스트 검사, Compose 설정 검사, 이미지 빌드를 수행합니다. Frontend CI는 컨테이너 healthcheck도 기다립니다. CI에서는 실제 API 키와 AWS 연결을 사용하지 않습니다.

## 자동 배포 (CD)

`main`에 서비스 코드나 워크플로가 push되면 해당 CI 성공 후 서비스별 GitHub Environment를 사용해 각자의 EC2에 자동 배포합니다. Environment 이름은 Backend `backend`, Frontend `frontend`, MCP `MCP`입니다. PR에서는 CI만 실행하고 수동 `workflow_dispatch`에서는 CI 후 배포도 실행합니다. 각 배포는 해당 서비스의 Compose만 실행하며 상태를 검사합니다. 한 서비스의 배포가 겹치면 순차 실행합니다. Environment에 승인 규칙이 있으면 승인 후 진행됩니다.

각 Environment에는 기존에 등록된 Secret 4개(`AWS_HOST`, `AWS_USER`, `AWS_SSH_PRIVATE_KEY`, `AWS_SSH_KNOWN_HOSTS`)를 사용합니다. 각 `AWS_HOST`는 해당 서비스의 EC2를 가리켜야 합니다.

각 EC2에는 Docker Compose와 `curl`이 필요합니다. 첫 배포 전에 해당 EC2의 `~/weather-mcp-deployment/<서비스>/config/.env.docker`를 준비하세요. Backend EC2에는 `backend/config/.env`도 필요하며 API 키를 여기에 설정합니다. 이 파일들은 Git과 배포 묶음에 포함되지 않고 배포 시 유지됩니다.

Backend EC2의 `backend/config/.env.docker`에는 `WEATHER_MCP_URL=http://<MCP EC2 사설 IP>:8010/mcp`를, Frontend EC2의 `frontend/config/.env.docker`에는 `BACKEND_URL=http://<Backend EC2 사설 IP>:8000`을 설정합니다. 세 EC2가 서로 통신할 수 있는 VPC 경로가 있어야 합니다. 보안 그룹은 MCP 8010을 Backend에서, Backend 8000을 Frontend에서, Frontend 8501을 사용자에게 허용하세요. SSH 22는 GitHub Actions Runner에서 접속 가능해야 합니다.

최초 배포는 MCP → Backend → Frontend 순서로 `main`에 각 서비스 변경을 반영하거나 해당 워크플로를 실행하세요. Backend 배포는 MCP readiness를, Frontend 배포는 Backend readiness를 확인합니다. 배포 후 Actions의 `deploy` Job과 `http://<Frontend EC2 주소>:8501`을 확인하세요. 실제 API 키를 서버 환경 파일에 넣어야 날씨 조회와 LLM 응답까지 동작합니다.
