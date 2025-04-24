映画詳細情報自動補完ツール：仕様書
✦ 概要
映画タイトルのみが記載されたCSVファイルにおいて、**未入力の詳細項目（公開年、監督名、あらすじ等）**を、複数の映画情報サイト（**映画.com, Kinenote, Yahoo!映画, Filmarks** 等）から自動で収集・補完、または指定されたJSONファイルから読み込んで補完し、CSVファイルとして出力するPythonベースの自動処理スクリプト群。

✦ 処理対象
入力形式：
1.  **CSVファイル (`--input`)**: Shift_JISエンコーディング
    *   必須列: `movie_id`, `title`
    *   オプション列（存在しない場合は自動追加）: `year`, `director`, `summary`, `cast`, `producer`, `cinematographer`, `country`, `runtime`, `distributor`, `full_staff`, `full_cast`, `reviews`
2.  **JSONファイル (`--json-input`, オプション)**: UTF-8エンコーディング
    *   形式: 映画情報の辞書を含むリスト。各辞書には `movie_id` および上記オプション列に対応するキーが含まれることを期待。
    *   例: `MovieData_<サイト名>_YYYYMMDDHHMMSS.json` (サイトごとに生成される場合)

Web検索（スクレイピング）が実行される条件：
`--json-input` オプションが **指定されない** 場合で、かつCSVファイル内に以下の **いずれか** に該当する映画レコードが存在する場合

*   `year` が空欄またはNaN
*   `director` が空欄またはNaN
*   `summary` が空欄またはNaN

✦ 主な機能とフロー
*   **サイト別スクリプト:** 各映画情報サイトに対応する個別のスクレイパー (`scrapers/<サイト名>_scraper.py`) と、それを呼び出すメインスクリプト (`fill_movie_details_<サイト名>.py`) によって処理を実行する。
*   **モード分岐:** 各メインスクリプトにおいて、`--json-input` オプションの有無で処理が分岐する。

**【Web検索モード (`--json-input` なし)】**

① CSV読み込み (各 `fill_movie_details_<サイト名>.py` 共通)
    *   Shift_JIS で読み込み (`--input`)
    *   データ構造を pandas.DataFrame として保持
    *   必須列 (`movie_id`, `title`) が存在しない場合はエラー終了
    *   仕様書記載のオプション列が存在しない場合は追加して NaN で初期化
    *   `year`, `runtime` 列を数値型 (Int64) に変換 (変換できない値は NaN)

② 詳細未入力映画の抽出 (各 `fill_movie_details_<サイト名>.py` 共通)
    *   上記の「Web検索が実行される条件」に該当するレコードから、 `--limit` で指定された件数 (デフォルト5件) を抽出
    *   優先順位：`movie_id` 昇順でソートして選定

③ 映画情報サイトによる情報取得（スクレイピング, サイトごとに実装）
    *   **対象サイト:** スクリプト名に対応するサイト（例: `fill_movie_details_kinenote.py` ならKinenote）
    *   抽出された各映画タイトルで対象サイトを検索
    *   検索結果から最上位（または最も適切）と思われる作品リンクを取得
    *   作品ページから以下の情報を取得（サイトによって取得可能な項目は異なる）：
        *   `year` (公開年)
        *   `director` (監督)
        *   `summary` (あらすじ, 最大300字程度)
        *   `cast` (主要キャスト文字列, 先頭4名程度)
        *   `producer` (プロデューサー関連)
        *   `cinematographer` (撮影監督)
        *   `country` (製作国)
        *   `runtime` (上映時間, 分)
        *   `distributor` (配給会社)
        *   `full_staff` (全スタッフ情報, 辞書のリスト)
        *   `full_cast` (全キャスト情報, 辞書のリスト)
        *   `reviews` (レビュー情報, 辞書のリスト)
    *   **スクレイピング手法:**
        *   基本は `requests` + `BeautifulSoup` を使用。
        *   JavaScriptによる動的コンテンツ読み込みが必要なサイト（例: Kinenoteのリンク抽出）の場合、**Selenium** を使用する実装を検討・導入する。
    *   **待機時間:** 各リクエスト間やタイトル処理後に適切な待機時間を挿入（例: 1秒など）。
    *   **デバッグ用ファイル:** `--debug` オプション指定時、最後にスクレイピングしたページや検索結果ページのHTMLを `_debug_last_scraped_page_<サイト名>.html` や `_debug_search_result_<サイト名>.html` のようなファイル名で保存する。

