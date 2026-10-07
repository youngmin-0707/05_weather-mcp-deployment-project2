# AWS EC2 자동 배포 준비

## 1. EC2 준비

Amazon Linux 2023 EC2에 Docker와 Docker Compose Plugin을 설치합니다. Security Group은 SSH
22와 Frontend 8501만 허용하고, 8000·8010은 인터넷에 공개하지 않습니다.

EC2에 배포 폴더와 Secret 환경 파일을 최초 한 번 준비합니다.

```bash
mkdir -p ~/weather-mcp-deployment
cd ~/weather-mcp-deployment
nano .env
chmod 600 .env
```

```ini
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash
```

Workflow는 이 `.env`를 GitHub에서 복사하거나 로그로 출력하지 않습니다.

## 2. GitHub production Environment

Repository `Settings → Environments → New environment`에서 `production`을 만듭니다. 가능한
계정에서는 Required reviewers와 `main` Branch 제한을 설정합니다.

다음 Environment Secret을 등록합니다.

| Secret | 내용 |
| --- | --- |
| `AWS_HOST` | EC2 Public DNS 또는 IP |
| `AWS_USER` | Amazon Linux의 `ec2-user` |
| `AWS_SSH_PRIVATE_KEY` | 배포용 Private Key 전체 |
| `AWS_SSH_KNOWN_HOSTS` | 관리자가 지문을 확인한 EC2 known_hosts 항목 |

`AWS_SSH_KNOWN_HOSTS`는 앞의 EC2 단계에서 로컬 PC의 SSH 접속이 성공하면서 자동 저장된
Windows `known_hosts` 항목을 사용합니다. 서버에 다시 접속하거나 서버의 `.ssh`를 수정하지
않습니다. 로컬 PowerShell에서 조회하고 `ssh-ed25519` 한 줄 전체를 Clipboard에 복사합니다.

```powershell
$knownHost = ssh-keygen -F <PUBLIC_IPV4_OR_DNS> `
  -f "$env:USERPROFILE\.ssh\known_hosts" |
  Select-String "ssh-ed25519" |
  ForEach-Object { $_.Line }

$knownHost
$knownHost | Set-Clipboard
```

`<EC2 주소> ssh-ed25519 <긴 공개 Host Key>` 한 줄 전체를 GitHub `production` Environment의
`AWS_SSH_KNOWN_HOSTS`에 등록합니다. `SHA256:...` Fingerprint만 넣거나 `# Host ... found`
주석을 포함하지 않습니다. 조회 결과가 없다면 Public IP 변경 또는 최초 접속을 하지 않은
예외이므로 이때만 주소와 Fingerprint를 확인하고 SSH로 한 번 접속한 뒤 다시 조회합니다.

GitHub-hosted Runner에서 EC2 SSH로 접근 가능한 네트워크 정책이 별도로 필요합니다. 이를
해결하기 위해 22번 Port를 `0.0.0.0/0`으로 열지 않습니다. 실제 운영에서는 SSM, VPN,
Bastion 또는 보안 정책에 맞는 self-hosted Runner를 사용합니다.

## 3. 배포 흐름

```text
개인 브랜치 Push 또는 Pull Request
→ Fake MCP·LLM Backend Test
→ Compose 검사
→ Frontend·Backend·MCP Image Build
→ main 병합
→ 같은 CI 재실행·성공
→ production 승인
→ EC2 Source 복사·Compose 실행
→ /health/ready 성공
```

## 4. EC2 확인과 복구

```bash
cd ~/weather-mcp-deployment
docker compose ps
docker compose logs --tail=100 weather-mcp backend frontend
curl --fail http://127.0.0.1:8000/health/ready
```

배포 후 문제가 있으면 GitHub에서 마지막 정상 Commit으로 되돌린 새 Commit을 만든 뒤 같은
승인 절차로 다시 배포합니다. 이 입문 예제는 Blue/Green이나 자동 Rollback을 구현하지 않습니다.
