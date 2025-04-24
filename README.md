# 映画詳細情報自動補完ツール

## 概要

このツールは、映画タイトルのみが記載されたCSVファイルを読み込み、映画.com から公開年、監督名、あらすじ等の詳細情報を自動で取得して補完、または事前に生成されたJSONファイルから情報を読み込んで補完し、新しいCSVファイルとして出力するPythonスクリプト (`fill_movie_details.py`) です。

## 主な機能

*   指定されたCSVファイルを読み込みます (Shift_JISエンコーディング)。
*   **2つの動作モード:**
    *   **Web検索モード (デフォルト):**
        *   詳細情報（公開年、監督、あらすじ）が未入力の映画レコードを抽出します (`--limit` で件数指定可能)。
        *   映画.com をスクレイピングして、以下の詳細情報を取得します:
            *   `year`, `director`, `summary`, `cast` (主要キャスト文字列), `producer`, `cinematographer`, `country`, `runtime`, `distributor`
            *   `full_staff`, `full_cast`, `reviews` (詳細なリスト/辞書構造)
        *   取得した全映画の詳細データをタイムスタンプ付きのJSONファイル (`MovieData_YYYYMMDDHHMMSS.json`) に保存します。
        *   取得した情報でCSVデータを更新します (元の値が空の場合のみ)。
        *   公開年が取得できない場合は `1800` を設定します。
    *   **JSON入力モード (`--json-input` 指定時):**
        *   指定されたJSONファイル (映画情報のリスト形式) を読み込みます。
        *   Webスクレイピングは行いません。
        *   JSONデータの内容に基づいてCSVデータを更新します (元の値が空の場合のみ)。
*   更新されたデータを新しいCSVファイルとして保存します (Shift_JISエンコーディング)。
    *   `full_staff`, `full_cast`, `reviews` はJSON形式の文字列として保存されます。
    *   Shift_JISで表現できない文字は `?` に置換されます。
*   出力CSVの列順序を指定された順序に整形します。

## 動作環境

*   Python 3.x
*   必要なライブラリ (詳細は `requirements.txt` を参照してください)
    *   pandas
    *   requests
    *   beautifulsoup4

## インストール

```bash
pip install -r requirements.txt
```

## ファイル構造

### 入力/出力 CSVファイル

*   **エンコーディング:** Shift_JIS
*   **列構成:**
    *   **必須列:**
        *   `movie_id` (文字列または数値): 各映画を一意に識別するID。
        *   `title` (文字列): 映画のタイトル (日本語)。
    *   **オプション/自動補完列 (以下の順序で出力):**
        *   `year` (整数): 公開年 (取得失敗時は1800)。
        *   `director` (文字列): 監督名。
        *   `summary` (文字列): あらすじ (最大300字程度)。
        *   `cast` (文字列): 主要キャスト (例: "俳優A (役名A), 俳優B (役名B), ...")。
        *   `producer` (文字列): プロデューサー。
        *   `cinematographer` (文字列): 撮影監督。
        *   `country` (文字列): 製作国。
        *   `runtime` (整数): 上映時間 (分)。
        *   `distributor` (文字列): 配給会社。
        *   `full_staff` (JSON文字列): スタッフ詳細情報 (後述のJSON構造参照)。
        *   `full_cast` (JSON文字列): キャスト詳細情報 (後述のJSON構造参照)。
        *   `reviews` (JSON文字列): レビュー情報 (後述のJSON構造参照)。

*   **注意:**
    *   入力CSVにオプション列が存在しない場合、スクリプト実行時に自動で追加され、空の値 (NaN) で初期化されます。
    *   出力CSVは、上記のオプション列の順序 (`movie_id`, `title` の後) で保存されます。
    *   `full_staff`, `full_cast`, `reviews` 列には、詳細な構造化データが **JSON形式の文字列** として格納されます。CSVエディタ等で直接見ると、`[{...}]` や `{...}` のような長い文字列に見えますが、プログラムで処理することで元の構造（リストや辞書）を復元できます。

### JSONファイル (Web検索出力 / JSON入力)

*   **エンコーディング:** UTF-8
*   **全体構造:** 映画情報を示す複数の **辞書 (dictionary)** を要素とする **リスト (list)** 形式。
    ```json
    [
      { "movie_id": "id1", "title": "映画A", "year": 2023, ... },
      { "movie_id": "id2", "title": "映画B", "year": 2024, ... },
      ...
    ]
    ```
