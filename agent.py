#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dev-automation-agent
저장소 잡무(커밋 메시지, README 초안, 데일리 스탠드업 노트)를 자동화하는 CLI 도구.

- OPENAI_API_KEY 환경변수가 있으면 LLM으로 더 자연스러운 문장을 생성하고,
- 없으면 휴리스틱 템플릿으로 동작하므로 API 키 없이도 바로 쓸 수 있다.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROGRAM = "agent.py"
VERSION = "0.1.0"

LLM_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
CONFIG_FILE = "agent.config.json"

# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

def err(msg: str) -> int:
    print(f"❌ 오류: {msg}", file=sys.stderr)
    return 1


def info(msg: str) -> None:
    print(f"ℹ️  {msg}")


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def run_git(*args: str) -> subprocess.CompletedProcess:
    """git 명령 실행. 실패하면 CalledProcessError 발생."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=True,
    )


def is_git_repo(path: Path | None = None) -> bool:
    try:
        run_git("-C", str(path or "."), "rev-parse", "--git-dir")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def load_config() -> dict:
    cfg = {"language": "ko", "readme_output": "README.draft.md"}
    p = Path(CONFIG_FILE)
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️  설정 파일 읽기 실패 ({CONFIG_FILE}): {e}. 기본값을 사용합니다.", file=sys.stderr)
    return cfg


# ---------------------------------------------------------------------------
# LLM 어댑터 (키가 없으면 None)
# ---------------------------------------------------------------------------

def llm_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def llm_generate(system_prompt: str, user_prompt: str) -> str | None:
    """OpenAI API 호출. 실패하면 None을 반환해 휴리스틱으로 대체한다."""
    try:
        from openai import OpenAI
    except ImportError:
        info("`openai` 패키지가 없습니다. 휴리스틱 모드로 동작합니다.")
        info("LLM을 쓰려면: pip install openai")
        return None

    try:
        client = OpenAI()  # OPENAI_API_KEY 환경변수 자동 사용
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:  # 네트워크/인증 실패 등은 휴리스틱으로 대체
        print(f"⚠️  LLM 호출 실패 ({e}). 휴리스틱 모드로 전환합니다.", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# 1. commit-msg — 스테이징된 변경으로 커밋 메시지 생성
# ---------------------------------------------------------------------------

def get_staged_diff() -> tuple[str, list[str]]:
    """(diff 텍스트, 변경된 파일 목록)"""
    diff = run_git("diff", "--staged").stdout
    files_out = run_git("diff", "--staged", "--name-only").stdout
    files = [f for f in files_out.splitlines() if f.strip()]
    return diff, files


def heuristic_commit_type(files: list[str]) -> str:
    exts = {Path(f).suffix.lower() for f in files}
    names = {Path(f).name.lower() for f in files}
    if any(n.startswith("readme") for n in names):
        return "docs"
    if any(n.startswith("test") or "test" in n for n in names) and len(names) == 1:
        return "test"
    if exts <= {".md", ".rst", ".txt"}:
        return "docs"
    if any("fix" in f or "bug" in f for f in names):
        return "fix"
    if any(n in {"requirements.txt", "package.json", ".gitignore", "dockerfile"} for n in names) and len(names) == 1:
        return "chore"
    if any(n in names for n in ("main.py", "app.py", "agent.py")) and len(exts) == 1:
        return "feat"
    return "feat" if exts & {".py", ".js", ".ts", ".java", ".go"} else "chore"


def cmd_commit_msg(args: argparse.Namespace) -> int:
    if not is_git_repo():
        return err("git 저장소가 아닙니다. `git init` 후 사용하세요.")
    try:
        diff, files = get_staged_diff()
    except subprocess.CalledProcessError as e:
        return err(f"git diff 읽기 실패: {e.stderr.strip()}")

    if not files:
        return err("스테이징된 변경이 없습니다. `git add <파일>` 로 변경을 스테이징하세요.")

    truncated = diff[:4000] + ("\n... (생략)" if len(diff) > 4000 else "")
    result = None

    if llm_available():
        info(f"LLM({LLM_MODEL})으로 커밋 메시지를 생성합니다...")
        result = llm_generate(
            "당신은 커밋 메시지 작성 도우미입니다. Conventional Commits 형식(type: 제목)으로, "
            "제목은 50자 이내 한국어 또는 영어 간결체로 작성하세요. 본문이 필요하면 '-' 로 구분해 1~3줄로 쓰세요.",
            f"스테이징된 변경 파일:\n{chr(10).join(files)}\n\n--- diff ---\n{truncated}",
        )

    if not result:
        ctype = heuristic_commit_type(files)
        # 변경 파일 기준 짧은 제목 자동 구성
        if len(files) == 1:
            subject = f"{ctype}: {files[0]} 변경"
        else:
            subject = f"{ctype}: {len(files)}개 파일 변경 ({files[0]} 외)"
        result = f"{subject}\n\n- 변경 파일: {', '.join(files[:5])}" + (" 외" if len(files) > 5 else "")
        info("휴리스틱 템플릿으로 생성했습니다. (OPENAI_API_KEY를 설정하면 LLM 생성 가능)")

    print("\n" + "=" * 50)
    print("📝 생성된 커밋 메시지")
    print("=" * 50)
    print(result)
    print("=" * 50)

    if args.apply:
        try:
            run_git("commit", "-m", result)
            ok("커밋이 완료되었습니다.")
        except subprocess.CalledProcessError as e:
            return err(f"커밋 실패: {e.stderr.strip()}")
    else:
        info("적용하려면 `python agent.py commit-msg --apply` 로 실행하세요.")
    return 0


# ---------------------------------------------------------------------------
# 2. readme — 저장소 스캔 후 README 초안 생성
# ---------------------------------------------------------------------------

IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".next", "dist", "build"}
KEY_FILES = ("requirements.txt", "package.json", "pyproject.toml", "setup.py",
             "Makefile", "Dockerfile", "docker-compose.yml", "main.py", "app.py", "index.js")


def scan_repo(root: Path) -> dict:
    tree: list[str] = []
    key_found: list[str] = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in IGNORE_DIRS for part in rel.parts):
            continue
        if p.is_file():
            tree.append(str(rel))
            if rel.name in KEY_FILES or rel.name.lower().startswith("readme"):
                key_found.append(str(rel))
    return {"tree": tree[:200], "key_files": key_found, "truncated": len(tree) > 200}


def cmd_readme(args: argparse.Namespace) -> int:
    root = Path(args.path or ".").resolve()
    if not root.is_dir():
        return err(f"경로가 없습니다: {root}")
    cfg = load_config()
    scan = scan_repo(root)

    if not scan["tree"]:
        return err("저장소가 비어 있습니다.")

    tree_txt = "\n".join(scan["tree"])
    result = None

    if llm_available():
        info(f"LLM({LLM_MODEL})으로 README 초안을 생성합니다...")
        result = llm_generate(
            "당신은 기술 문서 작성자입니다. 파일 트리를 보고 프로젝트 README.md를 한국어로 작성하세요. "
            "섹션: 소개, 주요 기능, 설치, 사용법, 기술 스택. 불확실한 내용은 추측하지 말고 일반적인 표현으로.",
            f"프로젝트 루트: {root.name}\n\n파일 트리:\n{tree_txt}\n\n주요 파일: {', '.join(scan['key_files']) or '없음'}",
        )

    if not result:
        result = heuristic_readme(root, scan)
        info("휴리스틱 템플릿으로 생성했습니다. (OPENAI_API_KEY를 설정하면 LLM 생성 가능)")

    out = Path(args.output or cfg["readme_output"])
    out.write_text(result, encoding="utf-8")
    ok(f"README 초안을 '{out}' 에 저장했습니다.")
    print("\n" + "=" * 50)
    print(result[:1500] + ("\n... (전체 내용은 파일 참고)" if len(result) > 1500 else ""))
    print("=" * 50)
    return 0


def heuristic_readme(root: Path, scan: dict) -> str:
    key = ", ".join(scan["key_files"]) if scan["key_files"] else "확인 필요"
    dirs = sorted({Path(t).parts[0] for t in scan["tree"] if len(Path(t).parts) > 1})
    return f"""# {root.name}

