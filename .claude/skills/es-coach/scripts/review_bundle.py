#!/usr/bin/env python3
"""段階 O（出力レビュー）のレビュアーに渡す情報を1ファイルにまとめる。

レビュアーが参照ファイルやスクリプトを毎回読み直すと、時間とトークンの大半がそこで消える。
必要な部分だけを抜き出して1ファイルにし、レビュアーにはこれだけを読ませる。

使い方:
  python3 review_bundle.py --workdir $W --company MIXI --question "設問原文" --limit 500 --mode within --round 1

入力（$W 内）: draft.txt（必須）, plan.md, research.md（無ければ history/companies/企業名.md）,
              reviews/output_r{N-1}.md（2回目以降）
出力: $W/bundle_output_r{N}.md（パスと文字数を表示）
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
ROOT = SKILL.parent.parent.parent  # .claude/skills/es-coach → プロジェクトルート
REFS = SKILL / "references"
HISTORY = SKILL / "history"


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def section(md: str, heading: str) -> str:
    """`heading` で始まる見出しから、同じか上位レベルの次の見出しまでを返す。"""
    m = re.search(rf"^(#+) {re.escape(heading)}.*$", md, re.M)
    if not m:
        return ""
    level = len(m.group(1))
    rest = md[m.end():]
    n = re.search(rf"^#{{1,{level}}} ", rest, re.M)
    return (m.group(0) + (rest[: n.start()] if n else rest)).strip()


def run(*args: str) -> str:
    r = subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=ROOT)
    return (r.stdout + r.stderr).strip()


def lessons() -> str:
    t = re.sub(r"<!--.*?-->", "", read(HISTORY / "lessons.md"), flags=re.S)
    out, head = [], None
    for line in t.splitlines():
        if line.startswith("#"):
            head = line
        elif line.strip():
            if head:
                out.append(head)
                head = None
            out.append(line)
    return "\n".join(out) or "（なし）"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workdir", required=True)
    p.add_argument("--company", required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--limit", type=int, required=True)
    p.add_argument("--mode", default="within", choices=["within", "about", "atleast"])
    p.add_argument("--exclude-newlines", action="store_true")
    p.add_argument("--round", type=int, default=1)
    a = p.parse_args()

    w = Path(a.workdir)
    draft = read(w / "draft.txt")
    if not draft:
        sys.exit(f"{w / 'draft.txt'} がありません")

    rubric = read(REFS / "rubric.md")
    mi = read(REFS / "material-index.md")
    research = read(w / "research.md") or read(HISTORY / "companies" / f"{a.company}.md") or "（なし）"
    lint_args = [str(SCRIPTS / "es_lint.py"), "--file", str(w / "draft.txt"),
                 "--limit", str(a.limit), "--mode", a.mode]
    if a.exclude_newlines:
        lint_args.append("--exclude-newlines")

    parts = [
        f"# 段階O レビュー資料 第{a.round}回",
        f"- 企業: {a.company}\n- 設問原文: {a.question}\n- 上限: {a.limit}字（{a.mode}）",
        "## 対象本文（draft.txt）\n\n" + draft,
        "## 骨子（plan.md）\n\n" + (read(w / "plan.md") or "（なし）"),
        "## 機械チェック結果（es_lint.py。文字数・一文の長さ・口癖・誇張・NG表現はこれで判定済み）\n\n```\n"
        + run(*lint_args) + "\n```",
    ]
    if a.round > 1:
        prev = read(w / "reviews" / f"output_r{a.round - 1}.md")
        parts.append(f"## 前回（第{a.round - 1}回）の指摘\n\n" + (section(prev, "要修正") or prev or "（記録なし）"))
    parts += [
        "## 採点基準（rubric.md より）\n\n" + "\n\n".join(
            s for s in (section(rubric, "自動不合格"), section(rubric, "8項目"), section(rubric, "選考通過の観点")) if s),
        "## 正典表・時系列表（material-index.md より）\n\n" + "\n\n".join(
            s for s in (section(mi, "実績数値の正典表"), section(mi, "時系列表")) if s),
        "## 蓄積した教訓（lessons.md。違反は要修正）\n\n" + lessons(),
        f"## {a.company} での過去の修正履歴\n\n" + run(str(SCRIPTS / "knowledge.py"), "list", "--company", a.company, "--last", "10"),
        f"## {a.company} で使用済みのエピソード（同一企業での重複は減点）\n\n"
        + run(str(SCRIPTS / "es_index.py"), "--root", str(ROOT), "--episodes", "--company", a.company),
        "## 企業リサーチメモ\n\n" + research,
    ]
    out = w / f"bundle_output_r{a.round}.md"
    out.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    print(f"{out}（{len(out.read_text(encoding='utf-8'))} 字）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
