# 🤖 dev-automation-agent

저장소의 반복 잡무를 자동화하는 Python CLI 도구입니다.

- **commit-msg**: 스테이징된 변경을 읽어 Conventional Commits 스타일 커밋 메시지 생성
- **readme**: 저장소 파일 트리를 스캔해 README 초안 생성
- **standup**: 최근 `git log`를 요약해 한국어 데일리 스탠드업 노트 작성 (어제/오늘 한 일)

`OPENAI_API_KEY` 환경변수가 설정되어 있고 `openai` 패키지가 설치되면 LLM(gpt-4o-mini 기본)으로 더 자연스러운 문장을 생성합니다. 키가 없으면 **휴리스틱 템플릿 모드**로 동작하므로 API 키 없이도 바로 사용할 수 있습니다.

---

## 설치

```bash
cd dev-automation-agent
python -m venv .venv && source .venv/bin/activate   # 선택 사항
pip install -r requirements.txt                     # openai는 선택 사항 (없어도 동작)
```

## 설정 (선택)

LLM 모드를 쓰려면 API 키를 설정하세요.

```bash
export OPENAI_API_KEY="sk-..."
# 모델 변경 (기본: gpt-4o-mini)
export OPENAI_MODEL="gpt-4o-mini"
```

설정 파일로 기본 동작을 바꿀 수 있습니다. 예시 파일을 복사해 사용하세요.

```bash
cp agent.config.example.json agent.config.json
```

| 키 | 설명 | 기본값 |
|---|---|---|
| `language` | 출력 언어 | `ko` |
| `readme_output` | `readme` 서브커맨드 기본 출력 파일 | `README.draft.md` |

## 사용법

### 1. 커밋 메시지 생성

```bash
# 먼저 변경을 스테이징
git add .

# 메시지 미리보기
python agent.py commit-msg

# 바로 커밋까지
python agent.py commit-msg --apply
```

### 2. README 초안 생성

```bash
# 현재 저장소 스캔 → README.draft.md 생성
python agent.py readme

# 다른 저장소 스캔 / 출력 파일 지정
python agent.py readme --path /path/to/repo --output README.new.md
```

### 3. 스탠드업 노트

```bash
# 최근 1일 커밋 요약
python agent.py standup

# 최근 7일 + 파일 저장
python agent.py standup --days 7 --output standup.md
```

## 오류 안내

| 상황 | 메시지 |
|---|---|
| git 저장소가 아님 | `git init` 후 사용 안내 |
| 스테이징된 변경 없음 | `git add` 안내 |
| API 키 없음 | 휴리스틱 모드로 자동 전환 |

## English summary

A Python CLI toolkit that automates repo chores: conventional-commit message generation from staged diffs, README draft generation from a repo scan, and Korean daily-standup notes from recent git history. Uses an LLM when `OPENAI_API_KEY` is set; otherwise falls back to heuristic templates — no API key required to run.

## 라이선스

MIT
