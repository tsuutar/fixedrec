"""
fixedrec - 固定長レコード変換ツール
"""

from .parser import StructDef, parse_structs_config, strip_block_and_line_comments, parse_ext_list
from .cli import main, parse_bytes_from_arg, parse_term, escape_bytes

__version__ = "1.0.0"
__all__ = [
    "StructDef",
    "parse_structs_config",
    "strip_block_and_line_comments",
    "parse_ext_list",
    "main",
    "parse_bytes_from_arg",
    "parse_term",
    "escape_bytes",
]
