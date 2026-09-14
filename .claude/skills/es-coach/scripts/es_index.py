#!/usr/bin/env python3
"""entry_sheet.md（78KB）を毎回全文読まずに扱うための索引ツール。

使い方（cwd がプロジェクトルート、または --root で指定）:
  python3 es_index.py                       # 企業 / 設問 / 行番号 / 上限 / 本文字数 / 比率 の一覧
  python3 es_index.py --company MIXI        # その企業セクションの本文だけ出力
  python3 es_index.py --question 挑戦       # 設問見出しの部分一致検索（回答本文つき）
  python3 es_index.py --episodes            # 企業 × エピソードタグの使用マトリクス
  python3 es_index.py --episodes --company DeNA   # 1社分のタグ一覧

構造の前提:
  - 企業見出しは `# 企業名` または `## 企業名`。見出しレベルが混在しているのが実態なので両方拾う。
  - 企業見出しより下位の見出しはすべて「設問」として扱う（`##` でも `###` でも）。
  - 最初の企業見出しより前は「共通素材」（開発経験・学歴・インターン一覧など）。
  - `## 見出し` が企業かどうかは KNOWN_COMPANIES と簡易ヒューリスティックで判定する。
    新しい企業が誤判定されたら KNOWN_COMPANIES に追加する。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata

# ---- 企業判定 -----------------------------------------------------------------

KNOWN_COMPANIES = {
    "リクルート", "サイボウズ", "GREE", "Sansan", "freee", "ドワンゴ", "WealthNavi",
    "メルカリ", "ピクシブ", "DeNA", "チームラボ", "MIXI",
}

# 企業セクション内に現れる `##` 見出しのうち、企業名に見えてしまうもの
NON_COMPANY_HEADINGS = {
    "キャッチコピー", "志望動機", "自己PR", "自己ＰＲ", "GitHub", "開発経験", "学歴", "インターン",
    "逆質問", "研究内容", "ポートフォリオ", "技術経験", "プロダクトの説明", "総合評価", "AIツールの利用",
}

HEADING_RE = re.compile(r"^(#{1,6})\s*(.*?)\s*$")
LIMIT_RE = re.compile(r"(約|目安)?\s*(\d+)\s*(字|文字)\s*(以内|以上|程度)?")


def looks_like_company(level: int, text: str) -> bool:
    if not text:
        return False
    if text in KNOWN_COMPANIES:
        return True
    if level == 1:
        return True
    if level != 2:
        return False
    if text in NON_COMPANY_HEADINGS:
        return False
    # 短くて、句読点・括弧・空白を含まない見出しは企業名とみなす
    if len(text) > 20:
        return False
    if re.search(r"[、。？?！!（）()【】「」:：/／・\s]", text):
        return False
    # 「〜について」「〜経験」「〜たい」など設問っぽい語尾は除外
    if re.search(r"(について\d*|経験|たい|こと|きっかけ|課題|取り組み|理由|説明|貢献|目標|質問|動機|内容|利用|評価)$", text):
        return False
    return True


# ---- エピソードタグ -----------------------------------------------------------
# material-index.md はこの dict を参照するだけ。タグの正典はここ。

EPISODE_TAGS: dict[str, str] = {
    "iPhone対応": r"iPhone\s*対応|iPhone向け|iPhone(に|へ)移植|iPhoneでも",
    "PR分割・レビュー負荷": r"PRを分割|PR分割|デモ動画|レビュー負荷|レビュアーの負荷|レビュアーが|事前レビュー|レビュー前",
    "不具合修正": r"不具合修正|不具合の原因|原因コード|バグ修正|原因特定|原因を特定",
    "AR倉庫アプリ不具合(3日)": r"AR|アンカー|倉庫|位置ずれ|ポジション",
    "要件解像度の失敗→認識合わせ": r"解像度|疑問点を洗い出|着手前に|着手(の)?時点",
    "React/FastAPI適応": r"React|Fast\s*API",
    "APIリクエスト60〜70%削減": r"60\s*[〜~～]\s*70\s*[%％]",
    "実装速度30〜40%向上": r"30\s*[〜~～]\s*40\s*[%％]",
    "タスク約1か月短縮": r"[1１一]\s*(か|ヶ|カ|ケ|箇)?月(ほど|程|間)?短縮|一月短縮",
    "家族FB・mecap": r"家族|mecap|タイマーアプリ|タスク時間管理アプリ|作業時間を(測定|計測)",
    "NovelAssistEditor": r"NovelAssistEditor|小説",
    "勉強会・登壇": r"登壇|iOSDC|try!?\s*Swift|stmn|勉強会",
    "対話ロボット研究": r"対話ロボット|相槌",
    "AIメンター活用": r"専属のメンター|AIを.{0,8}メンター",
    "TCA": r"\bTCA\b",
    "SPM分割": r"\bSPM\b|パッケージ(に)?分割|モジュール分割",
    "Figmaプロトタイプ": r"Figma",
    "認知負荷・情報共有": r"認知負荷|冒頭に目的",
    "Swift Testing": r"Swift\s*Testing",
    "弱み3つ(テスト/大規模/要件定義)": r"テストコード|スケーラビリティ|要件定義",
}

NUMBER_RE = re.compile(r"\d+\s*[〜~～]?\s*\d*\s*(%|％|か月|ヶ月|カ月|名|年|倍|件|人|回|分|時間|週間)")


# ---- パース -------------------------------------------------------------------

class Section:
    def __init__(self, company: str, company_line: int, company_level: int):
        self.company = company
        self.company_line = company_line
        self.company_level = company_level
        self.questions: list[Question] = []
        self.lines: list[str] = []  # セクション全体（見出し含む）

    def text(self) -> str:
        return "\n".join(self.lines)


class Question:
    def __init__(self, title: str, line: int, level: int):
        self.title = title
        self.line = line
        self.level = level
        self.body_lines: list[str] = []

    def body(self) -> str:
        return "\n".join(self.body_lines).strip("\n")

    def limit(self) -> tuple[int | None, str]:
        m = LIMIT_RE.search(self.title)
        if not m:
            return None, ""
        n = int(m.group(2))
        prefix, suffix = m.group(1) or "", m.group(4) or ""
        if suffix == "以上":
            mode = "atleast"
        elif prefix in ("約", "目安") or suffix == "程度":
            mode = "about"
        else:
            mode = "within"
        return n, mode


def count_chars(text: str) -> int:
    return len(unicodedata.normalize("NFC", text).strip("\n"))


def parse(path: str) -> tuple[list[str], list[Section]]:
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    common: list[str] = []
    sections: list[Section] = []
    cur: Section | None = None
    curq: Question | None = None

    for i, raw in enumerate(lines, start=1):
        m = HEADING_RE.match(raw)
        if m:
            level, text = len(m.group(1)), m.group(2)
            # 企業見出し？（`#` 企業の直後に `## 新企業` が来るケースがあるので、レベルの大小では判定しない）
            if looks_like_company(level, text):
                cur = Section(text, i, level)
                cur.lines.append(raw)
                sections.append(cur)
                curq = None
                continue
            if cur is not None:
                curq = Question(text, i, level)
                cur.questions.append(curq)
                cur.lines.append(raw)
                continue
        if cur is None:
            common.append(raw)
        else:
            cur.lines.append(raw)
            if curq is not None:
                curq.body_lines.append(raw)
    return common, sections


# ---- 出力 ---------------------------------------------------------------------

def fmt_ratio(n: int, limit: int | None) -> str:
    if not limit:
        return "-"
    r = n / limit * 100
    flag = "" if 90 <= r <= 100 else (" OVER" if r > 100 else " SHORT")
    return f"{r:.0f}%{flag}"


def cmd_list(sections: list[Section], common: list[str]) -> None:
    print(f"共通素材: L1〜L{len(common)}（企業見出しより前。開発経験・学歴・インターン一覧など）")
    print()
    print(f"{'企業':<12} {'L':>4}  {'設問（先頭40字）':<42} {'上限':>5} {'字数':>5}  比率")
    print("-" * 90)
    for s in sections:
        print(f"{s.company:<12} {s.company_line:>4}  {'(' + '#' * s.company_level + ' セクション見出し)':<42}")
        for q in s.questions:
            limit, mode = q.limit()
            n = count_chars(q.body())
            title = q.title[:40] + ("…" if len(q.title) > 40 else "")
            lim = f"{limit}" if limit else "-"
            print(f"{'':<12} {q.line:>4}  {title:<42} {lim:>5} {n:>5}  {fmt_ratio(n, limit)}")
        print()


def find_section(sections: list[Section], name: str) -> Section | None:
    for s in sections:
        if s.company.lower() == name.lower():
            return s
    for s in sections:
        if name.lower() in s.company.lower():
            return s
    return None


def cmd_company(sections: list[Section], name: str) -> int:
    s = find_section(sections, name)
    if not s:
        print(f"企業セクションが見つかりません: {name}", file=sys.stderr)
        print("既存: " + ", ".join(x.company for x in sections), file=sys.stderr)
        return 1
    print(f"# {s.company}  (L{s.company_line}〜L{s.company_line + len(s.lines) - 1}, 見出しレベル {'#' * s.company_level})")
    print(s.text())
    return 0


def cmd_question(sections: list[Section], keyword: str) -> None:
    kw = keyword.lower()
    hits = 0
    for s in sections:
        for q in s.questions:
            if kw in q.title.lower():
                hits += 1
                limit, _ = q.limit()
                n = count_chars(q.body())
                print(f"## [{s.company}] L{q.line}  {q.title}")
                print(f"   上限 {limit or '-'} / 字数 {n} / {fmt_ratio(n, limit)}")
                print(q.body())
                print()
    if hits == 0:
        print(f"一致する設問なし: {keyword}")


def tags_in(text: str) -> list[str]:
    return [tag for tag, pat in EPISODE_TAGS.items() if re.search(pat, text)]


def cmd_episodes(sections: list[Section], only: str | None) -> None:
    tags = list(EPISODE_TAGS)
    if only:
        s = find_section(sections, only)
        if not s:
            print(f"企業セクションが見つかりません: {only}", file=sys.stderr)
            return
        print(f"# {s.company} で使用済みのエピソード")
        for q in s.questions:
            body = q.body()
            found = tags_in(body)
            nums = NUMBER_RE.findall(body)
            print(f"- L{q.line} {q.title[:40]}")
            print(f"    タグ: {', '.join(found) if found else '（なし）'}   数値表現: {len(nums)} 個")
        return

    # マトリクス
    usage: dict[str, set[str]] = {t: set() for t in tags}
    for s in sections:
        for t in tags_in(s.text()):
            if t in usage:
                usage[t].add(s.company)
    print(f"{'エピソード':<32} {'社数':>3}  使用企業")
    print("-" * 90)
    for t in tags:
        cos = sorted(usage[t])
        print(f"{t:<32} {len(cos):>3}  {', '.join(cos) if cos else '（未使用）'}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".", help="entry_sheet.md があるディレクトリ（既定: cwd）")
    p.add_argument("--file", default="entry_sheet.md", help="対象ファイル名")
    p.add_argument("--company", help="企業セクションを出力（--episodes と併用で1社分のタグ一覧）")
    p.add_argument("--question", help="設問見出しの部分一致検索")
    p.add_argument("--episodes", action="store_true", help="エピソード使用マトリクス")
    args = p.parse_args()

    path = os.path.join(args.root, args.file)
    if not os.path.exists(path):
        print(f"ファイルがありません: {path}", file=sys.stderr)
        return 1
    common, sections = parse(path)

    if args.episodes:
        cmd_episodes(sections, args.company)
        return 0
    if args.company:
        return cmd_company(sections, args.company)
    if args.question:
        cmd_question(sections, args.question)
        return 0
    cmd_list(sections, common)
    return 0


if __name__ == "__main__":
    sys.exit(main())
