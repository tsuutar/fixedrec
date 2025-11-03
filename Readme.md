# fixedrec - 固定長バイナリレコードをフィールドごとに分割して区切りテキスト形式で出力するツール

固定長バイナリレコードをフィールドごとに分割して区切りテキスト形式で出力するツール。
**C 言語風の struct 設定ファイル**でレイアウトを定義し、**フィールドはバイナリのまま**出力（区切りや行末だけを整形）します。
(バイナリではなく 16 進数出力も可能)

## ✨ 特徴

- **バイト列を一切変換せず**、そのまま出力（デコードしない）
- 入力終端は **CRLF / LF / CR / なし / 任意バイト列** を指定可能（`--in-term`）
- 出力行末は **CRLF / LF / CR / なし / 任意バイト列** を指定可能（`--out-term`）
- フィールド区切りは **任意**（デフォルト TAB、`--sep` で変更）
- **複数 struct** の定義／**拡張子マッピング**／`/* ... */` **ブロックコメント**対応
- 可視化用の **エスケープ**（`--escape hex --prefix %` など）に対応
- 巨大ファイル OK（**ストリーム処理**）

---

## 📖 目次

- [要件](#要件)
- [インストール](#インストール)
- [使い方（クイック）](#使い方クイック)
- [設定ファイルの書き方](#設定ファイルの書き方)
- [主なオプション](#主なオプション)
- [使用例](#使用例)
- [動作仕様](#動作仕様)
- [トラブルシュート](#トラブルシュート)
- [テスト](#テスト)
- [開発](#開発)

---

## 要件

- Python **3.10+** (型ヒント `str | None` を使用)

---

## インストール

### 方法 1: リポジトリをクローンして使用

```bash
# 1. リポジトリをクローン
git clone https://github.com/tsuutar/fixedrec.git
cd fixedrec

# 2. Python仮想環境を作成
python -m venv .venv

# 3. 仮想環境を有効化
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
# Windows (cmd)
.venv\Scripts\activate.bat
# Linux/macOS
source .venv/bin/activate

# 4. 開発モードでインストール
pip install -e .

# 5. 実行確認
python -m fixedrec --help
# または
fixedrec --help
```

### 方法 2: 直接インストール

```bash
git clone https://github.com/tsuutar/fixedrec.git
cd fixedrec
pip install .
```

---

## 使い方（クイック）

```bash
# パッケージとしてインストール後
# BMPファイルのヘッダ出力(16進数の場合)
fixedrec -i input.bmp -o out.tsv -c layout.struct --struct BMP_HEADER --in-term none --sep "\t" --escape hex --max-rows 1 --header-structs

# BMPファイルのヘッダ出力(生バイトの場合)
fixedrec -i input.bmp -o out2.tsv -c layout.struct --struct BMP_HEADER --in-term none --sep "\t" --max-rows 1

# または python -m で実行
# BMPファイルのヘッダ出力
python -m fixedrec -i input.bmp -o out.tsv -c layout.struct --struct BMP_HEADER --in-term none --sep "\t" --escape hex --max-rows 1 --header-structs
```

- デフォルト: 入力終端=CRLF、出力行末=CRLF、区切り=TAB
- フィールドは**生バイト**で出力（文字エンコード変換なし）

---

## 設定ファイルの書き方

`layout.struct`（UTF-8 推奨。`//` と `/* ... */` コメント可）

```c
/* 例: 2種類の構造体。閉じカッコ後に拡張子を列挙してマッピング */
struct FIX47 {
  BYTE Title[10];
  BYTE COL_A[15];
  BYTE COL_B[20];
} txt, dat, csv;   // .txt / .dat / .csv に適用（ドット有無どちらでもOK）

struct FIX32 {
  BYTE Foo[8];
  BYTE Bar[8];
  BYTE Baz[16];
} bin;             // .bin に適用
```

- **構造体名**は必須（複数定義する場合、無名は不可推奨）
- フィールドは `BYTE Name[Len];` のみ（Len は > 0）
- `} txt, dat;` のように拡張子をカンマ区切りで列挙（小文字で照合）

---

## 主なオプション

```text
-i,  --input PATH        入力バイナリ（固定長 + 入力終端 の繰返し）
-o,  --output PATH       出力テキスト（バイナリ書込）
-c,  --config PATH       struct定義ファイル（UTF-8/UTF-8(BOM)/CP932 対応）
     --struct NAME       使用するstruct名（未指定時は拡張子で自動選択）

     --in-term  VAL      入力終端: crlf|lf|cr|none|hex:0a|"\\x1e\\x1f" など（既定: crlf）
     --out-term VAL      出力行末: 同上（既定: crlf）
     --sep      VAL      フィールド区切り: "," / "\\t" / " | " / hex:1f 等（既定: "\\t"）

     --escape none|hex   可視化エスケープ（既定: none=生バイト）
     --prefix STR        --escape hex時の接頭辞（既定: "\\x", 例: "%", "\\u", "$"）

     --max-rows N        先頭Nレコードのみ処理（0=全件）
     --lenient           入力終端の不一致/欠落時も警告して継続（既定は厳格エラー）
     --dump-layout       レイアウトと推定レコード数を表示して終了
  --header-structs    設定ファイルに定義された struct 名を出力ファイル先頭にヘッダ行として出力
     --summary           サマリのみ表示
```

**メモ**

- `hex:...` は偶数桁の 16 進（例: `hex:0d0a`）
- `"\t"`, `"\\x1f"` のような **バックスラッシュエスケープ**も使用可

---

## 使用例

### 1) 基本（CRLF 終端 →TSV）

```bash
fixedrec -i data.dat -o out.tsv -c layout.struct
```

### 2) 入力が LF 終端、出力も LF に

```bash
fixedrec -i data.lf -o out_lf.tsv -c layout.struct \
  --in-term lf --out-term lf
```

### 3) 入力が「終端なし（生固定長）」、出力は CRLF

```bash
fixedrec -i data.raw -o out.tsv -c layout.struct \
  --in-term none --out-term crlf
```

### 4) 区切りを US(0x1F)、非 ASCII を `%NN` で可視化

```bash
fixedrec -i data.bin -o out.txt -c layout.struct \
  --sep hex:1f --escape hex --prefix %
```

### 5) 複数 struct がある設定で、**拡張子から自動選択**

```bash
fixedrec -i sample.txt -o out.tsv -c layout.struct
# -> .txt にマッピングされた struct を自動選択
```

### 6) 明示的に struct 指定

```bash
fixedrec -i some.bin -o out.tsv -c layout.struct --struct FIX47
```

### 7) レイアウト確認（レコード長/推定件数）

```bash
fixedrec -i data.dat -c layout.struct --dump-layout
```

---

## 動作仕様

- **入力**
  1 レコード = **合計バイト長**（`BYTE` フィールドの総和） + **入力終端**（`--in-term`）
  ※ファイルサイズがレコード長の倍数でない場合は警告します。

- **出力**
  各フィールドは **バイナリのまま**出力（文字コードに一切触れません）。
  フィールドは `--sep` で結合し、行末に `--out-term` を付与します。

- **エスケープ**
- **エスケープ**
  `--escape hex` のとき、**すべてのバイト**を `--prefix` と 2 桁の 16 進で表記します（例：`%41%42%0a`、`\x41\x42\x0a`）。

- **メモリ/性能**
  レコード単位の**ストリーム処理**です。数 GB 級でも動作（I/O 帯域依存）。

- **終了コード**

  - `0` 正常終了
  - `1` 入力が空など軽度エラー
  - `2` 設定/引数/整合性エラー、I/O 例外 など

---

## トラブルシュート

- **「構造体が見つからない」**

  - `--struct` を指定するか、設定の `} txt, dat;` など拡張子マッピングを確認。

- **「hex 指定エラー」**

  - `hex:` の後は **偶数桁**の 16 進のみ。例：`hex:1f`（OK）、`hex:1`（NG）

- **「出力が文字化けに見える」**

  - 本ツールは**変換しません**。可視化したい場合は `--escape hex` を使うか、
    後段で適切なエンコード（UTF-8 等）として解釈できるツールで確認してください。

- **「末尾不完全/終端不一致」**

  - 既定はエラー停止。継続したい場合は `--lenient` を付けると警告して出力を続けます
    （出力行末は常に `--out-term` で正規化）。

---

## 🧪 テスト

### テスト実行

```bash
# 全テストを実行
python tests/test_cli_basic.py

# または unittestフレームワークで実行
python -m unittest tests.test_cli_basic
```

### テストの内容

- `TestStripComments`: コメント削除機能
- `TestParseExtList`: 拡張子リストのパース
- `TestParseStructsConfig`: struct 定義ファイルのパース
- `TestParseBytesFromArg`: バイト列引数のパース
- `TestParseTerm`: 終端文字列のパース
- `TestEscapeBytes`: バイトエスケープ機能
- `TestChooseStruct`: struct 自動選択機能
- `TestIntegration`: 統合テスト（実ファイルでの動作確認）

### ダミー入力の生成例

```python
with open("dummy.dat", "wb") as f:
    for i in range(3):
        f.write(b"TITLE_____")              # 10B
        f.write(b"A______________")         # 15B
        f.write(b"B____________________")   # 20B
        f.write(b"\r\n")                    # CRLF
```

### 設定確認

```bash
fixedrec -i dummy.dat -c layout.struct --dump-layout
```

### 差分チェック

```bash
fixedrec -i dummy.dat -o out.tsv -c layout.struct
hexdump -C out.tsv
```

---

## 🔧 開発

### ビルドとパッケージング

```bash
# ビルド用ツールをインストール
pip install build

# パッケージをビルド
python -m build

# dist/ ディレクトリに .whl と .tar.gz が生成されます
```

---

## 🪟 Windows 用 exe を作る（PyInstaller）

以下は Windows (PowerShell) 環境で単一実行ファイル（one-file exe）を作る手順の例です。

注意点:

- PyInstaller は実行環境に依存するため、Windows 用 exe は Windows 上でビルドしてください。
- ウイルス対策ソフトが単一ファイル化した exe を誤検出することがあります。リリース時は署名や検証手順を検討してください。

手順の概要:

1. 必要パッケージを追加インストール

```powershell
pip install pyinstaller
```

4. PyInstaller でビルド

```powershell
# ワンファイル（単一 exe）
pyinstaller --noconfirm --noupx --clean --onefile --name fixedrec entry.py
```

5. 出力物の確認

`dist\fixedrec.exe` が生成されます。簡単に動作確認:

```powershell
.\dist\fixedrec.exe --help
```

ヒント

- 外部ファイルは実行ファイルと同じフォルダに配置するか、フルパスを指定してください。