④ 取得データの一次保存 (JSON)
    *   ③で取得した全映画 (limit件数分) の詳細データをリストに格納
    *   サイト名とタイムスタンプ付きのJSONファイル (`MovieData_<サイト名>_YYYYMMDDHHMMSS.json`) にUTF-8で出力

⑤ CSVの更新 (Web検索結果)
    *   ③で取得した情報を元に、DataFrameを更新。
    *   更新条件: 元のDataFrameの値が NaN の場合のみ。
    *   `year` が取得できなかった場合はサイトや仕様に応じて処理（例: Kinenoteでは未設定、旧映画.comでは`1800`）。
    *   `full_staff`, `full_cast`, `reviews` はJSON文字列に変換して保存。
    *   `year`, `runtime` は数値 (Int64) として保存。

⑥ CSVの保存・出力
    *   下記【共通処理】の「CSV保存・出力」を実行。

**【JSON入力モード (`--json-input` あり)】**

① CSV読み込み
    *   Web検索モードの①と同様。

② JSON読み込み
    *   `--json-input` で指定されたJSONファイルをUTF-8で読み込む。
    *   ファイルが存在しない、または形式が不正な場合 (リストでない、要素が辞書でない等) はエラー終了。

③ CSVの更新 (JSONデータ)
    *   ②で読み込んだJSONデータ (映画情報のリスト) を使用してDataFrameを更新。
    *   更新キー: `movie_id`
    *   更新条件: 元のDataFrameの値が NaN であり、かつJSONデータに対応するキーと値が存在する場合のみ。
    *   `full_staff`, `full_cast`, `reviews` はJSON文字列に変換して保存。
    *   `year`, `runtime` は数値 (Int64) として保存 (JSON内の値が数値に変換できない場合はNaN/NA)。

④ CSVの保存・出力
    *   下記【共通処理】の「CSV保存・出力」を実行。

**【共通処理】**

*   **CSV保存・出力:**
    *   保存ファイル名：`--output` で指定されたファイル名
    *   出力形式：Shift_JIS
    *   **列順序:** `movie_id`, `title`, `year`, `director`, `summary`, `cast`, `producer`, `cinematographer`, `country`, `runtime`, `distributor`, `full_staff`, `full_cast`, `reviews` の順序。元CSVにしか存在しない列はその後ろに追加される。
    *   **エンコードエラー処理:** Shift_JISで表現できない文字は `?` に置換 (`errors='replace'`)。

✦ 制約・注意点
*   Web検索モードでは、各実行で処理するのは `--limit` で指定された最大件数 (デフォルト5件)。
*   **対象サイト側の構造変更:** 各映画情報サイトのHTML構造や仕様が変更された場合、対応するスクレイピング処理が機能しなくなる可能性がある。
*   ネットワークエラーやサイト側の応答によっては情報取得に失敗する場合がある (Web検索モード)。
*   **Shift_JISエンコード:** 保存時にShift_JISで表現できない文字は `?` に置換され、情報が一部欠落する可能性がある。
*   **Selenium利用時の注意:**
    *   Seleniumを使用するスクリプトを実行する場合、対応するブラウザの **WebDriver** のセットアップが別途必要になる。
    *   `requests` に比べ、処理速度が低下し、メモリ消費量が増加する傾向がある。
*   JSON入力モードでは、入力JSONファイルの形式が期待通りでない場合、エラー終了または意図しない動作をする可能性がある。
*   User-Agent はサイトに応じて適切なものを設定（例: 一般的なブラウザ）。

✦ 今後の拡張候補（備考）
*   より高度な「未入力」判定ロジック
*   取得情報ソース（どのサイトから取得したか）をCSVに記録
*   GPTs連携による補完＋整形
*   あらすじの要約精度の向上
*   GUI操作 or GPTs化
*   より堅牢なエラーハンドリングとリトライ処理
*   複数サイトを一括で検索・最適な情報を選択する機能

✦ 想定実行例（CLI）
*   KinenoteからWeb検索で補完 (最大10件、デバッグモード):
    ```bash
    python fill_movie_details_kinenote.py --input movies.csv --output movies_updated_kinenote.csv --limit 10 --debug
    ```
*   Yahoo!映画からWeb検索で補完 (デフォルト5件):
    ```bash
    python fill_movie_details_yahooeiga.py --input movies.csv --output movies_updated_yahoo.csv
    ```
*   KinenoteのJSONファイルから補完:
    ```bash
    python fill_movie_details_kinenote.py --input movies.csv --output movies_updated_from_json.csv --json-input MovieData_kinenote.com_YYYYMMDDHHMMSS.json
    ```

【重要】CSVファイルはGitで管理しない
