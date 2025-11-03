#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
固定長レコード(任意のレコード区切り) → 区切りテキスト 変換ツール
（struct設定ファイル駆動・ブロックコメント対応・複数struct/拡張子マッピング対応）

◆ 入力前提
  - 1レコード = [BYTEフィールドの合計長] + 入力レコード終端(--in-term)
  - struct書式:
      struct Name {
        BYTE Field1[len];
        BYTE Field2[len];
        ...
      } ext1, ext2, ...;
    * // と /* ... */ コメント可。拡張子は .txt / txt いずれでも可。空白可。
    * 無名structは非推奨（複数定義がある場合はエラー）。

◆ 出力
  - 各フィールドは「バイト列のまま」出力（デコードしない）
  - フィールド区切り: --sep（既定= \\t）
  - 行末: --out-term（既定= crlf）
  - 可視化: --escape hex（非可視や '\\' を prefix+2桁HEX で表記）

◆ 例
  python -m fixedrec.cli -i input.bin -o out.tsv -c layout.struct
  python -m fixedrec.cli -i input.bin -o out.tsv -c layout.struct --in-term lf
  python -m fixedrec.cli -i input.bin -o out.tsv -c layout.struct --struct FIX47
  python -m fixedrec.cli -i input.bin -o out.csv -c layout.struct --sep "," --escape hex --prefix %
