# Yahoo! Eiga Scraper

# TODO: Implement Yahoo! Eiga specific search and scrape functions here 

import requests
from bs4 import BeautifulSoup
import re
import logging
import os
from urllib.parse import quote # URLエンコード用

# User-Agent設定 (映画.comと同じものを使用)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

def search_yahoo_eiga(title):
    """Yahoo!映画で映画タイトルを検索し、最上位の作品ページのURLを取得する (推測)"""
    search_query = quote(title)
    search_url = f"https://movies.yahoo.co.jp/search/?q={search_query}"
    try:
        logging.info(f"[Yahoo!映画] 検索中: {title} (URL: {search_url})")
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # --- !! 推測セレクタ !! ---
        # 検索結果リストから最初の映画へのリンクを探す
        # 例: <div class="rsltlst"> <ul> <li> <a href="/movie/...">...</a></li></ul></div>
        # または <section class="ResultList"> <div class="ResultList_item"> <a href="/movie/...">...</a></div></section>
        result_link = soup.select_one('div.ResultList__itemBody a[href^="/movie/"], section.ResultList .ResultList_item a[href^="/movie/"]') # より具体的に絞り込み

        if result_link and result_link.get('href'):
            # 相対URLを絶対URLに変換
            movie_page_url = "https://movies.yahoo.co.jp" + result_link['href']
            logging.info(f"  [Yahoo!映画] 作品ページURL発見: {movie_page_url}")
            return movie_page_url
        else:
            logging.warning(f"  [Yahoo!映画] 検索結果で作品ページが見つかりませんでした: {title}")
            return None
    except requests.exceptions.Timeout:
        logging.error(f"[Yahoo!映画] 検索タイムアウト: {title} ({search_url})")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"[Yahoo!映画] 検索リクエストエラー ({title}): {e}")
        return None
    except Exception as e:
        logging.error(f"[Yahoo!映画] 検索処理中の予期せぬエラー ({title}): {e}")
        return None

