# Codex-codeshark

개인 Telegram 메시지를 이 Mac의 Codex CLI에 연결하는 단일 사용자용 로컬 에이전트입니다. 채널은 Telegram 하나이며, 멀티에이전트나 별도 웹 UI는 포함하지 않습니다.

```text
Telegram 개인 채팅
  -> 사용자 인증과 승인 게이트
  -> SQLite 영속 작업 큐 / 스케줄러
  -> Codex CLI (`codex-codeshark` profile)
  -> workspace/ 내부 파일
```

## 구현된 기능

- 현재 Codex 세션을 이어 쓰는 대화형 작업
- 재시작 후에도 복구되는 단일-worker SQLite 작업 큐
- 일회성 알림, heartbeat, 5-field cron 예약 실행
- 모델이 메모리·스킬 후보를 제안하고 사용자가 승인하는 자기학습 루프
- 관련 요청에만 최대 3개의 승인된 로컬 스킬 주입
- 세션 turn 한도 도달 시 지속 정보 요약 후보 생성, 이전 세션 삭제, 새 세션 시작
- 외부 변경·파괴적 요청의 명시적 `/approve` 게이트
- Codex MCP 서버별 활성화 및 도구 allowlist
- 작업 취소, 제한시간, Telegram 메시지 분할, 평가 기록

## 안전 기본값

- BotFather 토큰은 저장소가 아닌 macOS Keychain에 저장
- 로컬에서 페어링한 Telegram 사용자 ID 하나와 개인 채팅만 허용
- 작업 디렉터리는 서버가 정한 `workspace/`로 고정
- Codex profile은 `workspace-write`, `approval_policy = never` 사용
- 한 번에 한 작업만 실행하며 기본 제한시간은 30분
- Telegram에서 임의 경로나 Codex CLI 옵션을 받지 않음
- 위험 작업은 실행 전에 task/job ID 단위 승인이 필요함
- 승인된 작업이 실행 중 중단되면 재시작 후 다시 승인을 요구함
- 모든 Codex MCP 서버를 로컬 정책에 등록해야 하며, 허용 도구가 없는 서버는 꺼짐

위험 요청 분류는 한국어·영어 패턴과 Codex에 주입하는 실행 정책을 함께 사용합니다. 완전한 보안 경계는 아니므로 외부 쓰기 도구는 MCP allowlist에서도 최소화해야 합니다.

## 1. 초기 설정

BotFather에서 봇을 만든 뒤 토큰을 복사합니다. 토큰을 채팅이나 파일에 넣지 말고 아래 명령의 비공개 입력창에만 입력하세요.

```bash
cd "$HOME/workspace/Codex-codeshark"
PYTHONPATH=src python3 -m codex_codeshark setup
```

설정 명령이 일회용 `/pair ...` 코드를 표시하면 Telegram에서 봇에게 그대로 전송합니다. 성공하면 다음 항목이 생성됩니다.

- 토큰: macOS Keychain의 `codex-codeshark.bot-token`
- 사용자 ID와 로컬 정책: git에서 제외된 `config.local.toml`

`config.local.toml`은 이 설치에서만 사용하는 설정 파일입니다. 페어링된 Telegram 사용자 ID, 고정 workspace, Codex 실행 파일과 profile, timeout·대기열·세션·메모리 상한, MCP 서버·도구 허용 목록을 담습니다. BotFather 토큰과 대화 전문은 들어 있지 않지만 사용자 ID와 로컬 경로가 있으므로 Git에는 커밋하지 않습니다.

설정 시점에 Codex의 `~/.codex/config.toml`과 `~/.codex/codex-codeshark.config.toml`에 있는 MCP 서버 이름은 `known_servers`로 자동 복사되고 모두 비활성 상태로 시작합니다. 나중에 Codex MCP 구성을 바꾸면 `config.local.toml`도 맞춰야 합니다. 허용하지 않을 서버도 `known_servers`에는 있어야 실행 시 명시적으로 비활성화됩니다.

```toml
[mcp_policy]
known_servers = ["github", "docs"]

[mcp_policy.allowed_tools]
docs = ["search", "fetch"]
# github는 이 게이트웨이에서 비활성화
```

## 2. 점검과 실행

```bash
PYTHONPATH=src python3 -m codex_codeshark doctor
PYTHONPATH=src python3 -m codex_codeshark run
```

`doctor`는 로컬 설정, Keychain 토큰, Telegram API, Codex 로그인/profile, MCP 정책 누락을 검사합니다. 등록되지 않은 MCP 서버가 하나라도 있으면 봇 실행도 실패합니다.

## Telegram 명령

일반 작업과 세션:

- 일반 텍스트: 현재 Codex 세션에 작업 추가
- `/status`: 실행 상태, 대기열, 세션 turn, 저장 항목 수
- `/tasks`: 최근 영속 작업 상태
- `/cancel`: 현재 실행 또는 가장 오래된 대기 작업 취소
- `/new`: 현재 Codex 세션을 삭제하고 새 세션 시작

학습과 평가:

- `/remember 내용`, `/memories`, `/forget ID`: 장기 메모리 관리
- `/learn memory 내용`: 메모리 후보 생성
- `/learn skill 이름 | 절차`: 재사용 스킬 후보 생성
- `/learning`, `/approve ID`, `/reject ID`: 학습·위험 작업 승인 관리
- `/skills`, `/forget_skill ID`: 승인된 스킬 관리
- `/good [메모]`, `/bad [이유]`: 직전 성공 작업 평가

