# scrapers/filmarks_scraper.py
import requests
from bs4 import BeautifulSoup
import re
import logging
import os
from urllib.parse import quote
import json

# User-Agent設定 (共通)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

def search_filmarks(title):
    """Filmarksで映画タイトルを検索し、最上位の作品ページのURLを取得する (推測)"""
    search_query = quote(title)
    search_url = f"https://filmarks.com/search/movies?q={search_query}" # Filmarksの検索URL (要確認)
    try:
        logging.info(f"[Filmarks] 検索中: {title} (URL: {search_url})")
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        # --- デバッグ用に検索結果HTMLを保存 ---
        try:
            debug_filename = "_debug_search_result_filmarks.html"
            with open(debug_filename, "wb") as f:
                f.write(response.content)
            logging.debug(f"  [Filmarks] デバッグ用に検索結果HTMLを '{debug_filename}' に保存しました。")
        except Exception as e:
            logging.warning(f"  [Filmarks] デバッグ用検索結果HTMLの保存中にエラー: {e}")
        # --- デバッグ用ここまで ---

        soup = BeautifulSoup(response.content, 'html.parser')

        # --- !! 推測セレクタ !! ---
        # 検索結果リストの最初の映画リンクを探す
        # 以前の推測: result_link = soup.select_one('.p-content-cassette__title a[href^="/movies/"]')
        # HTML構造に基づき修正: 最初の結果ブロック内の `/movies/` で始まるリンクを探す
        result_link = soup.select_one('div.p-content-cassette a[href^="/movies/"]') # 修正後のセレクタ

        if result_link and result_link.get('href'):
            # 相対URLを絶対URLに変換
            movie_page_url = "https://filmarks.com" + result_link['href']
            logging.info(f"  [Filmarks] 作品ページURL発見: {movie_page_url}")
            return movie_page_url
        else:
            logging.warning(f"  [Filmarks] 検索結果で作品ページが見つかりませんでした: {title}")
            return None
    except requests.exceptions.Timeout:
        logging.error(f"[Filmarks] 検索タイムアウト: {title} ({search_url})")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"[Filmarks] 検索リクエストエラー ({title}): {e}")
        return None
    except Exception as e:
        logging.error(f"[Filmarks] 検索処理中の予期せぬエラー ({title}): {e}")
        return None

