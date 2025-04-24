# Movie Scraper Utilities
import pandas as pd
import logging
import sys
import json
import os
import argparse
from datetime import datetime

# --- 定数 ---
DEFAULT_OUTPUT_COLUMNS = [
    'movie_id', 'title', 'year', 'director', 'summary', 'cast',
    'producer', 'cinematographer', 'country', 'runtime', 'distributor',
    'full_staff', 'full_cast', 'reviews'
]

# --- ロギング設定 ---
def setup_logging(log_level_str='INFO'):
    """基本的なロギング設定を行う"""
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)

# --- ファイル I/O ---
def load_csv(filepath):
    """指定されたパスからShift_JISエンコーディングでCSVファイルを読み込む"""
    try:
        logging.info(f"CSVファイルを読み込み中: {filepath}")
        # dtype={'movie_id': str} を追加して movie_id を文字列として読み込むことを保証する
        df = pd.read_csv(filepath, encoding='shift_jis', dtype={'movie_id': str})
        logging.info("CSVファイルの読み込み完了")
        return df
    except FileNotFoundError:
        logging.error(f"エラー: ファイルが見つかりません: {filepath}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"CSVファイルの読み込み中にエラーが発生しました: {e}")
        sys.exit(1)

def save_csv(df, filepath):
    """DataFrameをShift_JISエンコーディングでCSVファイルに保存する"""
    try:
        logging.info(f"更新されたCSVファイルを保存中: {filepath}")
        # Shift_JISでエンコードできない文字は '?' に置換する
        df.to_csv(filepath, encoding='shift_jis', index=False, errors='replace')
        logging.info("CSVファイルの保存完了")
    except Exception as e:
        logging.error(f"CSVファイルの保存中にエラーが発生しました: {e}")
        sys.exit(1)

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
        if not isinstance(data, list):
            logging.error(f"エラー: JSONファイルの内容が期待される形式 (リスト) ではありません: {filepath}")
            return None
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

def save_json(data, filepath):
    """データをUTF-8エンコーディングでJSONファイルに保存する"""
    try:
        logging.info(f"データをJSONファイルに保存中: {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logging.info(f"データを '{filepath}' に保存しました。")
    except Exception as e:
        logging.error(f"JSONファイル '{filepath}' の保存中にエラーが発生しました: {e}")

# --- DataFrame 操作 ---
def check_and_add_columns(df, required_columns):
    """DataFrameに必要な列が存在するか確認し、なければNaNで追加する。"""
    added_cols = []
    for col in required_columns:
        if col not in df.columns:
            df[col] = pd.NA # または np.nan
            added_cols.append(col)
    if added_cols:
        logging.info(f"以下の列をNaNで追加しました: {added_cols}")

    # --- FutureWarning対策: 主要な出力列の dtype を object に設定 --- 
    # (movie_id は load_csv で str に変換される想定)
    # (year, runtime は後で数値に変換されるため、ここでは object のままで良い)
    cols_to_object = [col for col in DEFAULT_OUTPUT_COLUMNS if col != 'movie_id']
    try:
        for col in cols_to_object:
            if col in df.columns and df[col].dtype != 'object':
                 # すでに object 型でなければ変換 (NaN を含む場合は object が適切)
                 # Int64 や Float64 など数値型になっている場合がある
                 df[col] = df[col].astype('object')
        logging.debug(f"列 {cols_to_object} の dtype を object に設定しました (FutureWarning対策)")
    except Exception as e:
        logging.warning(f"列の dtype 変換中にエラーが発生しました: {e}")
    # --- ここまで追加 ---

    return df

def reorder_columns(df, column_order):
    """DataFrameの列を指定された順序に並び替える"""
    existing_cols_in_order = [col for col in column_order if col in df.columns]
    other_cols = [col for col in df.columns if col not in column_order]
    # 元のDataFrameに存在しない列がcolumn_orderに含まれていてもエラーにならないようにする
    final_order = existing_cols_in_order + other_cols
    return df[final_order]

def update_dataframe_from_json(df, json_data):
    """JSONデータリストを使ってDataFrameを更新する"""
    update_count = 0
    if not json_data:
        logging.warning("JSONデータが空のため、DataFrameの更新は行われません。")
        return df.copy() # 変更がない場合もコピーを返す

    logging.info(f"JSONデータ ({len(json_data)} 件) を使用してDataFrameを更新します...")

    df_updated = df.copy() # 元のDataFrameを変更しない

    # movie_idをインデックスにして高速化
    # インデックスにする前に movie_id が存在することを確認
    if 'movie_id' not in df_updated.columns:
        logging.error("DataFrameに 'movie_id' 列が存在しないため、JSONからの更新処理を中断します。")
        return df_updated

    # movie_id を文字列に変換してからインデックスに設定
    df_updated['movie_id'] = df_updated['movie_id'].astype(str)
    df_indexed = df_updated.set_index('movie_id')
    original_columns = df_updated.columns # インデックス設定後の列リスト

    for details in json_data:
        if not isinstance(details, dict):
            logging.warning(f"JSONデータ内の無効な要素をスキップしました: {details}")
            continue

        movie_id = details.get('movie_id')
        movie_id_str = str(movie_id) if movie_id is not None else None
        title = details.get('title', '[タイトル不明]')

        if movie_id_str is None:
            logging.warning(f"movie_id が見つからないため、JSONデータ内の要素をスキップしました: {title}")
            continue

        logging.debug(f"--- JSONデータ処理開始: {title} (ID: {movie_id_str}) ---") # デバッグレベルに変更

        if movie_id_str in df_indexed.index:
            updated_this_iteration = False
            update_log_messages = []

            # 更新対象の列リスト (movie_id, titleを除く、かつDataFrameに存在する列のみ)
            columns_to_update = [
                col for col in DEFAULT_OUTPUT_COLUMNS
                if col in df_indexed.columns and col not in ['movie_id', 'title']
            ]

            for col in columns_to_update:
                # DataFrameの値が欠損しており、かつJSONデータにそのキーと値が存在する場合に更新
                if pd.isna(df_indexed.loc[movie_id_str, col]) and details.get(col) is not None:
                    value_to_update = details[col]
                    log_message = f"{col}"

                    try:
                        # JSON文字列として保存する列
                        if col in ['full_staff', 'full_cast', 'reviews']:
                            if isinstance(value_to_update, (list, dict)):
                                df_indexed.loc[movie_id_str, col] = json.dumps(value_to_update, ensure_ascii=False)
                                log_message += "(JSON)"
                            else:
                                logging.warning(f"  -> [{movie_id_str}:{title}] {col} の値が予期しない型 ({type(value_to_update)}) のためスキップ: {str(value_to_update)[:50]}...")
                                continue
                        # 数値型に変換する列
                        elif col in ['year', 'runtime']:
                            numeric_value = pd.to_numeric(value_to_update, errors='coerce')
                            if pd.notna(numeric_value):
                                # Int64 に変換しようと試みるが、対象列がなければastypeでエラーになる可能性
                                # loc で直接 int を代入するのが安全か
                                df_indexed.loc[movie_id_str, col] = int(numeric_value)
                                log_message += f":{int(numeric_value)}"
                            else:
                                df_indexed.loc[movie_id_str, col] = pd.NA
                                log_message += ": [変換失敗]"
                        # その他の文字列等
                        else:
                            df_indexed.loc[movie_id_str, col] = str(value_to_update)
                            display_value = str(value_to_update)
                            if len(display_value) > 30:
                                display_value = display_value[:27] + "..."
                            log_message += f":{display_value}"

                        updated_this_iteration = True
                        update_log_messages.append(log_message)

                    except Exception as e:
                         logging.warning(f"  -> [{movie_id_str}:{title}] {col} の更新中に予期せぬエラー: {e} (値: {str(value_to_update)[:50]}...)")
                         continue

            if updated_this_iteration:
                logging.info(f"  -> [{movie_id_str}:{title}] DataFrame更新: {', '.join(update_log_messages)}")
                update_count += 1
            else:
                logging.debug(f"  -> [{movie_id_str}:{title}] 更新対象の情報が見つからないか、既に値が存在するため、DataFrameは更新されませんでした。")

        else:
            logging.warning(f"元のDataFrameに movie_id = {movie_id_str} が見つかりません。JSONデータをスキップします。")

        logging.debug(f"--- JSONデータ処理完了: {title} (ID: {movie_id_str}) ---")

    logging.info(f"JSONデータから合計 {update_count} 回のデータ更新を行いました。")
    # インデックスをリセットして元のDataFrameと同じ列順序に戻す
    df_final = df_indexed.reset_index()
    # 元のDataFrameに存在した列のみを、元の順序で返す
    final_columns = [col for col in df.columns if col in df_final.columns]
    return df_final[final_columns]


# --- 引数パーサー ---
def setup_common_parser(description="映画の詳細情報を取得・更新するスクリプト"):
    """共通のコマンドライン引数を設定するパーサーを作成する"""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--input', required=True, help='入力CSVファイルのパス (Shift_JIS)')
    parser.add_argument('--output', required=True, help='出力CSVファイルのパス (Shift_JIS)')
    parser.add_argument('--json-input', default=None, help='Web検索の代わりに読み込むJSONファイルのパス (UTF-8)')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], help='ログレベル (デフォルト: INFO)')
    # --debug フラグは main 側で解釈して log-level を上書きする方がシンプル
    parser.add_argument('--debug', action='store_true', help='デバッグモード (ログレベルをDEBUGに設定)')

    return parser 