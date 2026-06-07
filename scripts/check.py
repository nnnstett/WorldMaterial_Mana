#!/usr/bin/env python3
"""World Material "Mana" ドキュメント整合性チェッカー（CLI）。

使い方:
    python3 scripts/check.py [--root DIR] [PATH ...]
    python3 scripts/check.py --emit-topology build/topology.json --dot build/topology.dot

リンクのトポロジーは常に全ドキュメントから構築する。PATH を指定した場合、
結果の報告対象だけをそのファイルに絞る（解決はトポロジー全体で行う）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from doc_check.config import Config
from doc_check.runner import load_documents, run
from doc_check.report import summarize, exit_code

# トポロジー＆チェック対象に含めるドキュメント集合
_INCLUDE_DIRS = ("docs", "world")
_INCLUDE_FILES = ("README.md", "glossary.md")


def _all_files(repo_root: str):
    """リポジトリ内の全ファイル（.git 除く）をルート相対 posix パスで返す。"""
    out = set()
    for dirpath, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            full = os.path.join(dirpath, f)
            out.add(os.path.relpath(full, repo_root).replace("\\", "/"))
    return out


def discover(repo_root: str):
    rels = []
    for name in _INCLUDE_FILES:
        if os.path.isfile(os.path.join(repo_root, name)):
            rels.append(name)
    for d in _INCLUDE_DIRS:
        base = os.path.join(repo_root, d)
        for dirpath, _dirs, files in os.walk(base):
            for f in files:
                if f.endswith(".md"):
                    full = os.path.join(dirpath, f)
                    rels.append(os.path.relpath(full, repo_root).replace("\\", "/"))
    return sorted(set(rels))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ドキュメント整合性チェッカー")
    parser.add_argument("paths", nargs="*", help="報告対象を絞るファイル（省略時は全件）")
    parser.add_argument("--root", default=None, help="リポジトリルート（既定: scripts の親）")
    parser.add_argument("--emit-topology", metavar="JSON", help="トポロジーを JSON 出力")
    parser.add_argument("--dot", metavar="DOT", help="トポロジーを Graphviz DOT 出力")
    args = parser.parse_args(argv)

    repo_root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    rels = discover(repo_root)
    if not rels:
        print("対象ドキュメントが見つかりません。", file=sys.stderr)
        return 0

    documents = load_documents(repo_root, rels)
    existing = _all_files(repo_root)
    findings, topo = run(documents, Config(), existing_files=existing)

    if args.emit_topology:
        _write(args.emit_topology, json.dumps(topo.to_dict(), ensure_ascii=False, indent=2))
        print(f"topology JSON → {args.emit_topology}")
    if args.dot:
        _write(args.dot, topo.to_dot())
        print(f"topology DOT → {args.dot}")

    if args.paths:
        targets = {p.replace("\\", "/") for p in args.paths}
        findings = [f for f in findings if f.path in targets]

    for f in findings:
        print(f.format())
    print(summarize(findings))
    return exit_code(findings)


def _write(path: str, content: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


if __name__ == "__main__":
    raise SystemExit(main())
