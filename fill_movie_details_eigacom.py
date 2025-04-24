import pandas as pd
import requests
from bs4 import BeautifulSoup
import argparse
import logging
import sys
import time
import re # re モジュールをインポート
import json # json モジュールをインポート
from datetime import datetime # datetime モジュールを再インポート
import os # os モジュールを追加 (ファイル存在チェック用)

# --- 共通モジュールとサイト固有モジュールのインポート ---
import movie_scraper_utils as utils
from scrapers import eiga_com_scraper

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)

# User-Agent設定
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

def load_csv(filepath):
    """指定されたパスからShift_JISエンコーディングでCSVファイルを読み込む"""
    try:
        logging.info(f"CSVファイルを読み込み中: {filepath}")
        df = pd.read_csv(filepath, encoding='shift_jis')
        logging.info("CSVファイルの読み込み完了")
        return df
    except FileNotFoundError:
        logging.error(f"エラー: ファイルが見つかりません: {filepath}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"CSVファイルの読み込み中にエラーが発生しました: {e}")
        sys.exit(1)

def find_missing_details(df, limit):
    """公開年が未入力のレコードを抽出する"""
    missing_df = df[df['year'].isnull()].copy()
    missing_df = missing_df.sort_values(by='movie_id').head(limit) # limit引数を使用
    logging.info(f"公開年が未入力の映画を{len(missing_df)}件抽出しました (最大{limit}件)。")
    return missing_df

def search_eiga_com(title):
    """映画.comで映画タイトルを検索し、最上位の作品ページのURLを取得する"""
    search_url = f"https://eiga.com/search/{requests.utils.quote(title)}"
    try:
        logging.info(f"映画.comで検索中: {title} (URL: {search_url})")
        response = requests.get(search_url, headers=HEADERS, timeout=10)
        response.raise_for_status() # HTTPエラーチェック
        soup = BeautifulSoup(response.content, 'html.parser')

        # 検索結果リストの最初のリンクを取得
        search_results = soup.select('#rslt-movie > ul > li > a')
        if search_results:
            movie_page_url = "https://eiga.com" + search_results[0]['href']
            logging.info(f"作品ページURLが見つかりました: {movie_page_url}")
            return movie_page_url
        else:
            logging.warning(f"検索結果が見つかりませんでした: {title}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"映画.comへのリクエスト中にエラーが発生しました ({title}): {e}")
        return None
    except Exception as e:
        logging.error(f"映画.comの検索処理中に予期せぬエラーが発生しました ({title}): {e}")
        return None

def scrape_movie_details(movie_page_url):
    """映画ページのURLから詳細情報を取得する"""
    # details辞書に取得項目を追加
    details = {
        'year': None,
        'director': None,
        'summary': None,
        'cast': None, # 主要キャスト (ログ用)
        'producer': None,
        'cinematographer': None,
        'country': None,
        'runtime': None,
        'distributor': None,
        'full_staff': [], # (ログ用)
        'full_cast': [], # (ログ用)
        'reviews': []
    }
    if not movie_page_url:
        return details

    try:
        logging.info(f"作品ページから詳細情報を取得中: {movie_page_url}")
        response = requests.get(movie_page_url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        # --- デバッグ用: HTMLコンテンツを一時ファイルに保存 ---
        try:
            debug_filename = "_debug_last_scraped_page.html"
            with open(debug_filename, "wb") as f: # バイナリ書き込みモード
                f.write(response.content)
            logging.info(f"  デバッグ用にHTMLを '{debug_filename}' に保存しました。")
        except Exception as e:
            logging.warning(f"  デバッグ用HTMLファイルの保存中にエラー: {e}")
        # --- デバッグ用処理ここまで ---

        soup = BeautifulSoup(response.content, 'html.parser')

        # 公開年 (形式: "YYYY年製作／...")
        production_info_tag = soup.select_one('.movie-info > p, p.data') # セレクタを汎用的に
        if production_info_tag:
            production_text = production_info_tag.get_text(separator=" ", strip=True)
            # 年 (YYYY年)
            year_match = re.search(r'(\d{4})年製作', production_text)
            if year_match:
                details['year'] = int(year_match.group(1))
                logging.info(f"  公開年: {details['year']}")

            # 製作国 (末尾の国名)
            country_match = re.search(r'/\s*([^/]+)\s*$', production_text)
            if country_match:
                details['country'] = country_match.group(1).strip()
                logging.info(f"  製作国: {details['country']}")

            # 上映時間 (XX分)
            runtime_match = re.search(r'(\d+)[分分]', production_text) # 「分」または「 分」に対応
            if runtime_match:
                details['runtime'] = int(runtime_match.group(1))
                logging.info(f"  上映時間: {details['runtime']}分")

            # 配給会社 (配給：XXX)
            distributor_match = re.search(r'配給：(.+)', production_text)
            if distributor_match:
                details['distributor'] = distributor_match.group(1).strip()
                logging.info(f"  配給会社: {details['distributor']}")


        # スタッフ情報 (監督、プロデューサー、撮影)
        staff_section = soup.select_one('#staff-cast dl.movie-staff')
        if staff_section:
            dt_tags = staff_section.find_all('dt')
            staff_dict = {}
            current_role = None
            for tag in staff_section.find_all(['dt', 'dd']):
                if tag.name == 'dt':
                    current_role = tag.text.strip()
                    if current_role not in staff_dict:
                         staff_dict[current_role] = []
                    details['full_staff'].append({'role': current_role, 'names': []}) # full_staff用
                elif tag.name == 'dd' and current_role:
                     name_tag = tag.find('a')
                     name = name_tag.text.strip() if name_tag else tag.text.strip()
                     if name:
                         staff_dict[current_role].append(name)
                         if details['full_staff'] and details['full_staff'][-1]['role'] == current_role:
                             details['full_staff'][-1]['names'].append(name)

            # 抽出したスタッフ情報から必要なものをdetailsに格納
            directors = staff_dict.get('監督', [])
            if directors:
                details['director'] = ", ".join(directors)
                logging.info(f"  監督: {details['director']}")

            producers = staff_dict.get('製作', []) + staff_dict.get('プロデューサー', []) + staff_dict.get('エグゼクティブプロデューサー', [])
            if producers:
                 # 重複を除去して結合
                details['producer'] = ", ".join(sorted(list(set(producers))))
                logging.info(f"  プロデューサー関連: {details['producer']}")

            cinematographers = staff_dict.get('撮影', [])
            if cinematographers:
                 details['cinematographer'] = ", ".join(cinematographers)
                 logging.info(f"  撮影: {details['cinematographer']}")

            # ログ用にスタッフリスト全体（先頭5件程度）を出力
            logging.info(f"  スタッフリスト (一部): {details['full_staff'][:5]}")


        # あらすじ
        story_section = soup.find('div', id='story')
        if story_section and story_section.find('p'):
            summary_text = story_section.find('p').text.strip()
            # 仕様に合わせて文字数制限
            details['summary'] = summary_text[:300] + ('...' if len(summary_text) > 300 else '')
            logging.info(f"  あらすじ取得完了 (先頭部分: {details['summary'][:50]}...)")

        # キャスト情報 (主要キャストを抽出, 例: 先頭4名)
        cast_list_items = soup.select('ul.movie-cast > li')
        if cast_list_items:
            cast_members = []
            for item in cast_list_items[:4]: # 先頭4件を取得
                actor_name_tag = item.select_one('span[itemprop="name"]')
                role_name_tag = item.select_one('small')
                cast_member_info = {}
                if actor_name_tag:
                    actor_name = actor_name_tag.text.strip()
                    cast_member_info['actor'] = actor_name
                    display_text = actor_name
                    if role_name_tag:
                        role_name = role_name_tag.text.strip()
                        cast_member_info['role'] = role_name
                        display_text += f" ({role_name} 役)"
                    else:
                         cast_member_info['role'] = None

                    details['full_cast'].append(cast_member_info)
                    if len(cast_members) < 4: # 主要キャストログ用 (変更なし)
                        cast_members.append(display_text)

            if cast_members: # 主要キャストログ用 (変更なし)
                details['cast'] = ", ".join(cast_members)
                logging.info(f"  キャスト (主要): {details['cast']}")
            # ログ用にキャストリスト全体（先頭5件程度）を出力
            logging.info(f"  キャストリスト (一部): {details['full_cast'][:5]}")

        # レビュー情報 (表示されているものを取得)
        review_section = soup.select_one('.movie-review-list')
        if review_section:
            reviews_data = []
            review_items = review_section.select('.user-review')
            logging.info(f"  ページ内のレビューを {len(review_items)} 件発見。抽出を試みます...")
            for item in review_items:
                review_info = {
                    'reviewer': None,
                    'rating': None,
                    'title': None,
                    'text': None,
                    'date': None,
                    'device': None,
                    'watch_method': None,
                    'impressions': []
                }
                # レビュアー名
                reviewer_tag = item.select_one('.user-name')
                if reviewer_tag: review_info['reviewer'] = reviewer_tag.text.strip()
                # 評価点
                rating_tag = item.select_one('.rating-star')
                if rating_tag:
                    rating_class = next((cls for cls in rating_tag.get('class', []) if cls.startswith('val')), None)
                    if rating_class:
                        try:
                            review_info['rating'] = int(rating_class.replace('val', '')) / 10.0
                        except ValueError:
                            pass # 変換失敗時はNoneのまま
                # レビュータイトル
                title_tag = item.select_one('.review-title a')
                if title_tag: review_info['title'] = title_tag.text.strip()
                # レビュー本文 (ネタバレ考慮せず表示されているテキストを取得)
                text_tag = item.select_one('.txt-block p.short, .txt-block p:not(.hidden)') # 表示されている方を取得
                if text_tag: review_info['text'] = text_tag.text.strip()
                # 投稿日時
                date_tag = item.select_one('.review-data .time')
                if date_tag: review_info['date'] = date_tag.text.strip()
                # 投稿デバイス
                device_tag = item.select_one('.review-data .post-device')
                if device_tag: review_info['device'] = device_tag.text.strip()
                # 鑑賞方法
                watch_method_tag = item.select_one('.review-data .watch-methods')
                if watch_method_tag: review_info['watch_method'] = watch_method_tag.text.strip()
                # 感想タグ
                impression_tags = item.select('.movie-impresses p span')
                review_info['impressions'] = [imp.text.strip() for imp in impression_tags]

                # 有効な情報が一つでもあればリストに追加
                if any(review_info.values()):
                    reviews_data.append(review_info)

            if reviews_data:
                details['reviews'] = reviews_data
                logging.info(f"  レビュー情報を {len(reviews_data)} 件抽出しました。 (例: {details['reviews'][0]['reviewer']}さん)")
            else:
                 logging.info("  レビュー情報の抽出に失敗、またはレビューが存在しませんでした。")

        return details

    except requests.exceptions.RequestException as e:
        logging.error(f"作品ページへのリクエスト中にエラーが発生しました ({movie_page_url}): {e}")
        return details # 部分的に取得できている可能性もあるため、取得済みの情報を返す
    except Exception as e:
        logging.error(f"作品ページの詳細情報取得中に予期せぬエラーが発生しました ({movie_page_url}): {e}")
        return details

def update_dataframe(df, missing_df, json_filepath):
    """取得した情報で元のDataFrameを更新し、詳細データをJSONに保存する"""
    update_count = 0
    processed_movie_ids = set()
    all_details = [] # 処理した映画の詳細を格納するリスト

    for index, row in missing_df.iterrows():
        title = row['title']
        movie_id = row['movie_id']
        logging.info(f"--- 処理開始: {title} (ID: {movie_id}) ---")

        # 既に主要情報が埋まっている場合はスキップ (year, director, summary)
        # 他の列 (cast, country など) は主要情報がなくても更新される可能性があるため、
        # ここでのスキップ条件は主要3項目のみとする
        if pd.notna(df.loc[index, 'year']) and pd.notna(df.loc[index, 'director']) and pd.notna(df.loc[index, 'summary']):
             logging.info(f"スキップ: 主要情報(年,監督,あらすじ)は既に入力済です。他の情報も確認します。")
             # continue せずに他の項目をチェック・更新する

        movie_page_url = search_eiga_com(title)
        # details の初期化もすべての列を含むようにする
        details = {
            'year': None, 'director': None, 'summary': None, 'cast': None,
            'producer': None, 'cinematographer': None, 'country': None,
            'runtime': None, 'distributor': None, 'full_staff': [],
            'full_cast': [], 'reviews': []
        }
        if movie_page_url:
            time.sleep(1)
            details = scrape_movie_details(movie_page_url) # scrape_movie_detailsはこれらのキーを持つ辞書を返す前提

            if details and any(details.values()):
                details['movie_id'] = movie_id
                details['title'] = title
                all_details.append(details)

        # DataFrameの更新 (取得できた情報のみ)
        updated_this_iteration = False # このイテレーションで更新があったか
        original_index = df[df['movie_id'] == movie_id].index

        if not original_index.empty:
            idx = original_index[0]

            # 各列について、DataFrameの値が欠損(NaN)であり、かつdetailsに値が存在する場合に更新
            update_log_messages = [] # 更新ログを一時保存

            # year (特別な1800処理を含む)
            if pd.isna(df.loc[idx, 'year']):
                if details.get('year') is not None:
                    df.loc[idx, 'year'] = details['year']
                    updated_this_iteration = True
                    update_log_messages.append(f"年:{details['year']}")
                else:
                    df.loc[idx, 'year'] = 1800
                    updated_this_iteration = True
                    logging.warning(f"  -> 年情報が見つからなかったため、1800 を設定しました。")
                    # update_log_messages.append("年:1800(デフォルト)") # 1800設定は別ログがあるので不要かも

            # director
            if pd.isna(df.loc[idx, 'director']) and details.get('director') is not None:
                df.loc[idx, 'director'] = details['director']
                updated_this_iteration = True
                update_log_messages.append(f"監督:{details['director'][:20]}...") # 長い場合があるので省略

            # summary
            if pd.isna(df.loc[idx, 'summary']) and details.get('summary') is not None:
                df.loc[idx, 'summary'] = details['summary']
                updated_this_iteration = True
                update_log_messages.append("あらすじ")

            # cast (主要キャスト文字列)
            if pd.isna(df.loc[idx, 'cast']) and details.get('cast') is not None:
                df.loc[idx, 'cast'] = details['cast']
                updated_this_iteration = True
                update_log_messages.append(f"キャスト:{details['cast'][:20]}...")

            # producer
            if pd.isna(df.loc[idx, 'producer']) and details.get('producer') is not None:
                df.loc[idx, 'producer'] = details['producer']
                updated_this_iteration = True
                update_log_messages.append("プロデューサー")

            # cinematographer
            if pd.isna(df.loc[idx, 'cinematographer']) and details.get('cinematographer') is not None:
                df.loc[idx, 'cinematographer'] = details['cinematographer']
                updated_this_iteration = True
                update_log_messages.append("撮影")

            # country
            if pd.isna(df.loc[idx, 'country']) and details.get('country') is not None:
                df.loc[idx, 'country'] = details['country']
                updated_this_iteration = True
                update_log_messages.append(f"製作国:{details['country']}")

            # runtime
            if pd.isna(df.loc[idx, 'runtime']) and details.get('runtime') is not None:
                # runtime は数値型になる可能性があるので、Int64に変換しておくのが望ましい
                try:
                    df.loc[idx, 'runtime'] = pd.to_numeric(details['runtime'], errors='coerce').astype('Int64')
                    updated_this_iteration = True
                    update_log_messages.append(f"上映時間:{details['runtime']}分")
                except (TypeError, ValueError):
                     logging.warning(f"  -> 上映時間の数値変換に失敗: {details['runtime']}")
                     df.loc[idx, 'runtime'] = pd.NA # エラー時はNaNに

            # distributor
            if pd.isna(df.loc[idx, 'distributor']) and details.get('distributor') is not None:
                df.loc[idx, 'distributor'] = details['distributor']
                updated_this_iteration = True
                update_log_messages.append("配給")

            # full_staff (JSON文字列)
            # pd.isna() はリストに対してうまく機能しないことがあるため、値が存在するかどうかで判断
            # または、初期値を pd.NA などにしておき、pd.isna() でチェックする
            if pd.isna(df.loc[idx, 'full_staff']) and details.get('full_staff'): # リストが空でないことを確認
                try:
                    df.loc[idx, 'full_staff'] = json.dumps(details['full_staff'], ensure_ascii=False)
                    updated_this_iteration = True
                    update_log_messages.append("スタッフ詳細(JSON)")
                except Exception as e:
                    logging.warning(f"  -> スタッフ詳細のJSON変換中にエラー: {e}")

            # full_cast (JSON文字列)
            if pd.isna(df.loc[idx, 'full_cast']) and details.get('full_cast'):
                try:
                    df.loc[idx, 'full_cast'] = json.dumps(details['full_cast'], ensure_ascii=False)
                    updated_this_iteration = True
                    update_log_messages.append("キャスト詳細(JSON)")
                except Exception as e:
                    logging.warning(f"  -> キャスト詳細のJSON変換中にエラー: {e}")

            # reviews (JSON文字列)
            if pd.isna(df.loc[idx, 'reviews']) and details.get('reviews'):
                try:
                    df.loc[idx, 'reviews'] = json.dumps(details['reviews'], ensure_ascii=False)
                    updated_this_iteration = True
                    update_log_messages.append("レビュー(JSON)")
                except Exception as e:
                    logging.warning(f"  -> レビューのJSON変換中にエラー: {e}")

            # 更新ログの出力
            if updated_this_iteration:
                logging.info(f"  -> DataFrame更新: {', '.join(update_log_messages)}")
                update_count += 1 # レコード単位ではなく、更新が行われた回数をカウント
            elif not movie_page_url:
                 logging.warning(f"映画.comで作品ページが見つからず、更新できませんでした (ID: {movie_id})")
            else: # URLは見つかったが、更新対象のデータがなかった or 既に埋まっていた
                 logging.info(f"  -> 更新対象の情報が見つからないか、既に値が存在するため、DataFrameは更新されませんでした。")

        else:
            logging.warning(f"元のDataFrameに movie_id = {movie_id} が見つかりません。スキップします。")


        logging.info(f"--- 処理完了: {title} (ID: {movie_id}) ---")

        # 次のタイトル処理前に200ミリ秒待機 (最後のループを除く)
        if index != missing_df.index[-1]: # 最後の映画でなければ待機
            wait_time = 0.2 # 200ミリ秒 = 0.2秒
            logging.info(f"次の映画の処理まで {int(wait_time*1000)}ミリ秒 ({wait_time}秒) 待機します...")
            time.sleep(wait_time)

    # --- ループ完了後、全詳細データをJSONファイルに保存 ---
    if all_details: # 処理したデータが1件以上ある場合
        try:
            with open(json_filepath, 'w', encoding='utf-8') as f:
                json.dump(all_details, f, ensure_ascii=False, indent=4)
            logging.info(f"処理した {len(all_details)} 件の映画の詳細データを '{json_filepath}' に保存しました。")
        except Exception as e:
            logging.error(f"JSONファイル '{json_filepath}' の保存中にエラーが発生しました: {e}")
    else:
        logging.info("JSONファイルへの保存対象となる詳細データがありませんでした。")
    # --- JSON保存処理ここまで ---

    # update_count は更新が行われた回数を示す（レコード数ではない）
    logging.info(f"合計 {update_count} 回のデータ更新を行いました。")
    return df

def save_csv(df, filepath):
    """DataFrameをShift_JISエンコーディングでCSVファイルに保存する"""
    try:
        logging.info(f"更新されたCSVファイルを保存中: {filepath}")
        # year列を整数型に変換しようと試みるが、NaNがあるとエラーになるためfloatのままにするか、fillna後に変換
        # ここでは欠損値はそのまま残す方針とする
        # df['year'] = df['year'].astype('Int64') # pandas 1.0以降

        # Shift_JISでエンコードできない文字は '?' に置換する
        df.to_csv(filepath, encoding='shift_jis', index=False, errors='replace')

        logging.info("CSVファイルの保存完了")
    except Exception as e:
        logging.error(f"CSVファイルの保存中にエラーが発生しました: {e}")
        sys.exit(1)

# --- 新しい関数: JSONファイルの読み込み ---
def load_json(filepath):
    """指定されたパスからJSONファイルを読み込む"""
    if not os.path.exists(filepath):
        logging.error(f"エラー: JSON入力ファイルが見つかりません: {filepath}")
        return None
    try:
        logging.info(f"JSONファイルを読み込み中: {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logging.info("JSONファイルの読み込み完了")
        # 期待する形式 (辞書のリスト) か簡易チェック
        if not isinstance(data, list):
            logging.error(f"エラー: JSONファイルの内容が期待される形式 (リスト) ではありません: {filepath}")
            return None
        # リストの中身が辞書かどうかもチェック (最初の要素で代表)
        if data and not isinstance(data[0], dict):
             logging.error(f"エラー: JSONファイル内の要素が期待される形式 (辞書) ではありません: {filepath}")
             return None
        return data
    except json.JSONDecodeError as e:
        logging.error(f"JSONファイルの解析中にエラーが発生しました ({filepath}): {e}")
        return None
    except Exception as e:
        logging.error(f"JSONファイルの読み込み中に予期せぬエラーが発生しました ({filepath}): {e}")
        return None
# --- JSON読み込み関数ここまで ---

# --- 新しい関数: JSON入力データでDataFrameを更新 ---
def update_dataframe_from_json(df, json_data):
    """JSONデータリストを使ってDataFrameを更新する"""
    update_count = 0
    if not json_data:
        logging.warning("JSONデータが空のため、DataFrameの更新は行われません。")
        return df

    logging.info(f"JSONデータ ({len(json_data)} 件) を使用してDataFrameを更新します...")

    for details in json_data: # detailsは映画情報の辞書
        if not isinstance(details, dict):
            logging.warning(f"JSONデータ内の無効な要素をスキップしました: {details}")
            continue

        movie_id = details.get('movie_id')
        title = details.get('title', '[タイトル不明]') # titleがない場合も考慮

        if movie_id is None:
            logging.warning(f"movie_id が見つからないため、JSONデータ内の要素をスキップしました: {title}")
            continue

        logging.info(f"--- JSONデータ処理開始: {title} (ID: {movie_id}) ---")

        original_index = df[df['movie_id'] == movie_id].index

        if not original_index.empty:
            idx = original_index[0]
            updated_this_iteration = False
            update_log_messages = []

            # 更新対象の列リスト (movie_id, titleを除く)
            columns_to_update = [
                'year', 'director', 'summary', 'cast', 'producer',
                'cinematographer', 'country', 'runtime', 'distributor',
                'full_staff', 'full_cast', 'reviews'
            ]

            for col in columns_to_update:
                # DataFrameの値が欠損しており、かつJSONデータにそのキーと値が存在する場合に更新
                if pd.isna(df.loc[idx, col]) and details.get(col) is not None:
                    value_to_update = details[col]
                    log_message = f"{col}"

                    # JSON文字列として保存する列
                    if col in ['full_staff', 'full_cast', 'reviews']:
                        # JSONデータから読み込んだ値は既にPythonオブジェクト(リスト/辞書)のはず
                        # そのまま json.dumps する
                        try:
                            df.loc[idx, col] = json.dumps(value_to_update, ensure_ascii=False)
                            log_message += "(JSON)"
                        except Exception as e:
                            logging.warning(f"  -> {col} のJSON変換中にエラー: {e}")
                            continue # この列の更新はスキップ
                    # 数値型に変換する列
                    elif col in ['year', 'runtime']:
                        try:
                            # Int64を許容するように変換
                            numeric_value = pd.to_numeric(value_to_update, errors='coerce')
                            if pd.notna(numeric_value):
                                df.loc[idx, col] = int(numeric_value) # Int64に変換
                                log_message += f":{int(numeric_value)}"
                            else:
                                df.loc[idx, col] = pd.NA # 変換失敗時はNA
                                log_message += ": [変換失敗]"
                        except (TypeError, ValueError) as e:
                            logging.warning(f"  -> {col} の数値変換中にエラー: {e} (値: {value_to_update})")
                            df.loc[idx, col] = pd.NA
                            continue
                    # その他の文字列等
                    else:
                        df.loc[idx, col] = value_to_update
                        # 簡単なログ表示のため、長すぎる場合は省略
                        display_value = str(value_to_update)
                        if len(display_value) > 30:
                            display_value = display_value[:27] + "..."
                        log_message += f":{display_value}"

                    updated_this_iteration = True
                    update_log_messages.append(log_message)

            if updated_this_iteration:
                logging.info(f"  -> DataFrame更新: {', '.join(update_log_messages)}")
                update_count += 1
            else:
                logging.info(f"  -> 更新対象の情報が見つからないか、既に値が存在するため、DataFrameは更新されませんでした。")

        else:
            logging.warning(f"元のDataFrameに movie_id = {movie_id} が見つかりません。JSONデータをスキップします。")

        logging.info(f"--- JSONデータ処理完了: {title} (ID: {movie_id}) ---")

    logging.info(f"JSONデータから合計 {update_count} 回のデータ更新を行いました。")
    return df
# --- JSON入力用更新関数ここまで ---

def main():
    # --- 引数処理 ---
    parser = utils.setup_common_parser(description='映画.com から映画の詳細情報を取得・更新するスクリプト')
    # 映画.com固有の引数を追加
    parser.add_argument('--limit', type=int, default=9999, help='Webから取得する場合に処理する最大映画数 (デフォルト: 9999, 無制限に近い値)')
    parser.add_argument('--wait', type=float, default=0.2, help='各映画処理後の待機時間(秒) (デフォルト: 0.2)')
    args = parser.parse_args()

    # --- ロギング設定 ---
    log_level = 'DEBUG' if args.debug else args.log_level
    utils.setup_logging(log_level)
    logging.info("処理を開始します (映画.com)")

    # --- JSON出力ファイル名 (Webスクレイピング時のみ) ---
    json_output_filepath = None
    if not args.json_input:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        # サイト名をファイル名に含める
        json_output_filepath = f"MovieData_eiga.com_{timestamp}.json"
        logging.info(f"抽出データの保存先JSONファイル: {json_output_filepath}")

    # --- CSV読み込みと列準備 ---
    df = utils.load_csv(args.input)
    df = utils.check_and_add_columns(df, utils.DEFAULT_OUTPUT_COLUMNS)

    # --- 処理の分岐 (JSON入力モード / Web検索モード) ---
    if args.json_input:
        # JSONファイルからデータを読み込んで更新
        logging.info(f"--json-input オプション指定: {args.json_input}")
        json_data = utils.load_json(args.json_input)
        if json_data:
            # movie_id を文字列に変換してから更新関数に渡す
            df['movie_id'] = df['movie_id'].astype(str)
            df = utils.update_dataframe_from_json(df, json_data)
        else:
            logging.error("JSONデータの読み込みに失敗したため、処理を中断します。")
            sys.exit(1)

    else:
        # --- Web検索モード ---
        logging.info("Webスクレイピングによりデータを取得・更新します。")

        # 更新対象の判定: 主要3項目(year, director, summary)のいずれかが欠損
        missing_major_info_df = df[
            df['year'].isna() | df['director'].isna() | df['summary'].isna()
        ].copy()
        # movie_id でソートし、limit 件数に絞る
        target_df = missing_major_info_df.sort_values(by='movie_id').head(args.limit)

        logging.info(f"主要情報(年,監督,あらすじ)のいずれかが未入力の映画を {len(target_df)} 件処理対象とします (最大{args.limit}件)。")

        all_scraped_data = [] # スクレイピング結果全体を保存するリスト
        update_count = 0 # 更新された行数をカウント

        if not target_df.empty:
            # movie_id をインデックスに設定して効率化
            df_indexed = df.set_index('movie_id') # movie_id は string 型のはず

            for index, row in target_df.iterrows():
                # movie_id と title を取得 (movie_idは文字列のはず)
                movie_id = str(row['movie_id']) # 念のため文字列に
                title = row['title']
                logging.info(f"--- 処理開始: {title} (ID: {movie_id}) ---")

                scraped_details = None # 初期化
                try:
                    # 1. 検索実行
                    movie_page_url = eiga_com_scraper.search_eiga_com(title)
                    time.sleep(args.wait / 2) # 検索後にも少し待機

                    # 2. 詳細情報取得
                    if movie_page_url:
                        scraped_details = eiga_com_scraper.scrape_movie_details(movie_page_url)
                        if scraped_details and any(v is not None for k, v in scraped_details.items() if k != 'source'): # source以外の何かが取れたか
                             # 取得成功時はmovie_idとtitleを追加してリストに保存
                             scraped_details['movie_id'] = movie_id
                             scraped_details['title'] = title # titleも追加しておく
                             all_scraped_data.append(scraped_details)
                        else:
                             logging.warning(f"  -> 詳細情報の取得に失敗、または有効な情報がありませんでした。URL: {movie_page_url}")
                             scraped_details = None # 失敗した場合は None に戻す

                    # 3. DataFrame を直接更新 (取得できた情報でNaNの箇所のみ)
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
                                             # scraped_details の時点で int になっているはず
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
                             update_count += 1 # 更新があった行数をカウント
                        else:
                             logging.info(f"  -> スクレイピングデータは取得しましたが、DataFrameの更新対象（NaN）はありませんでした。")

                    elif not movie_page_url:
                        logging.warning(f"  -> 映画.comで作品ページが見つかりませんでした。")
                    elif movie_id not in df_indexed.index:
                         logging.error(f"  -> 致命的エラー: movie_id '{movie_id}' がDataFrameインデックスに存在しません。")


                except Exception as e:
                    logging.error(f"  -> 映画'{title}' (ID:{movie_id}) の処理中に予期せぬエラーが発生: {e}", exc_info=args.debug)

                finally:
                     logging.info(f"--- 処理完了: {title} (ID: {movie_id}) ---")
                     # 待機処理 (最後のループを除く)
                     if index != target_df.index[-1]:
                         logging.debug(f"次の映画の処理まで {args.wait}秒 待機します...")
                         time.sleep(args.wait)

            # ループ完了後、インデックスをリセット
            df = df_indexed.reset_index()

            # --- スクレイピング結果をJSONファイルに保存 ---
            if all_scraped_data and json_output_filepath:
                utils.save_json(all_scraped_data, json_output_filepath)
            elif not target_df.empty: # 対象はいたが出力がなかった場合
                logging.info("JSONファイルへの保存対象となる有効なスクレイピングデータがありませんでした。")

            logging.info(f"Webスクレイピングによるデータ更新を {update_count} 行に対して行いました。")

        else:
            logging.info("Webスクレイピングによる更新対象映画が見つかりませんでした。")
            # この場合、JSON出力も行わない


    # --- 最終的なCSV保存 (共通処理) ---
    # 列順序を調整して保存
    df_output = utils.reorder_columns(df, utils.DEFAULT_OUTPUT_COLUMNS)
    utils.save_csv(df_output, args.output)

    logging.info("すべての処理が完了しました。")

if __name__ == '__main__':
    main() 