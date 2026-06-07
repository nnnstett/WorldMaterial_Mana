# scripts/ — ドキュメント整合性チェッカー

World Material "Mana" のドキュメント群を機械的に検証する CLI とライブラリ。

- **ゼロ依存**: Python 3.11 stdlib のみ。`pip install` 不要
- **テスト**: `unittest`（stdlib）で TDD
- **対象スコープ**: `docs/architecture.md` の §4 記述規約および `docs/redesign-plan.md` Phase 1 仕様
- **設計**: 全ドキュメントを 1 つのトポロジーグラフとして扱い、その上でリンク・参照・分量を検証

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
```

終了コード:
- `0`: error 無し（warning のみは許容）
- `1`: error あり

## ディレクトリ構成

```
scripts/
├── check.py                       # CLI エントリ
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

## ファイルスコープ別ルール

`docs/architecture.md` で定めた分類体系・記述規約は、ファイルの役割によって適用範囲が異なる。
スコープは `doc_check/config.py` で判定する。

| スコープ | 例 | 適用ルール |
|---|---|---|
| core | `world/core/axioms.md`, `theorems.md`, `open-questions.md` | links, references, ids, sections, forbidden, paths, volume, todos |
| applied | `world/magic.md`, `world/dungeons.md` 等 | links, references, sections, forbidden, paths, volume, todos |
| glossary | `glossary.md` | links, forbidden, paths |
| meta | `docs/architecture.md`, `docs/redesign-plan.md`, `docs/design-notes.md` | **適用外**（禁止語・旧パス・コードのみ参照の NG 例を意図的に含むため） |
| other | `README.md` 等 | links |

## チェック一覧

### 形式

- **links.missing-file** (error): 参照先ファイルが存在しない
- **links.missing-anchor** (error): 参照先ファイルに該当アンカー（見出し）が無い
- **links.id-mismatch** (error): リンクテキストの ID コードと参照先見出しの ID コードが不一致。`### [E1] 現界` のような ID 付き見出しへのリンクのみ照合し、ID 無し見出し（重要な帰結節など）への参照はスキップ
- **references.bare-code** (error): 散文中の「T1 により」「E4 が」のようなコードのみ参照
- **references.bare-bracket** (error): `[T1]` のようなセクション名を含まない括弧付き参照
  - 範囲表現「T1〜T6」「E1-E6」、列挙「E7, I5, T10, Q7」は例外として許容

### 構造

- **sections.missing** (error): 必須セクション欠落
  - 公理 E/I: 命題・関連
  - 定理 T: 命題・導出元・関連
  - 未解明 Q: 背景・現在判明していること・空白の意図・関連
- **sections.missing-premise** (error): 応用ファイル冒頭に `*前提:` リスト無し
- **ids.duplicate** (error): 同一ファイル内で E/I/T/Q ID が重複
- **glossary.missing** (error): core で定義された ID が `glossary.md` に未登録

### 内容

- **forbidden.term** (error): 廃止用語「補題」が本文に出現
- **forbidden.code** (error): 廃止接頭辞 `L#` / `C#` が本文に出現
  - 「体系」「系統」等の複合語との区別が難しいため、「系」単体は対象外
  - ダンジョン分類の「C-1, C-2」もハイフン区別で除外
- **paths.old-path** (error): 旧パス（`世界の法則.md`, `魔法.md`, `character/`, `history/` 等）への参照

### 長さ・分量上限（暴走防止）

閾値は [`doc_check/thresholds.json`](doc_check/thresholds.json)。原則 error。

- **volume.proposition** (error): 命題セクション本文が `proposition_max_sentences` 文を超える
- **volume.heading-depth** (error): 見出しが `heading_max_depth` より深い
- **volume.list-items** (error): 連続するリスト項目が `list_max_items` を超える
- **volume.file-length** (error): 応用ファイルが `applied_file_max_lines` を超える
- **volume.entry-length** (error): 1 命題エントリが `entry_max_chars` を超える
  - **Markdown リンクの URL とリンクテキスト全体は文字数カウントから除外**（リンク先見出し名が長くても誤検出しない）
- 段落の文数 / 詳細セクション行数: 上記項目で実質カバー（必要に応じて追加実装）

### その他

- **todos.scattered** (warning): TODO / FIXME / `- [ ]` がファイル末尾の `## ToDo` 節以外に出現

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
- **GitHub Actions**: `.github/workflows/check.yml`。doc-check は移行完了まで `continue-on-error: true` で informational

## チェッカー自体の開発

TDD で進める。

```sh
make test   # 常にグリーンであるべき
```

新しいチェックを追加する場合: テストを先に書く → `doc_check/checks/foo.py` を実装 → `runner.py` に配線 → `RULES_BY_SCOPE` を更新。
