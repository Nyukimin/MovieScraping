# Eiga.com Scraper

import requests
from bs4 import BeautifulSoup
import re
import logging
import os # デバッグHTML保存用

# User-Agent設定 (このスクレイパー固有)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

def search_eiga_com(title):
    """映画.comで映画タイトルを検索し、最上位の作品ページのURLを取得する"""
    search_url = f"https://eiga.com/search/{requests.utils.quote(title)}"
    try:
        logging.info(f"[映画.com] 検索中: {title} (URL: {search_url})")
        response = requests.get(search_url, headers=HEADERS, timeout=15) # タイムアウト少し延長
        response.raise_for_status() # HTTPエラーチェック
        soup = BeautifulSoup(response.content, 'html.parser')

        # 検索結果リストの最初の映画リンクを取得 (#rslt-movie を優先)
        search_results = soup.select('#rslt-movie > ul > li > a')
        if search_results:
            movie_page_url = "https://eiga.com" + search_results[0]['href']
            logging.info(f"  [映画.com] 作品ページURL発見: {movie_page_url}")
            return movie_page_url
        else:
            # 人物などでヒットした場合も考慮するかもしれないが、一旦映画のみ
            logging.warning(f"  [映画.com] 検索結果で作品ページが見つかりませんでした: {title}")
            return None
    except requests.exceptions.Timeout:
        logging.error(f"[映画.com] 検索タイムアウト: {title} ({search_url})")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"[映画.com] 検索リクエストエラー ({title}): {e}")
        return None
    except Exception as e:
        logging.error(f"[映画.com] 検索処理中の予期せぬエラー ({title}): {e}")
        return None

