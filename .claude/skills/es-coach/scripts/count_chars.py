#!/usr/bin/env python3
"""ES 回答の文字数を数え、上限に対する判定を返す。

使い方:
  python3 count_chars.py --file answer.txt --limit 500
  python3 count_chars.py --text "..." --limit 400 --mode about
  echo "..." | python3 count_chars.py --limit 500 --exclude-newlines

数え方（既定）:
  NFC 正規化したうえで、改行・空白・全角/半角・句読点・記号をすべて 1 文字として数える。
  これは Web フォームの maxlength に最も近い、最も厳しい慣習。ここで収まっていれば
  どの企業の数え方でも超過しない。

判定モード（--mode）:
  within  「N字以内」        → 90〜100% を OK
  about   「約N字 / N字程度」 → 90〜110% を OK
  atleast 「N字以上」        → 100〜120% を OK
  --min-ratio / --max-ratio で上書き可。

終了コード: 判定 OK なら 0、OVER/SHORT なら 1（grader やスクリプトから直接使える）。
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata

MODE_RANGES = {
    "within": (0.90, 1.00),
    "about": (0.90, 1.10),
    "atleast": (1.00, 1.20),
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    # 末尾の改行だけは数えない（ファイル末尾の改行を文字数に含めないため）
    return text.rstrip("\n")


def count_all(text: str) -> int:
    return len(text)


def count_without_newlines(text: str) -> int:
    return len(text.replace("\r", "").replace("\n", ""))


def count_without_spaces(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def judge(count: int, limit: int, lo: float, hi: float) -> tuple[str, float]:
    ratio = count / limit if limit else 0.0
    if ratio > hi + 1e-9:
        return "OVER", ratio
    if ratio < lo - 1e-9:
        return "SHORT", ratio
    return "OK", ratio


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group()
    src.add_argument("--file", help="回答本文のファイル")
    src.add_argument("--text", help="回答本文を直接渡す")
    p.add_argument("--limit", type=int, help="上限文字数")
    p.add_argument("--mode", choices=MODE_RANGES.keys(), default="within", help="上限表記の種類（既定: within）")
    p.add_argument("--min-ratio", type=float, help="OK とみなす下限比率（--mode を上書き）")
    p.add_argument("--max-ratio", type=float, help="OK とみなす上限比率（--mode を上書き）")
    p.add_argument("--exclude-newlines", action="store_true", help="判定に改行を含めない（企業が明記している場合のみ）")
    p.add_argument("--exclude-spaces", action="store_true", help="判定に空白も含めない")
    p.add_argument("--quiet", action="store_true", help="判定行だけ出力")
    args = p.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            raw = f.read()
    elif args.text is not None:
        raw = args.text
    else:
        raw = sys.stdin.read()

    text = normalize(raw)
    n_all = count_all(text)
    n_nonl = count_without_newlines(text)
    n_nosp = count_without_spaces(text)

    if args.exclude_spaces:
        target, label = n_nosp, "空白除く"
    elif args.exclude_newlines:
        target, label = n_nonl, "改行除く"
    else:
        target, label = n_all, "改行込み"

    if not args.quiet:
        print(f"改行込み: {n_all}")
        print(f"改行除く: {n_nonl}")
        print(f"空白除く: {n_nosp}")

    if args.limit is None:
        return 0

    lo, hi = MODE_RANGES[args.mode]
    if args.min_ratio is not None:
        lo = args.min_ratio
    if args.max_ratio is not None:
        hi = args.max_ratio
    verdict, ratio = judge(target, args.limit, lo, hi)
    print(
        f"判定: {verdict}  ({label} {target} / 上限 {args.limit} = {ratio*100:.0f}%,"
        f" 許容 {lo*100:.0f}〜{hi*100:.0f}%)"
    )
    if verdict == "OVER":
        print(f"→ {target - int(args.limit*hi)} 字削る必要あり")
    elif verdict == "SHORT":
        print(f"→ あと {int(args.limit*lo) - target + 1} 字以上増やす必要あり")
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
