# Weather MCP deployment

브라우저 → Frontend(Streamlit 8501) → Backend(FastAPI 8000) → Weather MCP(8010) → Open-Meteo 순서로 동작합니다. Backend는 선택한 LLM을 호출합니다. 세 서비스는 각각의 Compose 파일과 CI/CD를 유지하면서 같은 EC2에서 실행됩니다.

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

세 Compose 프로젝트는 외부 Docker 네트워크 `weather-local`을 공유합니다. 로컬 Docker Desktop에서도 Backend의 `config/.env.docker`에 `WEATHER_MCP_URL=http://weather-mcp:8010/mcp`, Frontend의 `config/.env.docker`에 `BACKEND_URL=http://backend:8000`을 설정합니다.

각 서비스의 컨테이너와 이미지는 `weather-mcp`, `weather-backend`, `weather-frontend`로 이름을 고정합니다. 루트의 이전 통합 Compose 구성은 제거했으며, 서비스별 `deploy/compose.yml`만 사용합니다.

```powershell
docker network create weather-local  # 네트워크가 없을 때 처음 한 번
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

`main`에 서비스 코드나 워크플로가 push되면 해당 CI 성공 후 서비스별 GitHub Environment를 사용해 같은 EC2에 자동 배포합니다. Environment 이름은 Backend `backend`, Frontend `frontend`, MCP `MCP`입니다. PR에서는 CI만 실행하고 수동 `workflow_dispatch`에서는 CI 후 배포도 실행합니다. 각 배포는 해당 서비스의 Compose만 실행합니다. 배포 스크립트는 공통 네트워크 생성과 컨테이너 시작을 순차 처리한 뒤 서비스별 상태를 검사합니다. Environment에 승인 규칙이 있으면 승인 후 진행됩니다.

각 Environment에는 기존에 등록된 Secret 4개(`AWS_HOST`, `AWS_USER`, `AWS_SSH_PRIVATE_KEY`, `AWS_SSH_KNOWN_HOSTS`)를 사용합니다. 세 Environment의 `AWS_HOST`는 동일한 EC2를 가리켜야 합니다.

EC2에는 Docker Compose, `curl`, `flock`이 필요합니다. 첫 배포 전에 `~/weather-mcp-deployment/backend/config/.env`에 API 키를 설정하세요. 실제 `.env`는 Git과 배포 묶음에 포함되지 않으며 배포 시 유지됩니다. 서비스별 `.env.docker`가 없으면 배포 스크립트가 예시 파일에서 만들고, Backend의 `WEATHER_MCP_URL`과 Frontend의 `BACKEND_URL`은 공통 네트워크의 서비스 이름으로 갱신합니다.

컨테이너 사이에서는 `weather-mcp:8010`과 `backend:8000`으로 통신합니다. Backend 8000과 MCP 8010은 EC2의 `127.0.0.1`에만 바인딩하고, Frontend 8501만 사용자에게 공개합니다. 보안 그룹에서 8501과 GitHub Actions Runner가 사용할 SSH 22의 접속을 허용하세요.

최초 전환 전 기존 컨테이너가 8000 또는 8501을 점유하는지 `docker ps`로 확인하고, 기존 서비스를 확인한 뒤 해당 컨테이너만 중지하세요. 최초 배포는 MCP → Backend → Frontend 순서로 각 워크플로를 실행합니다. Backend 배포는 MCP readiness를, Frontend 배포는 Backend readiness를 확인합니다. 배포 후 Actions의 `deploy` Job과 `http://<EC2 주소>:8501`을 확인하세요. 실제 API 키를 서버 환경 파일에 넣어야 날씨 조회와 LLM 응답까지 동작합니다.

배포 후 EC2에서 `docker ps -a`, `docker image ls`, `df -h /`로 컨테이너·이미지·디스크를 확인합니다. 이름 변경 전의 `weather-mcp-weather-mcp-1`, `weather-backend-backend-1`, `weather-frontend-frontend-1` 및 동일한 이름의 이미지는 새 서비스가 정상 작동하는 것을 확인한 뒤 정리할 수 있습니다. 배포 스크립트는 다른 프로젝트의 Docker 리소스를 자동으로 삭제하지 않습니다.
