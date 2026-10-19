# ナレッジ（修正履歴）の蓄積と参照

自動レビューやユーザーの指示で、骨子（プラン）や回答（出力）を直した内容を履歴として残し、次の ES づくりとレビューに生かす。
ナレッジはスキル内の `history/` に置かれ、すべての企業・設問で共有される。

| ファイル | 役割 | 更新方法 |
|---|---|---|
| `history/history.jsonl` | 修正1件ごとの生の記録（いつ・どの段階・何を・どう直したか・教訓） | `knowledge.py add` のみ（手で編集しない） |
| `history/lessons.md` | 繰り返し出た教訓・ユーザーの好みを一般化したルール集 | 下の手順で追記・整理する |

以下 `KN=.claude/skills/es-coach/scripts/knowledge.py`（`python3 $KN ...` で実行する）。

## 参照する（読む）タイミング

1. **作業開始時**: `python3 $KN brief --company 企業名` を読み、教訓を今回の作業ルールに加える。その企業で過去に直された点も確認する。
2. **骨子・本文を書く前**: 該当カテゴリの教訓（骨子なら answer・structure・episode・appeal、本文なら fact・style・length・appeal）を見直す。
3. **自動レビュー時**: レビュアーにも `python3 $KN brief --company 企業名` を読ませる。lessons.md の教訓は追加のチェック項目で、違反は「要修正」。直近の履歴と同じ種類の誤りの繰り返しも確認させる。

## 記録する（書く）タイミング

次の修正をしたら、**直した直後に1件ずつ** `python3 $KN add` で記録する。

- 自動レビューの「要修正」を直したとき（`--source review --round N`、段階 P は `--stage plan`、段階 O は `--stage output`）
- ユーザーの指示・コメントで骨子や回答を直したとき。骨子の合意前の指示も、報告後の「もっと〜して」「ここは違う」も含む（`--source prompt`）
- 記録しないもの: 直さなかった「提案」、その場限りの事実の追加（ユーザーが新しい数値を教えてくれた、など。数値自体は正典表側の話）

```bash
python3 .claude/skills/es-coach/scripts/knowledge.py add --stage output --source review --round 1 \
  --category appeal --company MIXI --question "挑戦したいこと" \
  --problem "第2段落が「チームで協力して課題を解決」で終わり、誰でも書ける内容だった" \
  --fix "PR分割を選んだ判断理由と、約1か月短縮の結果を書いた" \
  --lesson "エピソード段落は一般論で締めず、自分が選んだ方法とその理由で締める"
```

- `--problem` は具体的に（どの段落の何が）、`--lesson` は**別の企業・別の設問でも使える一般的な形**で書く。
- ユーザーの好み・方針で今後も続くもの（例:「燈は実名で書く」「志望動機に研究の話は入れない」）は `--source prompt` で記録し、lesson に好みとして明記する。

## 教訓を整理する（lessons.md への昇格）

報告の前に `python3 $KN promote` を実行し、候補があれば次のようにする。

- 同じ趣旨の教訓が2回以上出ていたら、1つの一般的なルールにまとめて lessons.md の該当カテゴリに1行で追記する。
- ユーザーが明示した好み・方針（source=prompt）は、1回でも lessons.md に追記してよい。
- 既存のルール（`style-guide.md`、`rubric.md` など）と矛盾する教訓は、追記せずユーザーに確認する。
- lessons.md を変更したら、報告でその内容を伝える。