자동화:

- `/remind 30 요청`: 30분 뒤 한 번 실행
- `/heartbeat 10 요청`: 10분마다 실행
- `/cron */15 * * * * | 요청`: 로컬 시간 기준 5-field cron 실행
- `/jobs`, `/pause ID`, `/resume_job ID`, `/delete_job ID`: 예약 작업 관리
- `/mcp`: 현재 MCP 서버·도구 정책 확인

예약 작업은 `codex exec --ephemeral`로 실행되어 대화 세션을 만들거나 이어 쓰지 않습니다. 외부 변경 가능성이 있는 예약 작업은 생성 즉시 멈추고 `/approve job-ID`를 기다립니다.

## 개인 데이터 마이그레이션

개인 데이터 archive에는 다음 항목만 포함됩니다.

- 장기 메모리와 승인된 스킬
- `/good`, `/bad` 평가 기록
- 학습 후보
- 예약 작업과 완료된 작업 메타데이터

BotFather 토큰, `config.local.toml`, 현재 Codex 세션, Telegram update offset, runtime 로그는 머신 종속 정보이므로 제외됩니다. Archive에는 Telegram chat ID와 메모리 등이 들어갈 수 있으므로 파일 권한은 `0600`으로 만들며 Git에 올리면 안 됩니다.

원본 Mac에서 봇을 중지한 뒤 내보냅니다.

```bash
cd "$HOME/workspace/Codex-codeshark"
python3 scripts/uninstall_launch_agent.py
PYTHONPATH=src python3 -m codex_codeshark export-data \
  "$HOME/codeshark-personal-data.codeshark.zip"
```

새 Mac에서는 먼저 `setup`으로 새 머신의 Keychain 토큰과 `config.local.toml`을 만든 다음 가져옵니다.

```bash
PYTHONPATH=src python3 -m codex_codeshark setup
PYTHONPATH=src python3 -m codex_codeshark import-data \
  "$HOME/codeshark-personal-data.codeshark.zip" --force
```

중복 실행 방지를 위해 archive의 대기 중 단발 작업은 취소 처리되고, 활성 예약 작업은 일시정지 상태로 가져옵니다. 내용을 확인한 뒤 Telegram의 `/resume_job ID`로 필요한 작업만 재개하세요. 기존 archive나 대상 개인 데이터를 교체할 때만 `--force`를 사용합니다.

## 자기학습과 세션 저장

모델은 다음 작업에도 유용한 사실이나 절차가 있을 때만 학습 후보를 제안합니다. 후보는 응답에서 숨겨져 `runtime/agent.db`의 pending 상태로 저장되며, `/approve` 전에는 메모리나 스킬에 반영되지 않습니다. 같은 이름의 승인된 스킬을 다시 승인하면 새 파일을 늘리지 않고 기존 스킬을 교체합니다.

대화형 세션은 기본 30 turn에서 자동 회전합니다. 회전 직전에 지속 정보만 학습 후보로 만들고 기존 Codex 세션을 영구 삭제한 뒤 다음 요청을 새 세션에서 실행합니다. 요약이나 삭제가 실패하면 기존 세션을 유지합니다. `/new`도 삭제 성공을 확인한 뒤에만 로컬 세션 ID를 비웁니다.

이 게이트웨이는 대화 전문을 별도로 복제하지 않으며, 다른 프로젝트나 Codex 앱에서 만든 세션은 정리하지 않습니다.

## 저장 용량 정책

| 저장소 | 보관 정책 |
|---|---|
| `runtime/state.json` | 현재 세션 ID, turn 수, Telegram offset만 저장 |
| Codex 현재 세션 | `max_session_turns` 도달 시 요약 후보 생성 후 삭제·회전 |
| 예약 실행 | ephemeral이라 Codex 세션 미저장 |
| `runtime/agent.db` 작업 | 완료·실패·취소·거절 시 원문 prompt 삭제, 최근 terminal 기록 200개 유지 |
| 학습 후보 | pending 최대 100개, 처리된 후보 최근 200개 유지 |
| 장기 메모리 | 기본 총 4,000자, 항목당 1,000자 |
| 로컬 스킬 | 최대 100개, 스킬당 8,000자 |
| 예약 작업 | active 최대 100개, 끝난 기록 최근 200개 |
| `runtime/feedback.jsonl` | 1 MB에서 1회 회전하여 현재 파일과 `.1`만 유지 |

상한은 `config.local.toml`의 `max_session_turns`와 `memory_max_chars`로 조정할 수 있습니다. 대기·반복 중인 작업과 승인 대기 후보는 실행에 필요하므로 사용자가 처리하거나 삭제할 때까지 유지됩니다.

## 3. 로그인 시 자동 실행

초기 설정과 `doctor`가 성공한 다음 실행하세요.

```bash
PYTHONPATH=src python3 scripts/install_launch_agent.py
```

상태와 로그:

```bash
launchctl print gui/$(id -u)/com.codeshark.agent
tail -f runtime/agent.out.log runtime/agent.err.log
```

제거:

```bash
python3 scripts/uninstall_launch_agent.py
```

## 개발

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m codex_codeshark doctor
```
