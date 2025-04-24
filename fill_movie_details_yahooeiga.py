# Yahoo!映画 詳細情報自動補完ツール

import pandas as pd
import logging
import sys
import time
from datetime import datetime
import argparse
import json

# --- 共通モジュールとサイト固有モジュールのインポート ---
import movie_scraper_utils as utils
from scrapers import yahoo_eiga_scraper # Yahoo!用のスクレイパーをインポート

# --- メイン処理 ---
def main():
    # --- 引数処理 ---
    parser = utils.setup_common_parser(description='Yahoo!映画 から映画の詳細情報を取得・更新するスクリプト')
    # Yahoo!映画固有の引数を追加 (映画.comと同じものを流用)
    parser.add_argument('--limit', type=int, default=9999, help='Webから取得する場合に処理する最大映画数 (デフォルト: 9999, 無制限に近い値)')
    parser.add_argument('--wait', type=float, default=0.5, help='各映画処理後の待機時間(秒) (デフォルト: 0.5)') # Yahooは少し長めに設定
    args = parser.parse_args()

    # --- ロギング設定 ---
    log_level = 'DEBUG' if args.debug else args.log_level
    utils.setup_logging(log_level)
    logging.info("処理を開始します (Yahoo!映画)")

    # --- JSON出力ファイル名 (Webスクレイピング時のみ) ---
    json_output_filepath = None
    if not args.json_input:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        # サイト名をファイル名に含める
        json_output_filepath = f"MovieData_yahoo.co.jp_{timestamp}.json"
        logging.info(f"抽出データの保存先JSONファイル: {json_output_filepath}")

    # --- CSV読み込みと列準備 ---
    df = utils.load_csv(args.input)
    df = utils.check_and_add_columns(df, utils.DEFAULT_OUTPUT_COLUMNS)

    # --- 処理の分岐 (JSON入力モード / Web検索モード) ---
    if args.json_input:
        logging.info(f"--json-input オプション指定: {args.json_input}")
        json_data = utils.load_json(args.json_input)
        if json_data:
            df['movie_id'] = df['movie_id'].astype(str) # 更新前に文字列化
            df = utils.update_dataframe_from_json(df, json_data)
        else:
            logging.error("JSONデータの読み込みに失敗したため、処理を中断します。")
            sys.exit(1)

    else:
        # --- Web検索モード ---
        logging.info("Webスクレイピングによりデータを取得・更新します。")

        missing_major_info_df = df[
            df['year'].isna() | df['director'].isna() | df['summary'].isna()
        ].copy()
        target_df = missing_major_info_df.sort_values(by='movie_id').head(args.limit)

        logging.info(f"主要情報(年,監督,あらすじ)のいずれかが未入力の映画を {len(target_df)} 件処理対象とします (最大{args.limit}件)。")

        all_scraped_data = []
        update_count = 0

        if not target_df.empty:
            df_indexed = df.set_index('movie_id') # 文字列化済みのはず

            for index, row in target_df.iterrows():
                movie_id = str(row['movie_id'])
                title = row['title']
                logging.info(f"--- 処理開始: {title} (ID: {movie_id}) ---")

                scraped_details = None
                try:
                    # 1. 検索実行 (Yahoo!用関数を呼び出し)
                    movie_page_url = yahoo_eiga_scraper.search_yahoo_eiga(title)
                    time.sleep(args.wait / 2)

                    # 2. 詳細情報取得 (Yahoo!用関数を呼び出し)
                    if movie_page_url:
                        scraped_details = yahoo_eiga_scraper.scrape_movie_details(movie_page_url, debug_mode=args.debug)
                        if scraped_details and any(v is not None for k, v in scraped_details.items() if k != 'source'):
                             scraped_details['movie_id'] = movie_id
                             scraped_details['title'] = title
                             all_scraped_data.append(scraped_details)
                        else:
                             logging.warning(f"  -> 詳細情報の取得に失敗、または有効な情報がありませんでした。URL: {movie_page_url}")
                             scraped_details = None

                    # 3. DataFrame を直接更新 (ロジックは映画.comと同じ)
                    if scraped_details and movie_id in df_indexed.index:
                        updated_this_iteration = False
                        update_log_messages = []
                        for col, value in scraped_details.items():
                            if col in df_indexed.columns and col not in ['movie_id', 'title', 'source'] and value is not None:
                                if pd.isna(df_indexed.loc[movie_id, col]):
                                    try:
                                        log_message = f"{col}"
                                        if col in ['full_staff', 'full_cast', 'reviews']:
                                            df_indexed.loc[movie_id, col] = json.dumps(value, ensure_ascii=False)
                                            log_message += "(JSON)"
                                        elif col in ['year', 'runtime']:
                                            df_indexed.loc[movie_id, col] = int(value)
                                            log_message += f":{int(value)}"
                                        else:
                                            df_indexed.loc[movie_id, col] = str(value)
                                            display_value = str(value)
                                            if len(display_value) > 30: display_value = display_value[:27] + "..."
                                            log_message += f":{display_value}"
                                        updated_this_iteration = True
                                        update_log_messages.append(log_message)
                                    except Exception as e:
                                        logging.warning(f"  -> [{movie_id}:{title}] 列'{col}'の更新中にエラー: {e} (値: {str(value)[:50]}...)")

                        if updated_this_iteration:
                             logging.info(f"  -> DataFrame更新: {', '.join(update_log_messages)}")
                             update_count += 1
                        else:
                             logging.info(f"  -> スクレイピングデータは取得しましたが、DataFrameの更新対象（NaN）はありませんでした。")

                    elif not movie_page_url:
                        logging.warning(f"  -> Yahoo!映画で作品ページが見つかりませんでした。")
                    elif movie_id not in df_indexed.index:
                         logging.error(f"  -> 致命的エラー: movie_id '{movie_id}' がDataFrameインデックスに存在しません。")

                except Exception as e:
                    logging.error(f"  -> 映画'{title}' (ID:{movie_id}) の処理中に予期せぬエラーが発生: {e}", exc_info=args.debug)

                finally:
                     logging.info(f"--- 処理完了: {title} (ID: {movie_id}) ---")
                     if index != target_df.index[-1]:
                         logging.debug(f"次の映画の処理まで {args.wait}秒 待機します...")
                         time.sleep(args.wait)

            df = df_indexed.reset_index()

            if all_scraped_data and json_output_filepath:
                utils.save_json(all_scraped_data, json_output_filepath)
            elif not target_df.empty:
                logging.info("JSONファイルへの保存対象となる有効なスクレイピングデータがありませんでした。")

            logging.info(f"Webスクレイピングによるデータ更新を {update_count} 行に対して行いました。")

        else:
            logging.info("Webスクレイピングによる更新対象映画が見つかりませんでした。")

    # --- 最終的なCSV保存 ---
    df_output = utils.reorder_columns(df, utils.DEFAULT_OUTPUT_COLUMNS)
    utils.save_csv(df_output, args.output)

    logging.info("すべての処理が完了しました。")

if __name__ == '__main__':
    main() 