*   **各映画情報の辞書構造 (リストの要素):**
    *   `movie_id` (文字列): 映画ID。
    *   `title` (文字列): タイトル。
    *   `year` (整数 or null): 公開年。
    *   `director` (文字列 or null): 監督。
    *   `summary` (文字列 or null): あらすじ。
    *   `cast` (文字列 or null): 主要キャスト文字列。
    *   `producer` (文字列 or null): プロデューサー。
    *   `cinematographer` (文字列 or null): 撮影監督。
    *   `country` (文字列 or null): 製作国。
    *   `runtime` (整数 or null): 上映時間(分)。
    *   `distributor` (文字列 or null): 配給会社。
    *   `full_staff` (辞書のリスト or null): 各スタッフカテゴリをキーとし、そのカテゴリのスタッフリスト（名前、役職/担当などを含む辞書）を値とする辞書。
        ```json
        "full_staff": {
          "監督": [{"name": "監督名", "role": ""}],
          "製作": [{"name": "製作担当者名", "role": ""}],
          ...
        }
        ```
    *   `full_cast` (辞書のリスト or null): 各キャストの名前と役名を含む辞書のリスト。
        ```json
        "full_cast": [
          {"name": "俳優A", "role": "役名A"},
          {"name": "俳優B", "role": "役名B"},
          ...
        ]
        ```
    *   `reviews` (辞書 or null): レビューの集計情報（スコア、レビュー数など）を含む辞書。
        ```json
        "reviews": {
          "average_score": 4.1,
          "review_count": 150,
          "score_distribution": {"5": 80, "4": 40, ...}
        }
        ```
    *   `scraping_timestamp` (文字列): Webスクレイピングで取得した場合のタイムスタンプ (ISO 8601形式)。JSON入力モードでは存在しない場合があります。

*   **用途:**
    *   Web検索モード実行時に、取得した全映画情報がこの形式でタイムスタンプ付きのJSONファイル (`MovieData_YYYYMMDDHHMMSS.json`) として保存されます。
    *   JSON入力モード (`--json-input`) では、この形式のJSONファイルを読み込み、CSVの更新に使用します。

## 使い方

```bash
python fill_movie_details.py --input <入力CSVパス> --output <出力CSVパス> [オプション]
```

**主なオプション:**

*   `--input <パス>` (必須): 入力CSVファイルのパス (Shift_JIS)。
*   `--output <パス>` (必須): 出力CSVファイルのパス (Shift_JIS)。
*   `--limit <件数>` (オプション, Web検索モード時): 一度にWebから取得・処理する映画の最大件数。デフォルトは `5`。
*   `--json-input <パス>` (オプション): このオプションを指定すると、Web検索を行わず、指定されたJSONファイルからデータを読み込んでCSVを更新します。

**実行例:**

*   **Web検索モード (最大10件処理):**
    ```bash
    # movies.csv を読み込み、未入力情報をWebから取得・補完し movies_updated_web.csv に出力
    # 同時に MovieData_YYYYMMDDHHMMSS.json も生成される
    python fill_movie_details.py --input movies.csv --output movies_updated_web.csv --limit 10
    ```
*   **JSON入力モード:**
    ```bash
    # movies.csv を読み込み、MovieData_20250424145731.json の情報で補完し movies_updated_json.csv に出力
    python fill_movie_details.py --input movies.csv --output movies_updated_json.csv --json-input MovieData_20250424145731.json
    ```

## 注意事項

*   映画.com のサイト構造が変更されると、Webスクレイピングが正常に動作しなくなる可能性があります。
*   短時間に大量のリクエストを行うと、アクセスがブロックされる可能性があります (Web検索モード)。スクリプトには待機処理が含まれています。
*   Shift_JISエンコーディングでCSVを保存する際、表現できない文字は `?` に置換されます。これにより、一部の文字情報が失われる可能性があります。
*   JSON入力モードを使用する場合、入力JSONファイルの形式が不正だとエラーになるか、正しく処理されない可能性があります。
*   **CSVファイル、JSONファイル、HTMLファイル (デバッグ用含む) は、Gitなどのバージョン管理システムには登録せず、 `.gitignore` に追加することを強く推奨します。** これらのファイルは、実行ごとに生成されたり、個人情報や大規模データを含む可能性があるためです。

## TODO / 今後の拡張

*   より柔軟な更新条件（特定の列のみ強制的に上書きするオプションなど）
*   Web検索時のエラーハンドリング強化（リトライ処理など）
*   設定ファイル（待機時間、User-Agentなど）の導入
*   テストコードの追加
*   GUIの作成 