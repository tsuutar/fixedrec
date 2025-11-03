#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fixedrec CLI の基本テスト
"""

from fixedrec.parser import (
    strip_block_and_line_comments,
    parse_ext_list,
    parse_structs_config,
    StructDef,
)
from fixedrec.cli import (
    parse_bytes_from_arg,
    parse_term,
    escape_bytes,
    choose_struct,
)
import sys
import unittest
import tempfile
import os
from pathlib import Path

# プロジェクトルートの src を追加（これを先に行うことでローカルの src を優先して import できる）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


# テスト対象モジュールのインポート


class TestStripComments(unittest.TestCase):
    """コメント除去のテスト"""

    def test_line_comment(self):
        """行末コメントの除去"""
        text = "struct Foo { // comment\n  BYTE A[1]; // another\n}"
        result = strip_block_and_line_comments(text)
        self.assertNotIn("//", result)
        self.assertIn("struct Foo {", result)
        self.assertIn("BYTE A[1];", result)

    def test_block_comment(self):
        """ブロックコメントの除去"""
        text = "struct Foo { /* block comment */ BYTE A[1]; }"
        result = strip_block_and_line_comments(text)
        self.assertNotIn("/*", result)
        self.assertNotIn("*/", result)
        self.assertIn("struct Foo {", result)
        self.assertIn("BYTE A[1];", result)

    def test_multiline_block_comment(self):
        """複数行ブロックコメントの除去"""
        text = """struct Foo {
            /* multi
               line
               comment */
            BYTE A[1];
        }"""
        result = strip_block_and_line_comments(text)
        self.assertNotIn("multi", result)
        self.assertNotIn("line", result)
        self.assertIn("BYTE A[1];", result)

    def test_mixed_comments(self):
        """ブロックと行コメントの混在"""
        text = "struct Foo { /* block */ BYTE A[1]; // line\n}"
        result = strip_block_and_line_comments(text)
        self.assertNotIn("/*", result)
        self.assertNotIn("//", result)


class TestParseExtList(unittest.TestCase):
    """拡張子リスト解析のテスト"""

    def test_simple_ext(self):
        """単純な拡張子"""
        result = parse_ext_list("txt")
        self.assertEqual(result, ["txt"])

    def test_multiple_exts(self):
        """複数の拡張子"""
        result = parse_ext_list("txt, dat, bin")
        self.assertEqual(result, ["txt", "dat", "bin"])

    def test_with_dots(self):
        """ドット付き拡張子"""
        result = parse_ext_list(".txt, .dat")
        self.assertEqual(result, ["txt", "dat"])

    def test_mixed_format(self):
        """混在フォーマット"""
        result = parse_ext_list("txt, .dat, BIN")
        self.assertEqual(result, ["txt", "dat", "bin"])

    def test_empty_string(self):
        """空文字列"""
        result = parse_ext_list("")
        self.assertEqual(result, [])

    def test_none(self):
        """None"""
        result = parse_ext_list(None)
        self.assertEqual(result, [])

    def test_trailing_semicolon(self):
        """末尾セミコロン"""
        result = parse_ext_list("txt;")
        self.assertEqual(result, ["txt"])


class TestParseStructsConfig(unittest.TestCase):
    """struct定義解析のテスト"""

    def test_simple_struct(self):
        """単純なstruct定義"""
        text = """
        struct Simple {
            BYTE Field1[10];
            BYTE Field2[20];
        } txt;
        """
        result = parse_structs_config(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Simple")
        self.assertEqual(len(result[0].fields), 2)
        self.assertEqual(result[0].fields[0], ("Field1", 10))
        self.assertEqual(result[0].fields[1], ("Field2", 20))
        self.assertEqual(result[0].exts, ["txt"])

    def test_multiple_structs(self):
        """複数のstruct定義"""
        text = """
        struct First {
            BYTE A[5];
        } txt;
        
        struct Second {
            BYTE B[10];
        } dat, bin;
        """
        result = parse_structs_config(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "First")
        self.assertEqual(result[1].name, "Second")
        self.assertEqual(result[1].exts, ["dat", "bin"])

    def test_struct_with_comments(self):
        """コメント付きstruct定義"""
        text = """
        // Line comment
        struct Test {
            BYTE A[1]; // field comment
            /* block comment */
            BYTE B[2];
        } txt;
        """
        result = parse_structs_config(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0].fields), 2)

    def test_no_extension(self):
        """拡張子なしのstruct定義"""
        text = """
        struct NoExt {
            BYTE Field[5];
        };
        """
        result = parse_structs_config(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].exts, [])

    def test_invalid_field_length(self):
        """不正なフィールド長"""
        text = """
        struct Bad {
            BYTE Field[0];
        } txt;
        """
        with self.assertRaises(ValueError) as cm:
            parse_structs_config(text)
        self.assertIn("フィールド長が不正", str(cm.exception))

    def test_no_fields(self):
        """フィールドなしのstruct"""
        text = """
        struct Empty {
        } txt;
        """
        with self.assertRaises(ValueError) as cm:
            parse_structs_config(text)
        self.assertIn("BYTE フィールドが見つかりません", str(cm.exception))

    def test_anonymous_struct(self):
        """無名struct（後方互換）"""
        text = """
        struct {
            BYTE A[1];
        } txt;
        """
        result = parse_structs_config(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "_anonymous_")


class TestParseBytesFromArg(unittest.TestCase):
    """バイト列解析のテスト"""

    def test_hex_format(self):
        """hex:形式"""
        result = parse_bytes_from_arg("hex:1f2a")
        self.assertEqual(result, b"\x1f\x2a")

    def test_hex_invalid_length(self):
        """hex:形式（奇数桁）"""
        with self.assertRaises(ValueError):
            parse_bytes_from_arg("hex:1f2")

    def test_escape_sequences(self):
        """エスケープシーケンス"""
        result = parse_bytes_from_arg("\\t")
        self.assertEqual(result, b"\t")

        result = parse_bytes_from_arg("\\n")
        self.assertEqual(result, b"\n")

        result = parse_bytes_from_arg("\\x1f")
        self.assertEqual(result, b"\x1f")

    def test_plain_string(self):
        """通常の文字列"""
        result = parse_bytes_from_arg("test")
        self.assertEqual(result, b"test")

    def test_unicode_string(self):
        """Unicode文字列（バックスラッシュなしの場合は直接UTF-8エンコード）"""
        # 修正後: バックスラッシュが含まれない場合は直接UTF-8エンコード
        result = parse_bytes_from_arg("テスト")
        expected = "テスト".encode("utf-8")
        self.assertEqual(result, expected)


class TestParseTerm(unittest.TestCase):
    """終端記号解析のテスト"""

    def test_crlf(self):
        """CRLF"""
        result = parse_term("crlf")
        self.assertEqual(result, b"\r\n")

        result = parse_term("CRLF")
        self.assertEqual(result, b"\r\n")

    def test_lf(self):
        """LF"""
        result = parse_term("lf")
        self.assertEqual(result, b"\n")

    def test_cr(self):
        """CR"""
        result = parse_term("cr")
        self.assertEqual(result, b"\r")

    def test_none(self):
        """none"""
        result = parse_term("none")
        self.assertEqual(result, b"")

    def test_custom_bytes(self):
        """カスタムバイト列"""
        result = parse_term("hex:1f")
        self.assertEqual(result, b"\x1f")


class TestEscapeBytes(unittest.TestCase):
    """バイトエスケープのテスト"""

    def test_none_mode(self):
        """エスケープなし"""
        data = b"\x00\x1f\x20\x7e\x7f"
        result = escape_bytes(data, "none")
        self.assertEqual(result, data)

    def test_hex_mode_printable(self):
        """hex モード（可視文字）"""
        data = b"ABC"
        result = escape_bytes(data, "hex")
        self.assertEqual(result, b"41 42 43")

    def test_hex_mode_non_printable(self):
        """hex モード（非可視文字）"""
        data = b"\x00\x1f"
        result = escape_bytes(data, "hex")
        self.assertEqual(result, b"00 1f")

    def test_hex_mode_backslash(self):
        """hex モード（バックスラッシュ）"""
        data = b"\\"
        result = escape_bytes(data, "hex")
        self.assertEqual(result, b"5c")

    def test_hex_mode_custom_prefix(self):
        """hex モード（カスタム接頭辞）"""
        data = b"\x00\x1f"
        result = escape_bytes(data, "hex", prefix="%")
        self.assertEqual(result, b"%00%1f")

    def test_invalid_mode(self):
        """不正なモード"""
        with self.assertRaises(ValueError):
            escape_bytes(b"test", "invalid")


class TestChooseStruct(unittest.TestCase):
    """struct選択のテスト"""

    def setUp(self):
        """テスト用のstruct定義を準備"""
        self.structs = [
            StructDef(name="Txt", fields=[("A", 1)], exts=["txt"]),
            StructDef(name="Dat", fields=[("B", 2)], exts=["dat", "bin"]),
            StructDef(name="NoExt", fields=[("C", 3)], exts=[]),
        ]

    def test_explicit_name(self):
        """明示的な名前指定"""
        result = choose_struct(self.structs, "Txt", "test.bin")
        self.assertEqual(result.name, "Txt")

    def test_explicit_name_not_found(self):
        """存在しない名前指定"""
        with self.assertRaises(ValueError) as cm:
            choose_struct(self.structs, "NotExists", "test.bin")
        self.assertIn("が見つかりません", str(cm.exception))

    def test_auto_select_by_extension(self):
        """拡張子による自動選択"""
        result = choose_struct(self.structs, None, "test.txt")
        self.assertEqual(result.name, "Txt")

        result = choose_struct(self.structs, None, "test.dat")
        self.assertEqual(result.name, "Dat")

    def test_auto_select_no_extension(self):
        """拡張子なし（単一struct時）"""
        single = [self.structs[0]]
        result = choose_struct(single, None, "test")
        self.assertEqual(result.name, "Txt")

    def test_auto_select_no_extension_multiple(self):
        """拡張子なし（複数struct時）"""
        with self.assertRaises(ValueError) as cm:
            choose_struct(self.structs, None, "test")
        self.assertIn("拡張子がありません", str(cm.exception))

    def test_auto_select_extension_not_found(self):
        """対応する拡張子なし（fallback to no-ext struct）"""
        result = choose_struct(self.structs, None, "test.xyz")
        self.assertEqual(result.name, "NoExt")

    def test_auto_select_extension_not_found_no_fallback(self):
        """対応する拡張子なし（fallbackもなし）"""
        structs = [self.structs[0], self.structs[1]]  # NoExtを除外
        with self.assertRaises(ValueError) as cm:
            choose_struct(structs, None, "test.xyz")
        self.assertIn("対応する struct が見つかりません", str(cm.exception))

    def test_case_insensitive_extension(self):
        """拡張子の大文字小文字を区別しない"""
        result = choose_struct(self.structs, None, "test.TXT")
        self.assertEqual(result.name, "Txt")


class TestIntegration(unittest.TestCase):
    """統合テスト（実際のファイル入出力）"""

    def setUp(self):
        """テンポラリディレクトリを準備"""
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: self._cleanup_temp_dir())

    def _cleanup_temp_dir(self):
        """テンポラリディレクトリのクリーンアップ"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_simple_conversion(self):
        """単純な変換テスト"""
        # 設定ファイル作成
        config_path = os.path.join(self.temp_dir, "layout.struct")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("""
            struct Test {
                BYTE Field1[5];
                BYTE Field2[3];
            } txt;
            """)

        # 入力ファイル作成（2レコード）
        input_path = os.path.join(self.temp_dir, "input.txt")
        with open(input_path, "wb") as f:
            f.write(b"AAAAA" + b"BBB" + b"\r\n")  # Record 1
            f.write(b"CCCCC" + b"DDD" + b"\r\n")  # Record 2

        # 出力ファイルパス
        output_path = os.path.join(self.temp_dir, "output.txt")

        # 変換実行
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "fixedrec",
             "-i", input_path,
             "-o", output_path,
             "-c", config_path],
            capture_output=True,
            text=True
        )

        # 結果確認
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

        # 出力ファイル確認
        with open(output_path, "rb") as f:
            output = f.read()

        # タブ区切りで2レコード出力されているはず
        lines = output.split(b"\r\n")
        self.assertEqual(len(lines), 3)  # 2レコード + 末尾空行
        self.assertEqual(lines[0], b"AAAAA\tBBB")
        self.assertEqual(lines[1], b"CCCCC\tDDD")

    def test_conversion_with_escape(self):
        """エスケープ付き変換テスト"""
        # 設定ファイル作成
        config_path = os.path.join(self.temp_dir, "layout.struct")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("""
            struct Test {
                BYTE Field1[3];
            } txt;
            """)

        # 入力ファイル作成（非可視文字を含む）
        input_path = os.path.join(self.temp_dir, "input.txt")
        with open(input_path, "wb") as f:
            f.write(b"\x00\x1f\x20" + b"\r\n")

        # 出力ファイルパス
        output_path = os.path.join(self.temp_dir, "output.txt")

        # 変換実行（hex エスケープ）
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "fixedrec",
             "-i", input_path,
             "-o", output_path,
             "-c", config_path,
             "--escape", "hex"],
            capture_output=True,
            text=True
        )

        # 結果確認
        self.assertEqual(result.returncode, 0)

        # 出力ファイル確認
        with open(output_path, "rb") as f:
            output = f.read()

        # エスケープされているはず（デフォルト prefix 無し → スペース区切りの2桁HEX）
        self.assertIn(b"00 1f", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
