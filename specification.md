映画詳細情報自動補完ツール：仕様書
✦ 概要
映画タイトルのみが記載されたCSVファイルにおいて、**未入力の詳細項目（公開年、監督名、あらすじ等）**を、映画.comから自動で収集・補完、または指定されたJSONファイルから読み込んで補完し、CSVファイルとして出力するPythonベースの自動処理スクリプト。

✦ 処理対象
入力形式：
1.  **CSVファイル (`--input`)**: Shift_JISエンコーディング
    *   必須列: `movie_id`, `title`
    *   オプション列（存在しない場合は自動追加）: `year`, `director`, `summary`, `cast`, `producer`, `cinematographer`, `country`, `runtime`, `distributor`, `full_staff`, `full_cast`, `reviews`
2.  **JSONファイル (`--json-input`, オプション)**: UTF-8エンコーディング
    *   形式: 映画情報の辞書を含むリスト。各辞書には `movie_id` および上記オプション列に対応するキーが含まれることを期待。
    *   例: `MovieData_YYYYMMDDHHMMSS.json`

Web検索（スクレイピング）が実行される条件：
`--json-input` オプションが **指定されない** 場合で、かつCSVファイル内に以下の **いずれか** に該当する映画レコードが存在する場合

*   `year` が空欄またはNaN
*   `director` が空欄またはNaN
*   `summary` が空欄またはNaN

✦ 主な機能とフロー
*   **モード分岐:** `--json-input` オプションの有無で処理が分岐する。

**【Web検索モード (`--json-input` なし)】**

① CSV読み込み
    *   Shift_JIS で読み込み (`--input`)
    *   データ構造を pandas.DataFrame として保持
    *   必須列 (`movie_id`, `title`) が存在しない場合はエラー終了
    *   仕様書記載のオプション列が存在しない場合は追加して NaN で初期化
    *   `year`, `runtime` 列を数値型 (Int64) に変換 (変換できない値は NaN)

② 詳細未入力映画の抽出
    *   上記の「Web検索が実行される条件」に該当するレコードから、 `--limit` で指定された件数 (デフォルト5件) を抽出
    *   優先順位：`movie_id` 昇順でソートして選定

③ 映画.comによる情報取得（スクレイピング）
    *   抽出された各映画タイトルで映画.comを検索
    *   検索結果の最上位の作品リンクを取得
    *   作品ページから以下の情報を取得：
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
    *   各リクエスト間に 1秒、各タイトル処理後に 0.2秒 の待機時間を挿入
    *   最後にスクレイピングしたページのHTMLを `_debug_last_scraped_page.html` に保存

④ 取得データの一次保存 (JSON)
    *   ③で取得した全映画 (limit件数分) の詳細データをリストに格納
    *   タイムスタンプ付きのJSONファイル (`MovieData_YYYYMMDDHHMMSS.json`) にUTF-8で出力

⑤ CSVの更新 (Web検索結果)
    *   ③で取得した情報を元に、DataFrameを更新。
    *   更新条件: 元のDataFrameの値が NaN の場合のみ。
    *   `year` が取得できなかった場合は `1800` を設定。
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
*   映画.com側のサイト構造が変更された場合、スクレイピングが機能しなくなる可能性がある。
*   ネットワークエラーやサイト側の応答によっては情報取得に失敗する場合がある (Web検索モード)。
*   公開年が取得できない場合、Web検索モードでは `1800` という固定値が設定される。
*   Shift_JISで保存する際、エンコードできない文字は `?` に置換されるため、元の情報が一部失われる可能性がある。
*   JSON入力モードでは、入力JSONファイルの形式が期待通りでない場合、エラー終了または意図しない動作をする可能性がある。
*   User-Agent は一般的なブラウザ (`Chrome`) のものを設定。

✦ 今後の拡張候補（備考）
*   より高度な「未入力」判定ロジック（特定の列が空の場合のみ対象とする等）
*   GPTs連携による補完＋整形
*   あらすじの要約精度の向上
*   GUI操作 or GPTs化（ファイルアップ→DL）
*   より堅牢なエラーハンドリングとリトライ処理 (Web検索モード)

✦ 想定実行例（CLI）
*   Web検索で補完 (最大10件):
    ```bash
    python fill_movie_details.py --input movies.csv --output movies_updated_web.csv --limit 10
    ```
*   JSONファイルから補完:
    ```bash
    python fill_movie_details.py --input movies.csv --output movies_updated_json.csv --json-input MovieData_YYYYMMDDHHMMSS.json
    ```

【重要】CSVファイルはGitで管理しない
