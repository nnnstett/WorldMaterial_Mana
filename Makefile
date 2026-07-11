PY ?= python3

.PHONY: check test topology faq help

help:
	@echo "make test      - ユニットテスト（チェッカー自体の検証。常にグリーンであるべき）"
	@echo "make check     - ドキュメント整合性チェック（移行完了までは既存債務で赤になる）"
	@echo "make topology  - 参照トポロジーを build/ に出力（JSON + DOT）"
	@echo "make faq       - セマンティック検証ケースから FAQ.md を再生成（要コミット）"

test:
	$(PY) -m unittest discover -s scripts -t scripts -p 'test_*.py'

faq:
	$(PY) scripts/semantic_eval.py gen-faq --suite semantic-tests/public --out FAQ.md

check:
	$(PY) scripts/check.py

topology:
	$(PY) scripts/check.py --emit-topology build/topology.json --dot build/topology.dot
