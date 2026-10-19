#!/usr/bin/env python3
"""レビュー・ユーザーの指示で骨子や回答を直した内容を、ナレッジとして蓄積・参照する。

保存先: .claude/skills/es-coach/history/
  history.jsonl  1行1件の修正記録（全企業・全設問で共有。手で編集しない）
  lessons.md     繰り返し出た教訓を一般化したルール集（手で追記・整理する）

usage:
  knowledge.py add --stage plan|output --source review|prompt --category appeal \\
      --problem "何が問題だったか" --fix "どう直したか" --lesson "次回から守る一般化したルール" \\
      [--company MIXI] [--question "挑戦したいこと"] [--round 2]
  knowledge.py list [--category appeal] [--stage output] [--company MIXI] [--last 30]
  knowledge.py brief [--company MIXI] [--last 5]    # 作成前に読む要約（教訓＋その企業の履歴）
  knowledge.py promote                              # lessons.md への昇格候補を表示

source: review（自動レビューの「要修正」を直した） / prompt（ユーザーの指示・コメントで直した）
category: answer（設問への回答・結論） / structure（構成・字数配分） / episode（エピソード・素材の選択） /
          fact（事実・数値・時制） / company（企業との接点・リサーチ） /
          appeal（選考通過の観点: 評価ポイント・差別化・人物像・減点表現） /
          style（文体・口癖・表記） / length（文字数） / other
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

KDIR = Path(__file__).resolve().parent.parent / "history"
HISTORY = KDIR / "history.jsonl"
LESSONS = KDIR / "lessons.md"
STAGES = ["plan", "output"]
SOURCES = ["review", "prompt"]
CATEGORIES = ["answer", "structure", "episode", "fact", "company", "appeal", "style", "length", "other"]


def load():
    if not HISTORY.exists():
        return []
    items = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"skip broken line: {line[:60]}", file=sys.stderr)
    return items


def fmt(e):
    head = f"- [{e['date']}] {e['category']} / {e['stage']} / {e['source']}"
    for k in ("company", "question"):
        if e.get(k):
            head += f" / {e[k]}"
    if e.get("round"):
        head += f" / 第{e['round']}回"
    return (f"{head}\n  - 問題: {e['problem']}\n  - 修正: {e['fix']}\n"
            f"  - 教訓: {e['lesson']}")


def cmd_add(a):
    KDIR.mkdir(parents=True, exist_ok=True)
    e = dict(date=datetime.now().strftime("%Y-%m-%d"), stage=a.stage, source=a.source,
             category=a.category, problem=a.problem, fix=a.fix, lesson=a.lesson)
    for k in ("company", "question", "round"):
        if getattr(a, k):
            e[k] = getattr(a, k)
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"記録しました（累計 {len(load())} 件）")


def filtered(a):
    xs = load()
    for k in ("category", "stage", "company"):
        v = getattr(a, k, None)
        if v:
            xs = [e for e in xs if e.get(k) == v]
    return xs[-a.last:] if a.last else xs


def cmd_list(a):
    xs = filtered(a)
    print(f"# 修正履歴（{len(xs)} 件）\n")
    print("\n".join(fmt(e) for e in xs) if xs else "（まだ履歴はありません）")


def lessons_body():
    """lessons.md からコメントと空のカテゴリ見出しを除いた本文（読む量を減らすため）。"""
    if not LESSONS.exists():
        return "（なし）"
    t = re.sub(r"<!--.*?-->", "", LESSONS.read_text(encoding="utf-8"), flags=re.S)
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


def cmd_brief(a):
    print("# ナレッジ要約（骨子・本文を書く前と、レビュー時に必ず確認）\n")
    print("## 蓄積した教訓（lessons.md）\n")
    print(lessons_body())
    xs = load()
    if not xs:
        print("\n## 直近の修正履歴\n\n（まだ履歴はありません）")
        return
    cnt = Counter(e["category"] for e in xs)
    print("\n## よく指摘されるカテゴリ\n")
    print(" / ".join(f"{c}: {n}件" for c, n in cnt.most_common()))
    if a.company:
        cx = [e for e in xs if e.get("company") == a.company]
        print(f"\n## {a.company} での修正履歴（{len(cx)} 件）\n")
        print("\n".join(fmt(e) for e in cx) if cx else "（なし）")
    if a.last:
        print(f"\n## 直近の修正履歴（{min(a.last, len(xs))} 件）\n")
        print("\n".join(fmt(e) for e in xs[-a.last:]))


def cmd_promote(a):
    groups = defaultdict(list)
    for e in load():
        groups[e["category"]].append(e)
    lessons_text = LESSONS.read_text(encoding="utf-8") if LESSONS.exists() else ""
    print("# lessons.md への昇格候補\n")
    print("同じカテゴリで2回以上記録された教訓のうち、lessons.md に未記載のもの。")
    print("似た教訓はまとめて1つの一般的なルールにしてから lessons.md の該当カテゴリに追記する。")
    print("source=prompt（ユーザーが明示した好み・方針）は1回でも昇格してよい。\n")
    found = False
    for cat in CATEGORIES:
        all_ = groups.get(cat, [])
        xs = [e for e in all_ if e["lesson"] not in lessons_text
              and (len(all_) >= 2 or e["source"] == "prompt")]
        if xs:
            found = True
            print(f"## {cat}（累計 {len(all_)} 件）")
            for e in xs:
                print(f"- {e['lesson']}  （{e['date']} {e['source']} {e.get('company', '')}）")
            print()
    if not found:
        print("（候補なし）")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("--stage", choices=STAGES, required=True)
    p.add_argument("--source", choices=SOURCES, required=True)
    p.add_argument("--category", choices=CATEGORIES, required=True)
    p.add_argument("--problem", required=True)
    p.add_argument("--fix", required=True)
    p.add_argument("--lesson", required=True)
    p.add_argument("--company")
    p.add_argument("--question")
    p.add_argument("--round", type=int)
    p.set_defaults(func=cmd_add)
    p = sub.add_parser("list")
    p.add_argument("--category", choices=CATEGORIES)
    p.add_argument("--stage", choices=STAGES)
    p.add_argument("--company")
    p.add_argument("--last", type=int, default=30)
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("brief")
    p.add_argument("--last", type=int, default=0, help="全企業の直近履歴も表示する件数（既定 0。教訓は lessons.md に集約済み）")
    p.add_argument("--company")
    p.set_defaults(func=cmd_brief)
    p = sub.add_parser("promote")
    p.set_defaults(func=cmd_promote)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
