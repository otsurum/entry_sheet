#!/usr/bin/env python3
"""entry_sheet.md に回答を追記する。既存の慣習（企業セクション → 設問見出し → 本文）を機械的に守る。

使い方:
  python3 append_entry.py --company MIXI --question "挑戦してみたいこと（500字以内）" --body-file answer.txt --dry-run
  python3 append_entry.py --company マネーフォワード --question "志望動機（400字以内）" < answer.txt

挙動:
  - `# 企業名` / `## 企業名` の既存セクションがあれば、その末尾に追記する。設問見出しのレベルは
    そのセクションに合わせる（`#` 配下なら `##`、`##` 配下なら `###`）。見出しレベルが混在している
    ファイルなので、正規化はせず既存に追従する（git 差分を汚さないため）。
  - 無ければファイル末尾に `## 企業名` + `### 設問` を新設する。
  - 同じ設問見出しが既にあれば上書きせず、`（v2 2026-09-14）` のように版を付けて追加する。
    過去版を残すのがこのリポジトリの慣習。
  - --dry-run で挿入位置と内容だけ表示する。まず dry-run で確認してから実行すること。
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import es_index  # noqa: E402


VERSION_RE = re.compile(r"[（(]v(\d+) \d{4}-\d{2}-\d{2}[)）]\s*$")


def normalize_title(t: str) -> str:
    t = VERSION_RE.sub("", t.strip())
    return re.sub(r"\s+", "", t)


def build_block(level: int, title: str, body: str) -> list[str]:
    return ["", "#" * level + " " + title, body.strip("\n"), ""]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".", help="entry_sheet.md があるディレクトリ（既定: cwd）")
    p.add_argument("--file", default="entry_sheet.md")
    p.add_argument("--company", required=True, help="企業名（見出しに使う表記そのまま）")
    p.add_argument("--question", required=True, help="設問見出し。設問原文＋（N字以内）を推奨")
    p.add_argument("--body-file", help="本文ファイル。省略時は stdin")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--date", default=dt.date.today().isoformat(), help="版表記に使う日付")
    args = p.parse_args()

    path = os.path.join(args.root, args.file)
    if not os.path.exists(path):
        print(f"ファイルがありません: {path}", file=sys.stderr)
        return 1

    if args.body_file:
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read()
    else:
        body = sys.stdin.read()
    body = body.strip("\n")
    if not body:
        print("本文が空です", file=sys.stderr)
        return 1

    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    _, sections = es_index.parse(path)
    section = None
    for s in sections:
        if s.company.strip().lower() == args.company.strip().lower():
            section = s
            break

    title = args.question.strip()

    if section is None:
        q_level = 3
        block = ["", "## " + args.company] + build_block(q_level, title, body)[1:]
        # ファイル末尾の空行を整える
        while lines and lines[-1].strip() == "":
            lines.pop()
        insert_at = len(lines)  # 0-based index → 追記は L(insert_at+1) から
        new_lines = lines + block
        where = f"ファイル末尾に新規セクション `## {args.company}` を作成（L{insert_at + 1}〜）"
    else:
        q_level = section.company_level + 1
        # 同一設問があれば版を付ける（既存の最大版 +1、初回の重複は v2）
        base = normalize_title(title)
        same = [q.title for q in section.questions if normalize_title(q.title) == base]
        if same:
            versions = [int(m.group(1)) for t in same for m in [VERSION_RE.search(t)] if m]
            n = (max(versions) + 1) if versions else 2
            title = f"{title}（v{n} {args.date}）"
        # セクション末尾（末尾の空行を除いた位置）を求める
        start = section.company_line - 1  # 0-based
        end = start + len(section.lines)  # exclusive
        while end > start + 1 and lines[end - 1].strip() == "":
            end -= 1
        block = build_block(q_level, title, body)
        new_lines = lines[:end] + block + lines[end:]
        insert_at = end
        where = (
            f"既存セクション `{'#' * section.company_level} {section.company}`（L{section.company_line}）の末尾、"
            f"L{insert_at + 1} から `{'#' * q_level} {title}` として挿入"
        )

    print(where)
    if args.dry_run:
        print("----- 挿入内容 -----")
        print("\n".join(block).strip("\n"))
        print("----- (dry-run: 書き込みなし) -----")
        return 0

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))
        if not "\n".join(new_lines).endswith("\n"):
            f.write("\n")
    print(f"書き込み完了: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
