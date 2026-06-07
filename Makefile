PY ?= python3

.PHONY: check test topology help

help:
	@echo "make test      - ユニットテスト（チェッカー自体の検証。常にグリーンであるべき）"
	@echo "make check     - ドキュメント整合性チェック（移行完了までは既存債務で赤になる）"
	@echo "make topology  - 参照トポロジーを build/ に出力（JSON + DOT）"

test:
	$(PY) -m unittest discover -s scripts -t scripts -p 'test_*.py'

check:
	$(PY) scripts/check.py

topology:
	$(PY) scripts/check.py --emit-topology build/topology.json --dot build/topology.dot