def scrape_movie_details(movie_page_url, debug_mode=False):
    """Yahoo!映画ページのURLから詳細情報を標準化された辞書形式で取得する (推測)"""
    details = {
        'source': 'yahoo.co.jp', # 情報源
        'year': None, 'director': None, 'summary': None, 'cast': None,
        'producer': None, 'cinematographer': None, 'country': None,
        'runtime': None, 'distributor': None, 'full_staff': None,
        'full_cast': None, 'reviews': None
    }
    if not movie_page_url or not movie_page_url.startswith("https://movies.yahoo.co.jp"):
        logging.warning(f"無効なURLのためスキップ: {movie_page_url}")
        return details

    try:
        logging.info(f"[Yahoo!映画] 詳細情報取得中: {movie_page_url}")
        response = requests.get(movie_page_url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        # --- デバッグ用HTML保存 ---
        if debug_mode:
            try:
                debug_filename = "_debug_last_scraped_page_yahoo.html"
                with open(debug_filename, "wb") as f:
                    f.write(response.content)
                logging.debug(f"  [Yahoo!映画] デバッグ用にHTMLを '{debug_filename}' に保存しました。")
            except Exception as e:
                logging.warning(f"  [Yahoo!映画] デバッグ用HTMLファイルの保存中にエラー: {e}")
        # --- デバッグ用ここまで ---

        soup = BeautifulSoup(response.content, 'html.parser')

        # --- !! 各種情報抽出 (推測セレクタ) !! ---

        # タイトル (h1などから取得確認用)
        title_tag = soup.select_one('title') # <title>タグから取得試行
        page_title = title_tag.text.strip() if title_tag else "[タイトル不明]"
        logging.debug(f"  ページタイトル: {page_title}")

        # 基本情報ブロック (公開年、国、時間など)
        # 例: <p class="basicInfo"><span>YYYY年公開</span> / <span>国名</span> / <span>XX分</span></p>
        # または <dl class="spec"><dt>公開</dt><dd>YYYY年</dd>...</dl>
        basic_info_text = ""
        spec_dl = soup.select_one('dl.spec, section[data-test=detail-spec] dl') # 推測
        if spec_dl:
             dds = spec_dl.find_all('dd')
             if len(dds) > 0 : basic_info_text = " / ".join(dd.get_text(" ", strip=True) for dd in dds)
             logging.debug(f"  スペック情報テキスト(dl): {basic_info_text}")

             # dl形式の場合、個別に取得試行
             dt_map = {dt.get_text(strip=True): dt.find_next_sibling('dd') for dt in spec_dl.find_all('dt')}
             if '公開' in dt_map and dt_map['公開']:
                 year_match = re.search(r'(\d{4})', dt_map['公開'].text)
                 if year_match: details['year'] = int(year_match.group(1))
             if '上映時間' in dt_map and dt_map['上映時間']:
                 runtime_match = re.search(r'(\d+)', dt_map['上映時間'].text)
                 if runtime_match: details['runtime'] = int(runtime_match.group(1))
             if '製作国' in dt_map and dt_map['製作国']:
                 details['country'] = dt_map['製作国'].get_text(" ", strip=True)
             if '配給' in dt_map and dt_map['配給']:
                 details['distributor'] = dt_map['配給'].get_text(" ", strip=True)

        else: # dl がない場合、pタグを探す
            basic_info_tag = soup.select_one('p.basicInfo, .Header__info') # 推測
            if basic_info_tag:
                basic_info_text = basic_info_tag.get_text(separator=" / ", strip=True)
                logging.debug(f"  基本情報テキスト(p): {basic_info_text}")

                # 年 (YYYY年公開 または YYYY)
                year_match = re.search(r'(\d{4})', basic_info_text) # YYYY年 or YYYY
                if year_match: details['year'] = int(year_match.group(1))

                # 時間 (XX分)
                runtime_match = re.search(r'(\d+)分', basic_info_text)
                if runtime_match: details['runtime'] = int(runtime_match.group(1))

                # 国 (パターンが難しいので暫定的に / で区切られた真ん中あたり？)
                parts = [p.strip() for p in basic_info_text.split('/') if p.strip() and not re.search(r'\d', p)]
                if len(parts) > 0: details['country'] = parts[0] # 最初の非数値要素を国と仮定

        logging.debug(f"    年:{details['year']}, 国:{details['country']}, 時間:{details['runtime']}, 配給:{details['distributor']}")

        # スタッフ情報
        # 例: <section id="staff"> <dl><dt>監督</dt><dd><a>名前</a></dd>...</dl> </section>
        staff_section = soup.select_one('section#staff, section[data-test=detail-staff]') # 推測
        if staff_section:
            full_staff_dict = {}
            directors = []
            producers = []
            cinematographers = []
            dts = staff_section.select('dt')
            for dt in dts:
                role = dt.get_text(strip=True)
                dd = dt.find_next_sibling('dd')
                if role and dd:
                    names = [a.get_text(strip=True) for a in dd.select('a')]
                    if not names: names = [dd.get_text(" ", strip=True)] # aタグがない場合

                    if names:
                         full_staff_dict[role] = [{"name": n, "role": ""} for n in names]
                         if role == '監督': directors.extend(names)
                         elif role in ['製作', 'プロデューサー', '製作総指揮']: producers.extend(names)
                         elif role == '撮影': cinematographers.extend(names)

            if full_staff_dict: details['full_staff'] = full_staff_dict
            if directors: details['director'] = ", ".join(directors)
            if producers: details['producer'] = ", ".join(sorted(list(set(producers))))
            if cinematographers: details['cinematographer'] = ", ".join(cinematographers)
            logging.debug(f"    監督: {details['director']}, P: {details['producer']}, 撮影: {details['cinematographer']}")
            logging.debug(f"    全スタッフ (一部): {str(details['full_staff'])[:100]}...")

        # あらすじ
        # 例: <section id="story"><p>...</p></section> または <p class="text" data-test="story">...</p>
        story_tag = soup.select_one('section#story p, p[data-test=story], div.Story__content') # 推測
        if story_tag:
            summary_text = story_tag.get_text(" ", strip=True)
            details['summary'] = summary_text[:300] + ('...' if len(summary_text) > 300 else '')
            logging.debug(f"    あらすじ取得 (先頭): {details['summary'][:50]}...")

        # キャスト情報
        # 例: <section id="cast"> <ul><li><p class="name"><a>俳優名</a></p><p class="role">役名</p></li></ul></section>
        cast_section = soup.select_one('section#cast, section[data-test=detail-cast]') # 推測
        if cast_section:
            full_cast_list = []
            main_cast_strings = []
            # <li> またはそれに類する要素を探す
            cast_items = cast_section.select('li, div.Cast__item') # 推測
            for item in cast_items:
                # 名前と役名を探すセレクタ (推測)
                name_tag = item.select_one('.name a, .Cast__name, p a')
                role_tag = item.select_one('.role, .Cast__role, p + p') # 名前の次に来る要素を仮定

                actor_name = name_tag.get_text(strip=True) if name_tag else None
                role_name = role_tag.get_text(strip=True) if role_tag else None

                if actor_name:
                    cast_info = {"name": actor_name, "role": role_name}
                    full_cast_list.append(cast_info)
                    if len(main_cast_strings) < 4:
                        display_text = actor_name
                        if role_name: display_text += f" ({role_name})"
                        main_cast_strings.append(display_text)

            if full_cast_list: details['full_cast'] = full_cast_list
            if main_cast_strings: details['cast'] = ", ".join(main_cast_strings)
            logging.debug(f"    キャスト (主要): {details['cast']}")
            logging.debug(f"    全キャスト (一部): {str(details['full_cast'])[:100]}...")

        # レビュー情報 (スコアと件数)
        # 例: <span class="ratingValue">4.1</span> <span class="reviewCount">(123件)</span>
        review_section = soup.select_one('.Review__average, section[data-test=detail-review-score]') # 推測
        if review_section:
            reviews_dict = {}
            score_tag = review_section.select_one('.Rating__value, .Score__value') # 推測
            count_tag = review_section.select_one('.Review__count, .Score__text em') # 推測
            if score_tag:
                 try: reviews_dict['average_score'] = float(score_tag.text.strip())
                 except ValueError: pass
            if count_tag:
                 count_match = re.search(r'(\d+)', count_tag.text.replace(',','')) # カンマ除去
                 if count_match: reviews_dict['review_count'] = int(count_match.group(1))

            if reviews_dict:
                details['reviews'] = reviews_dict
                logging.debug(f"    レビュー概要: {details['reviews']}")

        return details

    except requests.exceptions.Timeout:
        logging.error(f"[Yahoo!映画] 詳細取得タイムアウト: {movie_page_url}")
        return details
    except requests.exceptions.RequestException as e:
        logging.error(f"[Yahoo!映画] 詳細取得リクエストエラー ({movie_page_url}): {e}")
        return details
    except Exception as e:
        logging.error(f"[Yahoo!映画] 詳細取得処理中の予期せぬエラー ({movie_page_url}): {e}")
        return details 