def scrape_movie_details(movie_page_url, debug_mode=False):
    """Filmarks映画ページのURLから詳細情報を標準化された辞書形式で取得する"""
    details = {
        'source': 'filmarks.com', # 情報源
        'year': None, 'director': None, 'summary': None, 'cast': None,
        'producer': None, 'cinematographer': None, 'country': None,
        'runtime': None, 'distributor': None, 'full_staff': None,
        'full_cast': None, 'reviews': None
    }
    if not movie_page_url or not movie_page_url.startswith("https://filmarks.com"):
        logging.warning(f"無効なURLのためスキップ: {movie_page_url}")
        return details

    try:
        logging.info(f"[Filmarks] 詳細情報取得中: {movie_page_url}")
        response = requests.get(movie_page_url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        # --- デバッグ用HTML保存 ---
        if debug_mode:
            try:
                debug_filename = "_debug_last_scraped_page_filmarks.html"
                with open(debug_filename, "wb") as f:
                    f.write(response.content)
                logging.debug(f"  [Filmarks] デバッグ用にHTMLを '{debug_filename}' に保存しました。")
            except Exception as e:
                logging.warning(f"  [Filmarks] デバッグ用HTMLファイルの保存中にエラー: {e}")
        # --- デバッグ用ここまで ---

        soup = BeautifulSoup(response.content, 'html.parser')

        # --- 各種情報抽出 (セレクタ修正) ---
        logging.debug(f"  ページタイトル: {soup.title.string if soup.title else '[タイトル不明]'}")

        # 年・国・時間 (ヘッダー付近の div.p-content-detail__other-info から抽出)
        # 以前の推測: meta_div = soup.select_one('div.p-content-detail__meta')
        other_info_div = soup.select_one('div.p-content-detail__other-info')
        if other_info_div:
            # h3 タグの内容を結合して解析する方が確実か？
            # 例: 上映日：2023年04月28日 / 製作国：日本 / アメリカ / 上映時間：114分
            full_text = ""
            elements = other_info_div.find_all(['h3', 'ul'], recursive=False)
            last_h3 = None
            for elem in elements:
                if elem.name == 'h3':
                    full_text += elem.get_text(strip=True) + " "
                    last_h3 = elem.get_text(strip=True)
                elif elem.name == 'ul' and last_h3 and "製作国" in last_h3:
                    countries = [a.get_text(strip=True) for a in elem.select('li > a')]
                    full_text += ", ".join(countries) + " " # 国を連結

            logging.debug(f"  メタ情報テキスト(結合): {full_text}")

            # 年 (YYYY年) - ページタイトル横からも取得試行
            year_from_title = None
            title_h2 = soup.select_one('h2.p-content-detail__title')
            if title_h2:
                next_h2 = title_h2.find_next_sibling('h2') # Filmarksではタイトル横のh2に年情報があることが多い
                if next_h2 and next_h2.small and next_h2.small.a:
                     year_text = next_h2.small.a.get_text(strip=True)
                     year_match_title = re.search(r'(\d{4})年', year_text)
                     if year_match_title:
                         year_from_title = int(year_match_title.group(1))
                         details['year'] = year_from_title
                         logging.debug(f"    年(タイトル横から取得): {details['year']}")

            # 年 (他の場所からも取得試行 - 見つかっていない場合)
            if details['year'] is None:
                 year_match = re.search(r'(\d{4})年', full_text) # YYYY年形式を探す
                 if year_match:
                     details['year'] = int(year_match.group(1))
                     logging.debug(f"    年(メタ情報から取得): {details['year']}")

            # 時間 (XXX分)
            runtime_match = re.search(r'(\d+)分', full_text)
            if runtime_match:
                details['runtime'] = int(runtime_match.group(1))
                logging.debug(f"    時間(メタ情報から取得): {details['runtime']}")

            # 国 (製作国：の後のテキスト、または正規表現以外で抽出)
            # 再度国を抽出し直す (ulから取得する方が確実)
            country_list = []
            country_h3 = other_info_div.find('h3', string=lambda t: t and "製作国" in t)
            if country_h3:
                country_ul = country_h3.find_next_sibling('ul')
                if country_ul:
                    country_list = [a.get_text(strip=True) for a in country_ul.select('li > a')]
                    if country_list:
                        details['country'] = " / ".join(country_list)
                        logging.debug(f"    国(リストから取得): {details['country']}")

        logging.debug(f"    年:{details['year']}, 国:{details['country']}, 時間:{details['runtime']}")

        # あらすじ (JSON-LD -> content-detail-synopsis の順で試行)
        summary_text = None
        try:
            json_ld_script = soup.find('script', type='application/ld+json')
            if json_ld_script:
                json_data = json.loads(json_ld_script.string)
                if isinstance(json_data, list): # リストの場合、最初の要素を試す
                    json_data = json_data[0]
                if json_data.get('@type') == 'Movie' and json_data.get('outline'):
                    summary_text = json_data['outline']
                    logging.debug("    あらすじ(JSON-LDから取得)")
        except Exception as e:
            logging.warning(f"    JSON-LDの解析中にエラー: {e}")

        if not summary_text:
            synopsis_tag = soup.select_one('div.p-content-detail__synopsis content-detail-synopsis')
            if synopsis_tag and synopsis_tag.get('outline'):
                 summary_text = synopsis_tag['outline']
                 logging.debug("    あらすじ(content-detail-synopsisタグのoutline属性から取得)")
            elif synopsis_tag : # フォールバックとしてタグ内のテキスト取得を試みる (ほぼ無い想定)
                 summary_text = synopsis_tag.get_text(" ", strip=True)
                 logging.debug("    あらすじ(content-detail-synopsisタグのテキストから取得)")

        if summary_text:
            details['summary'] = summary_text[:300] + ('...' if len(summary_text) > 300 else '')
            logging.debug(f"    あらすじ取得 (先頭): {details['summary'][:50]}...")
        else:
            logging.debug("    あらすじが見つかりませんでした。")


        # 監督・キャスト・スタッフ・配給など (div.p-content-detail__people-list などから)
        people_section = soup.select_one('div.p-content-detail__people-list')
        if people_section:
             directors = []
             full_staff_dict = {}
             full_cast_list = []
             main_cast_strings = []

             # 監督
             # director_section = people_section.select_one('div.p-content-detail__people-list-others-inner:-soup-contains("監督")') # 擬似クラスは使えない
             director_heading = people_section.find('h3', class_='p-content-detail__people-list-term', string='監督')
             if director_heading:
                 director_parent_div = director_heading.parent
                 director_list_ul = director_parent_div.find('ul')
                 if director_list_ul:
                     names = [a_div.get_text(strip=True) for a_div in director_list_ul.select('li a div.c2-button-tertiary-s__text')]
                     if names:
                         directors = names
                         full_staff_dict['監督'] = [{"name": n, "role": ""} for n in names]

             # キャスト (出演者)
             # cast_section = people_section.select_one('div.p-people-list#js-content-detail-people-cast') # ID指定でも良い
             cast_heading = people_section.find('h3', class_='p-content-detail__people-list-term', string='出演者')
             if cast_heading:
                  cast_items = cast_heading.find_next_siblings('h4', class_='p-people-list__item')
                  for item in cast_items:
                      name_tag = item.select_one('a div.c2-button-tertiary-s-multi-text__text')
                      role_tag = item.select_one('a div.c2-button-tertiary-s-multi-text__subtext')
                      actor_name = name_tag.get_text(strip=True) if name_tag else None
                      role_name = role_tag.get_text(strip=True) if role_tag else None
                      if actor_name:
                          cast_info = {"name": actor_name, "role": role_name}
                          full_cast_list.append(cast_info)
                          if len(main_cast_strings) < 4: # 主要キャストは4名まで
                              display_text = actor_name
                              if role_name: display_text += f" ({role_name})"
                              main_cast_strings.append(display_text)

             if full_staff_dict: details['full_staff'] = full_staff_dict
             if directors: details['director'] = ", ".join(directors)
             if full_cast_list: details['full_cast'] = full_cast_list
             if main_cast_strings: details['cast'] = ", ".join(main_cast_strings)
             logging.debug(f"    監督: {details['director']}")
             logging.debug(f"    キャスト (主要): {details['cast']}")

        # 配給 (div.p-content-detail__genre 内から)
        genre_div = soup.select_one('div.p-content-detail__genre')
        if genre_div:
            distributor_heading = genre_div.find('h3', string=lambda t: t and "配給" in t)
            if distributor_heading:
                 distributor_ul = distributor_heading.find_next_sibling('ul')
                 if distributor_ul:
                     dist_names = [a.get_text(strip=True) for a in distributor_ul.select('li > a')]
                     if dist_names:
                         details['distributor'] = ", ".join(dist_names)
                         logging.debug(f"    配給: {details['distributor']}")

        # レビュー情報 (スコアと件数)
        reviews_dict = {}
        # スコア
        score_tag = soup.select_one('div.p-content-detail-state div.c2-rating-l__text') # 修正
        if score_tag:
             try:
                 score_text = score_tag.get_text(strip=True)
                 if score_text and score_text != '-': # スコア未登録の場合'-'が入る
                    reviews_dict['average_score'] = float(score_text)
             except ValueError:
                 logging.warning(f"    レビュースコアの取得または変換に失敗: {score_tag.get_text(strip=True)}")
        # 件数
        count_tag = soup.select_one('div.p-mark-histogram__top__total-count') # 修正
        if count_tag:
             count_text = count_tag.get_text(strip=True)
             count_match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)', count_text) # カンマ区切り対応
             if count_match:
                 try:
                     reviews_dict['review_count'] = int(count_match.group(1).replace(',', ''))
                 except ValueError:
                      logging.warning(f"    レビュー件数の変換に失敗: {count_match.group(1)}")

        if reviews_dict:
            details['reviews'] = reviews_dict
            logging.debug(f"    レビュー概要: {details['reviews']}")

        return details

    except requests.exceptions.Timeout:
        logging.error(f"[Filmarks] 詳細取得タイムアウト: {movie_page_url}")
        return details
    except requests.exceptions.RequestException as e:
        logging.error(f"[Filmarks] 詳細取得リクエストエラー ({movie_page_url}): {e}")
        return details
    except Exception as e:
        logging.error(f"[Filmarks] 詳細取得処理中の予期せぬエラー ({movie_page_url}): {e}")
        return details 