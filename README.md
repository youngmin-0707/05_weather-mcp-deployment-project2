# Weather MCP deployment

이 프로젝트는 `mcp_server`, `backend`, `frontend`를 독립된 Python 환경과 Compose 프로젝트로 실행합니다. 데이터 흐름은 브라우저 → Streamlit(8501) → FastAPI(8000) → Weather MCP(8010) → Open-Meteo입니다. Backend는 OpenAI 또는 Gemini를 호출합니다.

현재 애플리케이션 코드에는 Redis나 데이터베이스 클라이언트가 없습니다. AWS의 Redis/DB 연결 검증은 접속 정보와 사용 목적을 확인한 뒤 추가해야 합니다.

## 디렉터리

| 디렉터리 | 설정 | 로컬 URL | CI |
| --- | --- | --- | --- |
| `mcp_server` | `.env`, `compose.yml`, `requirements.txt` | `http://127.0.0.1:8010/health` | `mcp-server-ci.yml` |
| `backend` | `.env`, `compose.yml`, `requirements.txt` | `http://127.0.0.1:8000/health/ready`, `/health/dependencies` | `backend-ci.yml` |
| `frontend` | `.env`, `compose.yml`, `requirements.txt` | `http://127.0.0.1:8501` | `frontend-ci.yml` |

각 `.env.example`을 해당 디렉터리의 `.env`로 복사하고 Backend의 사용할 LLM API 키를 채웁니다. `.env`, `.venv`, PEM 키는 `.gitignore` 대상입니다. 기존 루트 `.env`의 LLM 설정은 `backend/.env`로 옮겼습니다. 순수 Python 실행에서는 URL이 `127.0.0.1`이고, Compose 컨테이너끼리는 공유 네트워크의 서비스 이름으로 연결합니다.

## Python 가상환경 실행 (PowerShell)

Python 3.12가 설치된 터미널에서 각 서비스를 별도 터미널로 실행합니다. 최초 1회 각 디렉터리에서 다음을 실행합니다.
가상환경과 의존성 설치를 한꺼번에 하려면 프로젝트 루트에서 `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-venvs.ps1`을 실행합니다.

```powershell
cd mcp_server
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Get-Content .env | ForEach-Object { if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') } }
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Get-Content .env | ForEach-Object { if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') } }
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

각 명령의 `cd`는 프로젝트 루트에서 시작합니다. 서비스는 MCP → Backend → Frontend 순서로 시작합니다. Windows 환경에서 `py` 대신 설치된 Python 3.12의 전체 경로를 사용할 수 있습니다.

## Compose 실행

프로젝트 루트에서 다음 순서로 실행합니다. 각 서비스는 별도 Compose 프로젝트이며 8010, 8000, 8501 포트를 호스트 루프백에 바인딩합니다. `docker network create`는 최초 1회만 실행합니다. 이미 존재한다는 메시지가 나오면 다음 명령으로 계속 진행하면 됩니다.

```powershell
docker network create weather-local
docker compose -f mcp_server/compose.yml --env-file mcp_server/.env config --quiet
docker compose -f backend/compose.yml --env-file backend/.env config --quiet
docker compose -f frontend/compose.yml --env-file frontend/.env config --quiet

docker compose -f mcp_server/compose.yml up -d --build
docker compose -f backend/compose.yml up -d --build
docker compose -f frontend/compose.yml up -d --build
```

세 설정을 한 번에 검사하려면 `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-config.ps1`을 실행합니다.

> Compose는 각 파일의 디렉터리를 프로젝트 디렉터리로 사용합니다. 루트에서 실행할 때에도 설정 값은 `--env-file`로 명시하는 편이 안전합니다.

상태 확인:

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Invoke-RestMethod http://127.0.0.1:8000/health/dependencies
Invoke-WebRequest http://127.0.0.1:8501/_stcore/health
```

브라우저에서 `http://127.0.0.1:8501`을 열고 Health Check 및 Weather Agent를 확인합니다. Weather Agent의 실제 응답에는 Open-Meteo와 LLM API 접속이 필요합니다.

### 로컬 Backend에서 AWS Redis·PostgreSQL 연결 확인

먼저 EC2로 SSH 접속 가능한 PowerShell 터미널에서 다음 터널을 유지합니다. `<EC2_PUBLIC_HOST>`에는 현재 EC2의 Public IPv4 또는 DNS를 입력합니다. 기존 서버 화면에서 Redis와 PostgreSQL은 각각 EC2 호스트의 6379, 5432 포트에 게시돼 있습니다.

```powershell
ssh -N -i .\agent2.pem -L 127.0.0.1:16379:127.0.0.1:6379 -L 127.0.0.1:15432:127.0.0.1:5432 ubuntu@<EC2_PUBLIC_HOST>
```

별도 터미널에서 로컬 Backend를 위의 Python 가상환경 실행 절차대로 시작하고 `Invoke-RestMethod http://127.0.0.1:8000/health/dependencies`를 호출합니다. `redis.status`와 `database.status`가 모두 `connected`이면 로컬 Backend 프로세스에서 AWS 컨테이너의 TCP 포트까지 경로가 연결된 것입니다. 이 검사는 Redis 인증이나 PostgreSQL SQL 쿼리 실행을 확인하지 않습니다. Backend 애플리케이션은 현재 두 서비스를 기능에 사용하지 않습니다.

기존 EC2 서버에서는 `bash scripts/check-linux-services.sh`로 화면에 보이는 다섯 컨테이너의 실행 상태, Redis 응답, PostgreSQL 준비 상태, MCP·Backend·Frontend HTTP 상태를 검사할 수 있습니다. 이 검사는 Redis·PostgreSQL의 개별 상태를 확인하며, Backend 코드에서 두 서비스를 실제 사용한다는 뜻은 아닙니다.

기존 EC2 화면에서 Redis와 PostgreSQL은 기본 `bridge`, Backend는 `weather-mcp-deployment_default`에 연결돼 있습니다. 서비스 간 이름 조회와 통신을 위해 EC2에 변경 파일을 복사한 뒤 `bash scripts/connect-aws-dependencies.sh`를 실행합니다. 이 명령은 `weather-local` 네트워크를 만들고 기존 Redis·PostgreSQL 컨테이너를 연결합니다. 기존 Backend가 실행 중이면 그것도 연결합니다. 그다음 `bash scripts/check-aws-connectivity.sh`로 Backend 컨테이너에서 Redis 6379와 PostgreSQL 5432에 TCP 접속되는지 검사합니다. Redis나 PostgreSQL 컨테이너를 다시 생성하면 연결 명령을 다시 실행해야 합니다. TCP 성공은 인증이나 SQL 쿼리 성공을 보증하지 않습니다.

중지할 때는 `frontend`, `backend`, `mcp_server`의 Compose 파일에 각각 `down`을 실행합니다.

## CI

`.github/workflows`에 서비스별 워크플로가 있습니다. 각 디렉터리 변경 시 해당 워크플로가 Python 문법과 테스트(해당 서비스), Compose 설정 검사, 이미지 빌드를 수행합니다. Frontend는 컨테이너 HTTP 상태도 확인합니다. CI는 실제 LLM 키나 AWS 리소스를 사용하지 않습니다.
