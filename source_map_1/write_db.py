#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
資料庫寫入工具 - 根據 JSON 檔案執行 HTTP 請求寫入資料庫
讀取 water_stations_sync_requests.json 檔案並執行其中的 PATCH/POST 請求
"""

import json
import requests
import time
import sys
import os
from typing import List, Dict, Any, Optional


class DatabaseWriter:
    """資料庫寫入器 - 執行 HTTP 請求更新資料庫"""

    def __init__(self, delay_seconds: float = 0.5):
        self.delay_seconds = delay_seconds
        self.success_count = 0
        self.error_count = 0
        self.skipped_count = 0
        self.results = []

    def execute_request(self, request_data: Dict[str, Any]) -> bool:
        """執行單個 HTTP 請求"""
        method = request_data.get('http_method', '').upper()
        url = request_data.get('url', '')
        body = request_data.get('request_body', {})
        name = request_data.get('name', 'Unknown')
        action = request_data.get('action', 'unknown')

        if not method or not url:
            print(f"❌ 無效請求資料: {name}")
            return False

        x_api_key = os.getenv('X_API_KEY')
        if not x_api_key:
            print("    ⚠️  未設定 X_API_KEY 環境變數，跳過 API 執行")
            return None

        try:
            print(f"🔄 執行 {method} 請求: {name}")
            print(f"body = {json.dumps(body)}")

            if method == 'PATCH':
                response = requests.patch(url, json=body, headers={"x-api-key": x_api_key}, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=body, timeout=30)
            else:
                print(f"❌ 不支援的 HTTP 方法: {method}")
                return False

            response.raise_for_status()
            print(f"✅ {action} 成功: {name}")

            # 記錄成功結果
            result = {
                'name': name,
                'action': action,
                'method': method,
                'status': 'success',
                'status_code': response.status_code
            }

            # 如果是 POST 請求，記錄創建的 ID
            if method == 'POST':
                try:
                    response_data = response.json()
                    if 'id' in response_data:
                        result['created_id'] = response_data['id']
                except:
                    pass

            self.results.append(result)
            return True

        except requests.exceptions.RequestException as e:
            print(f"❌ {action} 失敗: {name}")
            self._log_api_error(method, url, body, e, getattr(e, 'response', None))

            # 記錄失敗結果
            self.results.append({
                'name': name,
                'action': action,
                'method': method,
                'status': 'error',
                'error': str(e)
            })
            return False

    def _log_api_error(self, method: str, url: str, request_data: Dict[str, Any],
                      exception: Exception, response=None):
        """記錄 API 請求錯誤的詳細資訊"""
        print(f"  ❌ API 請求失敗:")
        print(f"     方法: {method}")
        print(f"     URL: {url}")
        print(f"     錯誤: {exception}")

        if response is not None:
            print(f"     響應狀態碼: {response.status_code}")
            try:
                response_text = response.text
                if response_text:
                    print(f"     響應內容: {response_text}")
                else:
                    print(f"     響應內容: (空)")
            except Exception as e:
                print(f"     無法讀取響應內容: {e}")
        else:
            print(f"     響應: 無響應 (連接錯誤或超時)")

    def process_json_file(self, json_file: str, confirm_before_execute: bool = True):
        """處理 JSON 檔案中的所有請求"""
        print(f"📂 讀取請求檔案: {json_file}")

        try:
            with open(json_file, 'r', encoding='utf-8') as file:
                requests_data = json.load(file)
        except FileNotFoundError:
            print(f"❌ 檔案不存在: {json_file}")
            return
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析錯誤: {e}")
            return
        except Exception as e:
            print(f"❌ 讀取檔案錯誤: {e}")
            return

        if not isinstance(requests_data, list):
            print("❌ JSON 檔案格式錯誤：應該是請求物件的陣列")
            return

        total_requests = len(requests_data)
        if total_requests == 0:
            print("ℹ️  沒有找到任何請求")
            return

        print(f"📊 總共找到 {total_requests} 個請求")
        print("=" * 50)

        # 統計請求類型
        patch_count = sum(1 for req in requests_data if req.get('http_method') == 'PATCH')
        post_count = sum(1 for req in requests_data if req.get('http_method') == 'POST')

        print(f"🔄 PATCH 請求: {patch_count} 個")
        print(f"🆕 POST 請求: {post_count} 個")
        print(f"⏱️  每次請求間隔: {self.delay_seconds} 秒")

        # 確認是否執行
        if confirm_before_execute:
            print("\n⚠️  即將執行以上請求，這將會修改資料庫內容！")
            confirmation = input("確定要繼續嗎？ (yes/y 確認，其他任何輸入取消): ").lower().strip()
            if confirmation not in ['yes', 'y']:
                print("❌ 用戶取消操作")
                return

        print("\n🚀 開始執行請求...")
        print("=" * 50)

        # 執行所有請求
        for i, request_data in enumerate(requests_data, 1):
            print(f"\n[{i}/{total_requests}]", end=" ")

            if self.execute_request(request_data):
                self.success_count += 1
            else:
                self.error_count += 1

            # 添加延遲避免觸及 API 限制 (除了最後一個請求)
            if i < total_requests:
                time.sleep(self.delay_seconds)

    def save_results(self, output_file: str = "write_db_results.json"):
        """保存執行結果到 JSON 檔案"""
        if not self.results:
            print("ℹ️  沒有結果可以儲存")
            return

        try:
            with open(output_file, 'w', encoding='utf-8') as file:
                json.dump(self.results, file, ensure_ascii=False, indent=2)
            print(f"\n💾 執行結果已儲存到: {output_file}")
        except Exception as e:
            print(f"❌ 儲存結果檔案錯誤: {e}")

    def show_summary(self):
        """顯示執行結果摘要"""
        total_processed = self.success_count + self.error_count + self.skipped_count

        print("\n" + "=" * 50)
        print("📊 執行結果摘要:")
        print(f"✅ 成功執行: {self.success_count} 個")
        print(f"❌ 執行失敗: {self.error_count} 個")
        print(f"⚠️  跳過處理: {self.skipped_count} 個")
        print(f"🎯 總計處理: {total_processed} 個")

        if self.success_count > 0:
            success_rate = (self.success_count / total_processed) * 100
            print(f"🏆 成功率: {success_rate:.1f}%")


def main():
    print("🗃️  資料庫寫入工具")
    print("=" * 50)

    # 檢查命令列參數
    json_file = sys.argv[1] if len(sys.argv) > 1 else "water_stations_sync_requests.json"
    confirm = True

    # 檢查是否有 --no-confirm 參數
    if len(sys.argv) > 2 and sys.argv[2] == "--no-confirm":
        confirm = False

    try:
        # 創建資料庫寫入器
        writer = DatabaseWriter(delay_seconds=0.5)

        # 處理 JSON 檔案
        writer.process_json_file(json_file, confirm_before_execute=confirm)

        # 顯示摘要
        writer.show_summary()

        # 保存結果
        writer.save_results()

    except KeyboardInterrupt:
        print("\n⚠️  用戶中斷操作")
        if 'writer' in locals():
            writer.show_summary()
    except Exception as e:
        print(f"❌ 發生未預期的錯誤: {e}")


if __name__ == "__main__":
    main()