#!/usr/bin/env python3
"""ES 回答の機械的に判定できる項目をまとめてチェックする（レビュアーを呼ぶ前に通す）。

使い方:
  python3 es_lint.py --file draft.txt --limit 500 --mode within
  python3 es_lint.py --file draft.txt --limit 400 --mode about --exclude-newlines

判定する項目（rubric.md の機械チェック可能な部分）:
  ERROR（直してから次へ）
    - 文字数が許容帯の外（count_chars.py と同じ数え方）
    - 一文 100 字超
    - 口癖の上限超過（単なる/単に 合計1、だけでなく 1、と考えています 1、設計思想 1、認知負荷 1、痛感しました 1）
    - 誇張副詞（飛躍的、劇的、徹底的、大幅に、極めて、非常に、圧倒的）
    - 「貴社」2回以上
    - インターン向け表現の残り（インターンでは、インターンを志望、現在〜従事しています など）
    - 減点表現（学ばせていただ、成長できる環境、かもしれません）
    - 使用禁止の数値（根拠のない改善率 30〜40%・60〜70%）
    - 感嘆符・『』・絵文字・ダッシュ
    - AIらしい表現（決め台詞・抽象語の飾り。style-guide.md の該当節）
    - 「」が3か所以上（強調に使っている可能性が高い）
  WARN（目で確認する）
    - 「」の各使用箇所（引用・表示文字列以外の強調なら直す）
    - 散文中のコロン・矢印
    - 正典表（material-index.md）に見当たらない数値表現
    - である調・常体の文末

終了コード: ERROR が無ければ 0、あれば 1。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from count_chars import MODE_RANGES, count_all, count_without_newlines, judge, normalize  # noqa: E402

SKILL = Path(__file__).resolve().parent.parent
MATERIAL_INDEX = SKILL / "references" / "material-index.md"

HABITS = [  # (表示名, 正規表現, 上限)
    ("単なる／単に", r"単なる|単に", 1),
    ("だけでなく", r"だけでなく", 1),
    ("と考えています", r"と考えています", 1),
    ("設計思想", r"設計思想", 1),
    ("認知負荷", r"認知負荷", 1),
    ("痛感しました", r"痛感しました", 1),
    ("貴社", r"貴社", 1),
]
EXAGGERATIONS = ["飛躍的", "劇的", "徹底的", "大幅に", "極めて", "非常に", "圧倒的"]
FORBIDDEN = [  # (理由, 正規表現)
    ("インターン向け表現", r"インターンでは|インターンシップで|インターンを志望|貴社のインターン"),
    ("終了済みインターンの現在形", r"現在.{0,15}従事しています"),
    ("減点表現（受け身）", r"学ばせていただ"),
    ("減点表現（環境目当て）", r"成長できる環境"),
    ("減点表現（自信の無さ）", r"かもしれません"),
    ("使用禁止の数値（根拠のない改善率）", r"30\s*[〜~～-]\s*40\s*[%％]|60\s*[〜~～-]\s*70\s*[%％]"),
    ("感嘆符", r"[!！]"),
    ("『』", r"[『』]"),
    ("ダッシュ", r"――|—|―"),
    ("AIらしい表現", r"こそが|が鍵と|鍵となる|まさに|本質的|解像度|言語化|価値提供|という観点|という構造|と言えます|私の原点"),
]
NUMBER = re.compile(r"約?\d+(?:\s*[〜~～・]\s*\d+)?\s*(?:%|％|か月|ヶ月|カ月|名|年|倍|日|件|社|回|週|人|つ)")
PLAIN_FORM_END = re.compile(r"(である|だ|した|する|ない|った)。")


def sentences(text: str) -> list[str]:
    out = []
    for para in text.splitlines():
        for s in re.split(r"(?<=。)", para):
            if s.strip():
                out.append(s.strip())
    return out


def canonical_text() -> str:
    try:
        t = MATERIAL_INDEX.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"## 実績数値の正典表(.*?)(?=\n## )", t, re.S)
    return re.sub(r"\s", "", m.group(1) if m else t)


def lint(text: str, limit: int | None, mode: str, exclude_newlines: bool):
    errors, warns = [], []

    if limit:
        n = count_without_newlines(text) if exclude_newlines else count_all(text)
        lo, hi = MODE_RANGES[mode]
        verdict, ratio = judge(n, limit, lo, hi)
        if verdict != "OK":
            errors.append(f"[文字数] {verdict}: {n} / {limit}（{ratio*100:.0f}%、許容 {lo*100:.0f}〜{hi*100:.0f}%）")

    for s in sentences(text):
        if len(s) > 100:
            errors.append(f"[一文100字超] {len(s)}字: 「{s[:30]}…」")

    for name, pat, cap in HABITS:
        c = len(re.findall(pat, text))
        if c > cap:
            errors.append(f"[口癖] 「{name}」{c}回（上限 {cap}）")

    for w in EXAGGERATIONS:
        if w in text:
            errors.append(f"[誇張副詞] 「{w}」")

    for why, pat in FORBIDDEN:
        for m in re.finditer(pat, text):
            errors.append(f"[{why}] 「{m.group(0)}」")

    if any(ord(ch) > 0xFFFF for ch in text):
        errors.append("[絵文字・特殊記号] BMP 外の文字がある（フォームで2文字扱いになる）")

    quotes = re.findall(r"「[^」]*」", text)
    if len(quotes) >= 3:
        errors.append(f"[「」の多用] {len(quotes)}か所。強調の「」は外す（引用・表示文字列だけ残す）")
    for q in quotes:
        warns.append(f"[「」] {q} → 引用・表示文字列でなければ「」を外す")
    for m in re.finditer(r"[：:→⇒]", text):
        warns.append(f"[記号] 「{m.group(0)}」→ 散文では接続詞か句点で区切る")

    canon = canonical_text()
    for m in NUMBER.finditer(text):
        tok = re.sub(r"\s", "", m.group(0))
        core = tok.lstrip("約")
        if re.fullmatch(r"\d{4}年", core):  # 年号は時系列表で確認する
            continue
        if core not in canon:
            warns.append(f"[正典表に無い数値?] 「{tok}」→ material-index.md の正典表・ユーザー発言で確認")

    for s in sentences(text):
        if PLAIN_FORM_END.search(s) and not s.endswith(("ました。", "ます。", "です。", "でした。")):
            warns.append(f"[常体の文末?] 「…{s[-15:]}」")

    return errors, warns


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--file")
    src.add_argument("--text")
    p.add_argument("--limit", type=int)
    p.add_argument("--mode", choices=MODE_RANGES.keys(), default="within")
    p.add_argument("--exclude-newlines", action="store_true")
    a = p.parse_args()

    raw = Path(a.file).read_text(encoding="utf-8") if a.file else a.text
    text = normalize(raw)
    errors, warns = lint(text, a.limit, a.mode, a.exclude_newlines)

    print(f"文字数: 改行込み {count_all(text)} / 改行除く {count_without_newlines(text)}")
    print(f"判定: {'NG' if errors else 'OK'}（ERROR {len(errors)} / WARN {len(warns)}）")
    for e in errors:
        print(f"ERROR {e}")
    for w in warns:
        print(f"WARN  {w}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
