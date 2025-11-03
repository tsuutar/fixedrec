#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
固定長レコード構造体定義のパーサー
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# 構造体内の BYTE 宣言:  BYTE Name[len];
BYTE_DECL_RE = re.compile(
    r"""\bBYTE\s+([A-Za-z_]\w*)\s*\[\s*(\d+)\s*\]\s*;""",
    re.ASCII
)

# 複数struct抽出: struct <Name?> { ... } <ext list>?;
#   - Name は必須とする（無名は1定義のみの時だけ許容）
#   - 後続の拡張子列は省略可（その場合は自動選択不可。--struct が必要）
STRUCT_BLOCK_RE = re.compile(
    r"""
    struct
    \s+([A-Za-z_]\w*)                      # 1: name
    \s*\{(.*?)\}                           # 2: body (non-greedy)
    \s*([^;{}]*)?;?                        # 3: trailing ext list (optional, up to ';')
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE
)


@dataclass
class StructDef:
    """構造体定義"""
    name: str
    fields: List[Tuple[str, int]]
    exts: List[str]  # lowercased, without leading dot


def strip_block_and_line_comments(text: str) -> str:
    """/* ... */ を先に除去し、その後で // 行末コメントを除去。"""
    # ブロックコメント
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # 行末 // コメント
    lines = []
    for raw in text.splitlines():
        s = raw.split("//", 1)[0]
        lines.append(s)
    return "\n".join(lines)


def parse_ext_list(exts_raw: Optional[str]) -> List[str]:
    """カンマ区切りの拡張子列を正規化して返す（小文字、先頭ドットは除去）。"""
    if not exts_raw:
        return []
    norm = []
    for tok in exts_raw.split(","):
        t = tok.strip()
        if not t:
            continue
        if t.startswith("."):
            t = t[1:]
        t = t.lower()
        # スペース混入や末尾セミコロンを取り除く
        t = t.strip(" ;\t\r\n")
        if t:
            norm.append(t)
    return norm


def parse_structs_config(text: str) -> List[StructDef]:
    """
    設定ファイル文字列から複数structを抽出し、StructDefの配列として返す。
    - /* ... */ と // コメントに対応
    - struct Name { ... } ext1, ext2; という拡張子マッピングを取り込む
    - BYTE Name[len]; のみをフィールドとして解析
    """
    cleaned = strip_block_and_line_comments(text)
    structs: List[StructDef] = []

    for m in STRUCT_BLOCK_RE.finditer(cleaned):
        name = m.group(1)
        body = m.group(2) or ""
        ext_raw = m.group(3) or ""

        fields: List[Tuple[str, int]] = []
        for mm in BYTE_DECL_RE.finditer(body):
            fname = mm.group(1)
            flen = int(mm.group(2))
            if flen <= 0:
                raise ValueError(f"フィールド長が不正です: {name}.{fname} = {flen}")
            fields.append((fname, flen))

        if not fields:
            raise ValueError(f"struct '{name}' に BYTE フィールドが見つかりません。")

        exts = parse_ext_list(ext_raw)
        structs.append(StructDef(name=name, fields=fields, exts=exts))

    if not structs:
        # 無名structの簡易対応（後方互換：単一定義のみ許可）
        # 例: struct { BYTE A[1]; } txt;
        # → 非推奨。必要ならここを強化可。
        anon = re.search(
            r"struct\s*\{(.*?)\}\s*([^;{}]*)?;?", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if anon:
            body = anon.group(1) or ""
            ext_raw = anon.group(2) or ""
            fields = []
            for mm in BYTE_DECL_RE.finditer(body):
                fname = mm.group(1)
                flen = int(mm.group(2))
                if flen <= 0:
                    raise ValueError(
                        f"フィールド長が不正です: <anonymous>.{fname} = {flen}")
                fields.append((fname, flen))
            if not fields:
                raise ValueError("無名structに BYTE フィールドが見つかりません。")
            exts = parse_ext_list(ext_raw)
            structs.append(StructDef(name="_anonymous_",
                           fields=fields, exts=exts))
        else:
            raise ValueError("struct 定義が見つかりません。")

    return structs
