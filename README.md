# 映画詳細情報自動補完ツール

## 概要

このツール群は、映画タイトルのみが記載されたCSVファイルを読み込み、複数の映画情報サイト（映画.com, Kinenote, Yahoo!映画, Filmarks など）から公開年、監督名、あらすじ等の詳細情報を自動で取得して補完、または事前に生成されたJSONファイルから情報を読み込んで補完し、新しいCSVファイルとして出力するPythonスクリプト群です。

各映画情報サイトに対応する個別のスクリプト (`fill_movie_details_<サイト名>.py`) を実行することで、そのサイトから情報を取得します。

## 主な機能

*   **サイト別処理:**
    *   `fill_movie_details_eiga.py`: 映画.com から情報を取得
    *   `fill_movie_details_kinenote.py`: Kinenote から情報を取得
    *   `fill_movie_details_yahooeiga.py`: Yahoo!映画 から情報を取得
    *   `fill_movie_details_filmarks.py`: Filmarks から情報を取得 (実装中)
*   **CSV読み込み:** 指定された入力CSVファイルを読み込みます (Shift_JISエンコーディング)。
*   **2つの動作モード (各スクリプト共通):**
    *   **Web検索モード (デフォルト):**
        *   詳細情報（公開年、監督、あらすじ）が未入力の映画レコードを抽出します (`--limit` で件数指定可能)。
        *   各スクリプトに対応するWebサイトをスクレイピングして、詳細情報を取得します。
            *   取得項目はサイトにより異なります (仕様書 `specification.md` 参照)。
            *   スクレイピングには `requests` + `BeautifulSoup` を基本としますが、JavaScriptによる動的コンテンツが多いサイト (例: Kinenote) では `selenium` を使用する場合があります (**WebDriverの別途設定が必要**)。
        *   取得した全映画の詳細データをサイト名とタイムスタンプ付きのJSONファイル (`MovieData_<サイト名>_YYYYMMDDHHMMSS.json`) に保存します。
        *   取得した情報でCSVデータを更新します (元の値が空の場合のみ)。
    *   **JSON入力モード (`--json-input` 指定時):**
        *   指定されたJSONファイル (映画情報のリスト形式) を読み込みます。
        *   Webスクレイピングは行いません。
        *   JSONデータの内容に基づいてCSVデータを更新します (元の値が空の場合のみ)。
*   **CSV出力:** 更新されたデータを新しいCSVファイルとして保存します (Shift_JISエンコーディング、列順序指定あり)。
*   **デバッグ:** `--debug` オプションで、スクレイピング中のHTMLをファイル (`_debug_*.html`) に保存できます。

## 動作環境

*   Python 3.x
*   必要なライブラリ (詳細は `requirements.txt` を参照してください)
    *   pandas
    *   requests
    *   beautifulsoup4
    *   **selenium** (Kinenoteなど、一部サイトで必要)
*   **WebDriver** (Seleniumを使用する場合に必要。例: ChromeDriver, GeckoDriverなど)
    *   使用するブラウザ (Chrome, Firefoxなど) に合わせて別途インストールし、パスを通すかスクリプト内で指定する必要があります。

## インストール

1.  **Pythonライブラリ:**
    ```bash
    pip install -r requirements.txt
    ```
2.  **WebDriver (Seleniumを使う場合):**
    *   使用するブラウザ (例: Chrome) のバージョンに合ったWebDriverをダウンロードします。
        *   ChromeDriver: [https://chromedriver.chromium.org/downloads](https://chromedriver.chromium.org/downloads)
        *   GeckoDriver (Firefox): [https://github.com/mozilla/geckodriver/releases](https://github.com/mozilla/geckodriver/releases)
    *   ダウンロードしたWebDriverの実行ファイルを、システムのPATHが通ったディレクトリに置くか、スクリプト実行時にパスを指定できるように準備します。

## ファイル構造

*   **メインスクリプト:** `fill_movie_details_<サイト名>.py` (例: `fill_movie_details_kinenote.py`)
*   **スクレイパーモジュール:** `scrapers/<サイト名>_scraper.py` (例: `scrapers/kinenote_scraper.py`)
*   **仕様書:** `specification.md`
*   **依存関係:** `requirements.txt`
*   **入力/出力CSV:** (ユーザーが用意/指定)
*   **出力JSON:** `MovieData_<サイト名>_YYYYMMDDHHMMSS.json` (Web検索モード時に生成)
*   **デバッグHTML:** `_debug_*.html` (`--debug` オプション時に生成)

## 使い方

情報を取得したいサイトに対応するスクリプトを実行します。

```bash
python fill_movie_details_<サイト名>.py --input <入力CSVパス> --output <出力CSVパス> [オプション]
```

**主なオプション:**

*   `--input <パス>` (必須): 入力CSVファイルのパス (Shift_JIS)。
*   `--output <パス>` (必須): 出力CSVファイルのパス (Shift_JIS)。
*   `--limit <件数>` (オプション, Web検索モード時): 一度にWebから取得・処理する映画の最大件数。デフォルトは `5`。
*   `--json-input <パス>` (オプション): このオプションを指定すると、Web検索を行わず、指定されたJSONファイルからデータを読み込んでCSVを更新します。
*   `--debug` (オプション, Web検索モード時): スクレイピング対象のHTMLをデバッグ用にファイル保存します。

**実行例:**

*   **KinenoteからWeb検索 (最大10件、デバッグ有効):**
    ```bash
    python fill_movie_details_kinenote.py --input movies.csv --output movies_updated_kinenote.csv --limit 10 --debug
    ```
*   **Yahoo!映画からWeb検索 (デフォルト5件):**
    ```bash
    python fill_movie_details_yahooeiga.py --input movies.csv --output movies_updated_yahoo.csv
    ```
*   **以前Kinenoteから取得したJSONで補完:**
    ```bash
    python fill_movie_details_kinenote.py --input movies.csv --output movies_updated_from_json.csv --json-input MovieData_kinenote.com_20250424225857.json
    ```

## 注意事項

*   各Webサイトの利用規約を遵守してください。短時間に大量のリクエストを行うとアクセス制限を受ける可能性があります。
*   Webサイト側のHTML構造や仕様が変更されると、対応するスクレイピング処理が正常に動作しなくなる可能性があります。
*   Seleniumを使用する場合、WebDriverのセットアップが必要です。
*   Shift_JISエンコーディングでCSVを保存する際、表現できない文字は `?` に置換されます。
*   **生成されるCSVファイル、JSONファイル、HTMLファイル (デバッグ用含む) は、Gitなどのバージョン管理システムには登録せず、 `.gitignore` に追加することを強く推奨します。**

## TODO / 今後の拡張

(仕様書 `specification.md` を参照) 