"""

import argparse
import codecs
import os
import sys
from typing import Sequence

from .parser import StructDef, parse_structs_config

# 便利な定数
CRLF = b"\r\n"
LF = b"\n"
CR = b"\r"


def parse_bytes_from_arg(arg: str) -> bytes:
    """
    任意の文字列をバイト列へ。
      - "hex:1f" のような16進列（偶数桁）→ bytes
      - バックスラッシュエスケープ "\\t", "\\x1f", "\\n" 等（Python互換）→ UTF-8 エンコード
      - 上記以外 → 与えられた文字列を UTF-8 エンコード
    """
    if arg.startswith("hex:"):
        hexpart = arg[4:].strip()
        if len(hexpart) == 0 or (len(hexpart) % 2) != 0:
            raise ValueError(f"hex 指定は偶数桁の16進で与えてください: {arg!r}")
        try:
            return bytes.fromhex(hexpart)
        except ValueError:
            raise ValueError(f"hex 指定を変換できません: {arg!r}")

    # バックスラッシュエスケープが含まれる場合のみ unicode_escape で処理
    if '\\' in arg:
        try:
            decoded = codecs.decode(arg, "unicode_escape")  # "\\t" → "\t" 等
            return decoded.encode("utf-8")
        except (UnicodeDecodeError, ValueError):
            # エスケープ処理に失敗した場合は通常のUTF-8エンコード
            pass

    return arg.encode("utf-8")


def parse_term(term: str) -> bytes:
    """区切り種別をプリセット or 任意バイト列へ。"""
    t = term.lower()
    if t == "crlf":
        return CRLF
    if t == "lf":
        return LF
    if t == "cr":
        return CR
    if t == "none":
        return b""
    return parse_bytes_from_arg(term)


def escape_bytes(bs: bytes, mode: str, prefix: str = "") -> bytes:
    """
    可視化用エスケープ。
      - mode="none": 元のバイト列をそのまま返す
      - mode="hex" : すべてのバイトを prefix+2桁HEX で表記
    """
    if mode == "none":
        return bs
    if mode != "hex":
        raise ValueError(f"未知の --escape モード: {mode!r}")
    # 変更: prefix が空文字の場合はスペース区切りの 2 桁 hex（例: "00 1f 2a"）を出力
    if prefix == "":
        out = " ".join(f"{b:02x}" for b in bs)
        return out.encode("ascii")

    # prefix が指定されている場合は従来通り連結して出力（例: "%00%1f" や "\\x00\\x1f"）
    out_chars = [f"{prefix}{b:02x}" for b in bs]
    return "".join(out_chars).encode("ascii")


def read_config_file(path: str) -> str:
    """設定ファイルを文字列として読む（utf-8-sig → utf-8 → cp932 の順にフォールバック）。"""
    for encoding in ["utf-8-sig", "utf-8", "cp932"]:
        try:
            with open(path, "r", encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            if encoding == "cp932":
                # 最後のエンコーディングでも失敗した場合は例外を再送出
                raise
            continue


def resolve_external_path(path: str) -> str:
    """外部ファイルの参照を解決するヘルパー。

    - 絶対パスならそのまま返す。
    - 相対パスの場合、PyInstaller でバンドルされた exe 実行時は exe の配置ディレクトリを優先して探索する。
    - 次にカレントディレクトリを探索する。
    - 見つからなければ元のパスを返す（呼び出し元でエラーを扱う）。
    """
    if os.path.isabs(path):
        return path

    # PyInstaller の frozen 実行時は exe のあるディレクトリを優先
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidate = os.path.join(exe_dir, path)
        if os.path.exists(candidate):
            return candidate

    # カレントワーキングディレクトリを確認
    cwd_candidate = os.path.join(os.getcwd(), path)
    if os.path.exists(cwd_candidate):
        return cwd_candidate

    # 見つからなければ元の相対パスを返す（そのまま open 等を行うと適切に例外が出る）
    return path


def choose_struct(structs: Sequence[StructDef], want_name: str | None, input_path: str) -> StructDef:
    """--struct 明示 or 入力拡張子で構造体を選択。一意に決まらなければエラー。"""
    if want_name:
        for s in structs:
            if s.name == want_name:
                return s
        names = ", ".join(sd.name for sd in structs)
        raise ValueError(f"--struct '{want_name}' が見つかりません。候補: {names}")

    # 自動選択：入力拡張子（小文字、ドット無し）
    base = os.path.basename(input_path)
    _, ext = os.path.splitext(base)
    ext = ext.lower().lstrip(".")
    if not ext:
        if len(structs) == 1:
            return structs[0]
        raise ValueError("入力ファイルに拡張子がありません。--struct で明示指定してください。")

    cand = [sd for sd in structs if ext in sd.exts]
    if len(cand) == 1:
        return cand[0]
    if len(cand) == 0:
        # 拡張子マッピングが無いstructが1つだけならそれを許容
        no_map = [sd for sd in structs if not sd.exts]
        if len(no_map) == 1:
            return no_map[0]
        names = ", ".join(sd.name for sd in structs)
        raise ValueError(f"拡張子 '.{ext}' に対応する struct が見つかりません。--struct で明示指定するか、"
                         f"定義に拡張子マッピングを追加してください。候補: {names}")
    # 複数マッチ
    names = ", ".join(sd.name for sd in cand)
    raise ValueError(
        f"拡張子 '.{ext}' に複数の struct がマッチしました: {names}。--struct で明示指定してください。")


def main():
    ap = argparse.ArgumentParser(
        description="固定長(任意終端)→区切りテキスト変換（struct複数/拡張子対応・ブロックコメント対応）")
    ap.add_argument("-i", "--input", required=True,
                    help="入力バイナリ（固定長 + 入力終端 の繰返し）")
    ap.add_argument("-o", "--output", required=True, help="出力テキスト（バイナリ書込）")
    ap.add_argument("-c", "--config", required=True,
                    help="struct定義ファイル（UTF-8/UTF-8(BOM)/CP932 対応）")
    ap.add_argument("--struct", dest="struct_name",
                    default=None, help="使用する struct 名（省略時は拡張子で自動選択）")

    # 入出力レコード終端
    ap.add_argument("--in-term", default="crlf",
                    help="入力レコード終端（crlf|lf|cr|none|hex:..|'\\n' 等, 既定=crlf）")
    ap.add_argument("--out-term", default="crlf",
                    help="出力行末（crlf|lf|cr|none|hex:..|'\\n' 等, 既定=crlf）")

    # フィールド可視化エスケープ
    ap.add_argument("--escape", choices=["none", "hex"], default="none",
                    help="フィールド可視化エスケープ（none=生バイト, hex=16進）")
    ap.add_argument("--prefix", default="",
                    help="--escape hex の接頭辞（例: %%, \\u, $ など。既定=無し → スペース区切りの2桁HEX出力）")

    # フィールド区切り
    ap.add_argument("--sep", default="\\t",
                    help="フィールド区切り。例: ',' / 'hex:1f' / '\\t' / ' | ' 等（既定=\\t）")

    ap.add_argument("--max-rows", type=int, default=0,
                    help="先頭Nレコードのみ処理（0=全件）")
    ap.add_argument("--lenient", action="store_true",
                    help="入力終端の不一致/欠落時も警告して継続（既定は厳密チェックで即エラー）")
    ap.add_argument("--dump-layout", action="store_true", help="レイアウトを表示して終了")
    ap.add_argument("--summary", action="store_true", help="処理サマリのみ簡潔に表示")
    ap.add_argument("--header-structs", action="store_true",
                    help="出力ファイル先頭に設定ファイルに定義された struct 名をヘッダ行として出力します（UTF-8、--sep で結合）")
    args = ap.parse_args()

    # 設定ファイル / 入出力パスを解決（exe 配布時は exe の配置先を優先）
    args.config = resolve_external_path(args.config)
    args.input = resolve_external_path(args.input)
    args.output = resolve_external_path(args.output)

    # 設定ファイル読込・解析（複数struct対応）
    try:
        cfg_text = read_config_file(args.config)
        structs = parse_structs_config(cfg_text)
    except Exception as e:
        print(f"[ERR] 設定ファイルエラー: {e}", file=sys.stderr)
        sys.exit(2)

    # 使用するstructを決定
    try:
        sd = choose_struct(structs, args.struct_name, args.input)
    except Exception as e:
        print(f"[ERR] 構造体選択エラー: {e}", file=sys.stderr)
        # 利便のため候補一覧を表示
        print("# 定義一覧:", file=sys.stderr)
        for x in structs:
            ex = (", ".join("." + e for e in x.exts)
                  ) if x.exts else "(拡張子マッピングなし)"
            print(
                f"  - {x.name}: fields={len(x.fields)}, exts={ex}", file=sys.stderr)
        sys.exit(2)

    total_field_len = sum(length for _, length in sd.fields)
    if total_field_len <= 0:
        print("[ERR] フィールド長合計が0です。定義を確認してください。", file=sys.stderr)
        sys.exit(2)

    # 入出力の終端と区切りを解釈
    try:
        in_term_bytes = parse_term(args.in_term)
        out_term_bytes = parse_term(args.out_term)
        sep_bytes = parse_bytes_from_arg(args.sep)
    except Exception as e:
        print(f"[ERR] 引数の解釈に失敗: {e}", file=sys.stderr)
        sys.exit(2)

    if len(sep_bytes) == 0:
        print("[ERR] --sep が空です。1バイト以上にしてください。", file=sys.stderr)
        sys.exit(2)

    in_term_len = len(in_term_bytes)
    rec_len = total_field_len + in_term_len

    # 入力サイズの事前整合チェック
    try:
        total_size = os.path.getsize(args.input)
    except OSError as e:
        print(f"[ERR] 入力ファイルにアクセスできません: {args.input} ({e})", file=sys.stderr)
        sys.exit(2)

    if total_size == 0:
        print("[ERR] 入力ファイルが空です。", file=sys.stderr)
        sys.exit(1)
    if rec_len > 0 and (total_size % rec_len != 0):
        print(f"[WARN] 入力サイズ {total_size} バイトは 1レコード長 {rec_len} の倍数ではありません。"
              f" 末尾不完全や終端不一致の可能性があります。", file=sys.stderr)

    if args.dump_layout:
        print("# Layout")
        print(f"- Using struct             : {sd.name}")
        for name, ln in sd.fields:
            print(f"  * {name}: {ln} bytes")
        print(
            f"- Input record terminator  : {in_term_bytes!r} (len={in_term_len})")
        print(
            f"- Output line terminator   : {out_term_bytes!r} (len={len(out_term_bytes)})")
        print(f"- Field separator          : {sep_bytes!r}")
        print(
            f"=> 1 record (input)        : {total_field_len} + {in_term_len} = {rec_len} bytes")
        approx = (total_size // rec_len) if rec_len > 0 else "N/A (in-term=none)"
        print(f"=> Approx. records in input: {approx}")
        return

    rows_limit = args.max_rows if args.max_rows > 0 else None
    processed = 0
    warnings = 0

    # 変換本体
    try:
        with open(args.input, "rb") as rf, open(args.output, "wb") as wf:
            # ヘッダ行の出力（オプション）: 設定ファイルに定義された struct 名を sep で結合
            if args.header_structs:
                struct_names = [s.name for s in structs]
                # struct 名は UTF-8 で出力（出力はバイナリ書込なので bytes にする）
                header_bytes = sep_bytes.join(name.encode(
                    "utf-8") for name in struct_names) + out_term_bytes
                wf.write(header_bytes)
            row_no = 0
            while True:
                # フィールド部を固定長で読む
                block = rf.read(total_field_len)
                if not block:
                    break
                if len(block) < total_field_len:
                    print(
                        f"[WARN] 末尾不完全: 残り {len(block)} バイト（期待 {total_field_len}）を破棄します。", file=sys.stderr)
                    warnings += 1
                    break

                # 入力終端の検証（長さ0ならスキップ）
                if in_term_len > 0:
                    tail = rf.read(in_term_len)
                    if len(tail) < in_term_len:
                        msg = f"[ERR] 末尾不完全: 入力終端が読めません（行 {row_no+1} 期待 {in_term_len}B）"
                        if args.lenient:
                            print(msg, file=sys.stderr)
                            warnings += 1
                            tail = in_term_bytes  # ダミー扱い
                        else:
                            print(msg, file=sys.stderr)
                            sys.exit(2)

                    if tail != in_term_bytes:
                        msg = (f"[ERR] 入力終端不一致（行 {row_no+1} ）: "
                               f"got={tail!r} expected={in_term_bytes!r}")
                        if args.lenient:
                            print(msg, file=sys.stderr)
                            warnings += 1
                            # 続行（出力は指定の out-term で正規化）
                        else:
                            print(msg, file=sys.stderr)
                            sys.exit(2)

                row_no += 1

                # フィールドを切出し → 必要ならエスケープ → 任意区切りで連結 → 出力行末(out-term)
                pos = 0
                out_fields = []
                for name, ln in sd.fields:
                    seg = block[pos:pos+ln]
                    pos += ln
                    out_fields.append(escape_bytes(
                        seg, args.escape, args.prefix))

                wf.write(sep_bytes.join(out_fields) + out_term_bytes)

                processed += 1
                if rows_limit is not None and processed >= rows_limit:
                    break
    except Exception as e:
        print(f"[ERROR] 変換中に例外が発生しました: {e}", file=sys.stderr)
        sys.exit(2)

    if args.summary:
        print(f"records_out={processed}, warnings={warnings}, "
              f"record_size_in={rec_len}B (fields={total_field_len}B + in-term {in_term_len}B), "
              f"in-term={in_term_bytes!r}, out-term={out_term_bytes!r}, sep={sep_bytes!r}, struct={sd.name}")
    else:
        print(f"完了: {processed} 行 → {args.output} (struct={sd.name})")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
