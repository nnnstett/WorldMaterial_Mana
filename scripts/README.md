# scripts/ — ドキュメント検証ツール

World Material "Mana" のドキュメント群を機械的に検証する CLI とライブラリ。

- **ゼロ依存**: Python 3.11 stdlib のみ。`pip install` 不要
- **テスト**: `unittest`（stdlib）で TDD
- **対象スコープ**: `docs/architecture.md`（§4 記述規約）と `docs/writing-rules.md` が定める規約のうち、機械判定可能な条項（対応は [architecture.md §5.5 保証マップ](../docs/architecture.md#55-保証マップ)）
- **設計**: 全ドキュメントを 1 つのトポロジーグラフとして扱い、その上でリンク・参照・分量を検証
- **意味検証**: `semantic_eval.py` で LLM 用の盲検ケースパックを生成・封印・集計し、ケースから `FAQ.md` を生成

## 使い方

```sh
# ユニットテスト（チェッカー自体）
make test
# 全ドキュメントをチェック
make check
# トポロジーを build/ に出力（JSON + Graphviz DOT）
make topology

# 特定ファイルだけ報告
python3 scripts/check.py world/core/axioms.md world/core/theorems.md

# LLM セマンティック検証の操作一覧
python3 scripts/semantic_eval.py --help
# セマンティック検証ケースから FAQ.md を再生成
make faq
```

終了コード:
- `0`: error 無し（warning のみは許容）
- `1`: error あり

## ディレクトリ構成

```
scripts/
├── check.py                       # CLI エントリ
├── semantic_eval.py               # 盲検 LLM セマンティック検証
├── README.md                      # 本ファイル
├── doc_check/
│   ├── model.py                   # Markdown パース + GitHub 互換 slugify
│   ├── topology.py                # 相互参照グラフ（ノード=ファイル/見出し、エッジ=リンク）
│   ├── config.py + thresholds.json  # 閾値・ファイルスコープ別ルール
│   ├── report.py                  # Finding / Severity / 終了コード
│   ├── runner.py                  # ロード → トポロジー → チェック実行
│   └── checks/                    # 個別チェック
└── tests/                         # unittest（ゼロ依存）
```

セマンティック検証の脅威モデル、ケース形式（1ファイル `ask`/`key`）、候補／採点パックの実行手順、
`FAQ.md` 生成は [LLM セマンティック検証](../docs/semantic-validation.md)を参照。`semantic-tests/public/`
は候補実行時にリポジトリとWebを遮断する運用で回帰判定にも使え、`make faq` で読者向け `FAQ.md`
（リポジトリ直下）を生成する。

## ファイルスコープ別ルール

`docs/architecture.md` で定めた分類体系・記述規約は、ファイルの役割によって適用範囲が異なる。
スコープは `doc_check/config.py` で判定する。

| スコープ | 例 | 適用ルール |
|---|---|---|
| core | `world/core/axioms.md`, `theorems.md`, `open-questions.md` | links, references, ids, sections, roles, forbidden, paths, volume, todos, meta_info |
| applied | `world/magic.md`, `world/dungeons.md` 等 | links, references, sections, forbidden, paths, volume, todos, meta_info |
| glossary | `glossary.md` | links, forbidden, paths, meta_info |
| meta | `docs/architecture.md`, `docs/writing-rules.md`, `docs/design-notes.md` | links のみ（規約文書間の相互参照の実在検査。内容系は NG 例を意図的に含むため適用外） |
| other | `README.md` 等 | links |

## チェック一覧

チェック ID と、それが保証する規約条項の対応は
[architecture.md §5.5 保証マップ](../docs/architecture.md#55-保証マップ) が正である
（本 README には再掲しない）。保証マップと実装の一致は
`tests/test_assurance_map.py` が検査し、片方だけの追加・削除は `make test` で落ちる。

各チェックの検出仕様の細部（誤検出回避の除外規則など）は、
`doc_check/checks/` の各モジュール docstring に実装と隣接して記す。

## 例外コメント

長さ・分量系を意図的に超過させたい場合、対象の直前に許容コメントを置く:

```markdown
<!-- check:length-exempt 列挙が必要な箇所 -->
- 項目 1
- 項目 2
- ...
```

直後の非空ブロックに対する分量 finding を抑制する。

## 閾値の決め方

`thresholds.json` の初期値は、テクニカルライティングおよび日本語スタイルガイドの定石を参考に
した暫定値:

| キー | 初期値 | 根拠 |
|---|---|---|
| `proposition_max_sentences` | 2 | architecture.md §4.1 命題は 1〜2 文 |
| `paragraph_max_sentences` | 5 | 一般的な日本語テクニカルライティングの目安 |
| `sentence_max_chars` | 80 | 横書き読みやすさの目安（60〜80 字） |
| `detail_section_max_lines` | 25 | スクロール無しで把握できる範囲 |
| `list_max_items` | 12 | ワーキングメモリの目安 |
| `heading_max_depth` | 4 | H4 まで（H5 以上は構造の悪臭） |
| `entry_max_chars` | 1500 | 1 命題エントリの本文サイズ目安 |
| `applied_file_max_lines` | 400 | 単一ファイルとして読み通せる範囲 |

書き始めた後に実データで調整する。

## トポロジー出力

```sh
make topology
# build/topology.json  # ノード（ファイル + アンカー）とエッジ（リンク）
# build/topology.dot   # Graphviz: dot -Tsvg build/topology.dot > topology.svg
```

可視化や独自分析に使える。CI でもアーティファクトとして保存される。

## 統合

- **Makefile**: `make test` / `make check` / `make topology`
- **lefthook**: `lefthook.yml`（プロジェクトルート）。`lefthook install` でフック有効化
- **GitHub Actions**: `.github/workflows/check.yml`。doc-check は CI ゲート（error で PR を失敗させる）

## チェッカー自体の開発

TDD で進める。

```sh
make test   # 常にグリーンであるべき
```

新しいチェックを追加する場合: テストを先に書く → `doc_check/checks/foo.py` を実装 → `runner.py` に配線 → `RULES_BY_SCOPE` を更新 → 保証マップ（`docs/architecture.md` §5.5）に行を追加（`tests/test_assurance_map.py` が同期を検査する）。