프로젝트 개요를 여기에 작성하세요.

## 주요 기능

- (자동 스캔 결과) 디렉터리: {", ".join(dirs) if dirs else "루트만 존재"}
- 주요 파일: {key}

## 설치

```bash
# Python 프로젝트인 경우
pip install -r requirements.txt
```

## 사용법

```bash
# 진입점 스크립트를 확인 후 작성하세요
python main.py
```

## 기술 스택

- 스캔된 주요 파일: {key}

---
*이 README는 `dev-automation-agent`의 휴리스틱 템플릿으로 생성되었습니다. 내용을 다듬어 주세요.*
"""


# ---------------------------------------------------------------------------
# 3. standup — 최근 git log로 한국어 스탠드업 노트
# ---------------------------------------------------------------------------

def get_commits(days: int) -> list[dict]:
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out = run_git(
        "log", f"--since={since}", "--pretty=format:%h|%ad|%s|%an",
        "--date=short",
    ).stdout
    commits = []
    for line in out.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            h, d, s, a = parts
            commits.append({"hash": h, "date": d, "subject": s, "author": a})
    return commits


def cmd_standup(args: argparse.Namespace) -> int:
    if not is_git_repo():
        return err("git 저장소가 아닙니다. `git init` 후 사용하세요.")
    try:
        commits = get_commits(args.days)
    except subprocess.CalledProcessError as e:
        return err(f"git log 읽기 실패: {e.stderr.strip()}")

    if not commits:
        info(f"최근 {args.days}일간 커밋이 없습니다.")
        return 0

    summary = "\n".join(f"- [{c['date']}] {c['subject']} ({c['author']})" for c in commits)
    result = None

    if llm_available():
        info(f"LLM({LLM_MODEL})으로 스탠드업 노트를 생성합니다...")
        result = llm_generate(
            "당신은 개발 팀의 스크럼 마스터입니다. 커밋 목록을 보고 한국어 데일리 스탠드업 노트를 작성하세요. "
            "형식:\n## 어제 한 일\n- ...\n## 오늘 할 일\n- (커밋에서 유추 가능한 다음 단계 1~3개)\n간결하게 bullet으로만 쓰세요.",
            f"최근 {args.days}일 커밋:\n{summary}",
        )

    if not result:
        by_date: dict[str, list[str]] = {}
        for c in commits:
            by_date.setdefault(c["date"], []).append(c["subject"])
        yesterday_lines = [f"- {s}" for d in sorted(by_date)[:-1] for s in by_date[d]]
        today_lines = [f"- {s} (진행 중/후속)" for s in by_date[sorted(by_date)[-1]]]
        result = (
            f"# 데일리 스탠드업 ({datetime.now().strftime('%Y-%m-%d')})\n\n"
            "## 어제 한 일\n"
            + ("\n".join(yesterday_lines) if yesterday_lines else "- (이전 기록 없음)")
            + "\n\n## 오늘 할 일\n"
            + "\n".join(today_lines)
            + "\n"
        )
        info("휴리스틱 템플릿으로 생성했습니다. (OPENAI_API_KEY를 설정하면 LLM 생성 가능)")

    print("\n" + "=" * 50)
    print("🗣️  스탠드업 노트")
    print("=" * 50)
    print(result)
    print("=" * 50)

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        ok(f"'{args.output}' 에 저장했습니다.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROGRAM,
        description="저장소 잡무 자동화 에이전트 (LLM + 휴리스틱 폴백)",
    )
    p.add_argument("--version", action="version", version=f"{PROGRAM} {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("commit-msg", help="스테이징된 변경으로 커밋 메시지 생성")
    c.add_argument("--apply", action="store_true", help="생성한 메시지로 바로 커밋")
    c.set_defaults(func=cmd_commit_msg)

    r = sub.add_parser("readme", help="저장소 스캔 후 README 초안 생성")
    r.add_argument("--path", default=".", help="대상 저장소 경로 (기본: 현재 디렉터리)")
    r.add_argument("--output", default=None, help="출력 파일 (기본: agent.config.json의 readme_output)")
    r.set_defaults(func=cmd_readme)

    s = sub.add_parser("standup", help="최근 git log로 스탠드업 노트 생성")
    s.add_argument("--days", type=int, default=1, help="최근 N일 (기본: 1)")
    s.add_argument("--output", default=None, help="파일로 저장 (지정 시)")
    s.set_defaults(func=cmd_standup)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n⚠️  사용자에 의해 중단되었습니다.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