def scrape_movie_details(movie_page_url, debug_mode=False):
    """映画ページのURLから詳細情報を標準化された辞書形式で取得する"""
    details = {
        'source': 'eiga.com', # 情報源を追加
        'year': None,
        'director': None,
        'summary': None,
        'cast': None, # 主要キャスト文字列
        'producer': None,
        'cinematographer': None,
        'country': None,
        'runtime': None,
        'distributor': None,
        'full_staff': None, # JSON化する前のリスト/辞書
        'full_cast': None,  # JSON化する前のリスト/辞書
        'reviews': None     # JSON化する前のリスト/辞書
    }
    if not movie_page_url or not movie_page_url.startswith("https://eiga.com"):
        logging.warning(f"無効なURLのためスキップ: {movie_page_url}")
        return details # 空のdetailsを返す

    try:
        logging.info(f"[映画.com] 詳細情報取得中: {movie_page_url}")
        response = requests.get(movie_page_url, headers=HEADERS, timeout=15) # タイムアウト少し延長
        response.raise_for_status()

        # --- デバッグ用HTML保存 ---
        if debug_mode:
            try:
                debug_filename = "_debug_last_scraped_page_eigacom.html"
                with open(debug_filename, "wb") as f:
                    f.write(response.content)
                logging.debug(f"  [映画.com] デバッグ用にHTMLを '{debug_filename}' に保存しました。")
            except Exception as e:
                logging.warning(f"  [映画.com] デバッグ用HTMLファイルの保存中にエラー: {e}")
        # --- デバッグ用ここまで ---

        soup = BeautifulSoup(response.content, 'html.parser')

        # --- 各種情報抽出 ---
        # 基本情報 (公開年、製作国、上映時間、配給)
        production_info_tag = soup.select_one('.movie-info > p.data, p.data') # セレクタ調整
        if production_info_tag:
            production_text = production_info_tag.get_text(separator=" / ", strip=True) # separator変更
            logging.debug(f"  基本情報テキスト: {production_text}")

            # 年 (YYYY年製作)
            year_match = re.search(r'(\d{4})年製作', production_text)
            if year_match:
                details['year'] = int(year_match.group(1))
                logging.debug(f"    公開年: {details['year']}")

            # 国 (最後が国名パターンが多い)
            parts = [p.strip() for p in production_text.split('/') if p.strip()]
            if len(parts) > 1 and not re.search(r'\d', parts[-1]) and "配給" not in parts[-1]: # 最後が数字や配給会社でなければ国と仮定
                details['country'] = parts[-1]
                logging.debug(f"    製作国: {details['country']}")

            # 時間 (XX分)
            runtime_match = re.search(r'(\d+)分', production_text)
            if runtime_match:
                details['runtime'] = int(runtime_match.group(1))
                logging.debug(f"    上映時間: {details['runtime']}分")

            # 配給 (配給：XXX)
            distributor_match = re.search(r'配給：([^/]+)', production_text)
            if distributor_match:
                details['distributor'] = distributor_match.group(1).strip()
                logging.debug(f"    配給会社: {details['distributor']}")

        # スタッフ情報
        staff_section = soup.select_one('#staff-cast dl.movie-staff')
        if staff_section:
            full_staff_dict = {}
            directors = []
            producers = []
            cinematographers = []
            current_role = None
            for tag in staff_section.find_all(['dt', 'dd']):
                if tag.name == 'dt':
                    current_role = tag.text.strip()
                    if current_role not in full_staff_dict:
                         full_staff_dict[current_role] = []
                elif tag.name == 'dd' and current_role:
                     name_tag = tag.find('a')
                     name = name_tag.text.strip() if name_tag else tag.text.strip()
                     if name:
                         full_staff_dict[current_role].append({"name": name, "role": ""}) # roleは空で統一
                         # 特定の役職も別途抽出
                         if current_role == '監督':
                             directors.append(name)
                         elif current_role in ['製作', 'プロデューサー', '製作総指揮', 'エグゼクティブプロデューサー']:
                             producers.append(name)
                         elif current_role == '撮影':
                             cinematographers.append(name)

            if full_staff_dict: details['full_staff'] = full_staff_dict # JSON用に辞書構造で保存
            if directors: details['director'] = ", ".join(directors)
            if producers: details['producer'] = ", ".join(sorted(list(set(producers)))) # 重複除去
            if cinematographers: details['cinematographer'] = ", ".join(cinematographers)
            logging.debug(f"    監督: {details['director']}, P: {details['producer']}, 撮影: {details['cinematographer']}")
            logging.debug(f"    全スタッフ (一部): {str(details['full_staff'])[:100]}...")


        # あらすじ
        story_section = soup.find('div', id='story')
        if story_section and story_section.find('p'):
            summary_text = story_section.find('p').text.strip()
            details['summary'] = summary_text[:300] + ('...' if len(summary_text) > 300 else '') # 文字数制限
            logging.debug(f"    あらすじ取得 (先頭): {details['summary'][:50]}...")

        # キャスト情報
        cast_list_items = soup.select('ul.movie-cast > li')
        if cast_list_items:
            full_cast_list = []
            main_cast_strings = [] # ログ用
            for item in cast_list_items:
                actor_name_tag = item.select_one('span[itemprop="name"]')
                role_name_tag = item.select_one('small')
                actor_name = actor_name_tag.text.strip() if actor_name_tag else None
                role_name = role_name_tag.text.strip() if role_name_tag else None

                if actor_name:
                    cast_info = {"name": actor_name, "role": role_name}
                    full_cast_list.append(cast_info)
                    # 主要キャストログ用 (先頭4名程度)
                    if len(main_cast_strings) < 4:
                        display_text = actor_name
                        if role_name: display_text += f" ({role_name})" # 役名は括弧なしに変更
                        main_cast_strings.append(display_text)

            if full_cast_list: details['full_cast'] = full_cast_list # JSON用にリストで保存
            if main_cast_strings: details['cast'] = ", ".join(main_cast_strings)
            logging.debug(f"    キャスト (主要): {details['cast']}")
            logging.debug(f"    全キャスト (一部): {str(details['full_cast'])[:100]}...")


        # レビュー情報 (スコアと件数のみ取得する方針に変更)
        review_summary_section = soup.select_one('.review-l') # スコアと件数があるセクション
        if review_summary_section:
            score_tag = review_summary_section.select_one('.rating-star')
            count_tag = review_summary_section.select_one('.rvw-count a') # 件数リンク
            reviews_dict = {}
            if score_tag:
                score_class = next((cls for cls in score_tag.get('class', []) if cls.startswith('val')), None)
                if score_class:
                    try:
                        reviews_dict['average_score'] = round(int(score_class.replace('val', '')) / 10.0, 1)
                    except ValueError: pass
            if count_tag:
                count_match = re.search(r'(\d+)', count_tag.text)
                if count_match:
                    reviews_dict['review_count'] = int(count_match.group(1))

            if reviews_dict:
                details['reviews'] = reviews_dict # JSON用に辞書で保存
                logging.debug(f"    レビュー概要: {details['reviews']}")
            else:
                 logging.debug("    レビュー概要が見つかりませんでした。")

        return details

    except requests.exceptions.Timeout:
        logging.error(f"[映画.com] 詳細取得タイムアウト: {movie_page_url}")
        return details # 取得できた部分だけ返す
    except requests.exceptions.RequestException as e:
        logging.error(f"[映画.com] 詳細取得リクエストエラー ({movie_page_url}): {e}")
        return details
    except Exception as e:
        logging.error(f"[映画.com] 詳細取得処理中の予期せぬエラー ({movie_page_url}): {e}")
        return details

# TODO: Move Eiga.com specific search and scrape functions here 