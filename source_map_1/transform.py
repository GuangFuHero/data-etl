#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL 工具 - 從 placemarks.csv 處理各種資料源
輸入: placemarks.csv, API 端點
輸出: water_stations_source.csv, water_stations_db.csv, medical_stations_source.csv, medical_stations_db.csv, restrooms_source.csv, restrooms_db.csv
依賴: pip install requests
"""

import csv
import pandas as pd
from typing import List, Dict, Any, Optional
import requests
import json
import sys
import os


class PlacemarksCSVReader:
    """從 placemarks.csv 讀取資料"""

    def __init__(self):
        self.placemarks = []

    def read_from_csv(self, csv_file: str) -> List[Dict[str, Any]]:
        """從 CSV 檔案讀取 Placemark 資料"""
        self.placemarks = []
        try:
            df = pd.read_csv(csv_file)
            self.placemarks = df.to_dict('records')
            print(f"✅ 成功讀取 {len(self.placemarks)} 筆 Placemark 資料從 {csv_file}")
        except (FileNotFoundError, pd.errors.EmptyDataError) as e:
            print(f"❌ 檔案錯誤: {e}")
            return []
        return self.placemarks

    def show_summary(self, placemarks: Optional[List[Dict[str, Any]]] = None):
        data_to_show = placemarks if placemarks is not None else self.placemarks
        if not data_to_show:
            print("❌ 沒有找到任何 Placemark 資料")
            return
        total_count = len(data_to_show)
        with_coords = sum(1 for p in data_to_show if pd.notna(p.get('latitude')) and pd.notna(p.get('longitude')))
        without_coords = total_count - with_coords
        print(f"\n📊 處理結果摘要:")
        print(f"總共找到: {total_count} 個 Placemark")
        print(f"有座標: {with_coords} 個")
        print(f"無座標: {without_coords} 個")
        if without_coords > 0:
            print(f"\n⚠️  以下 {without_coords} 個 Placemark 沒有座標:")
            for i, placemark in enumerate(data_to_show, 1):
                if pd.isna(placemark.get('latitude')) or pd.isna(placemark.get('longitude')):
                    print(f"  {i}. {placemark.get('name', 'N/A')}")

    def get_placemarks(self) -> List[Dict[str, Any]]:
        return self.placemarks


class ProcessorUtils:
    """共用處理器工具類別 - 提供各種處理器的共用功能"""

    @staticmethod
    def fetch_api_data(api_url: str, resource_type: str = "資源") -> List[Dict[str, Any]]:
        """從 API 撷取資料的共用方法"""
        try:
            print(f"🔄 正在從 API 撷取 {resource_type} 資料: {api_url}")
            
            all_resources = []
            offset = 0
            limit = 50
            
            while True:
                # 使用 params 參數構建請求
                params = {"limit": limit, "offset": offset}
                print(f"🔄 正在撷取 {resource_type} 資料 (offset: {offset})")
                
                response = requests.get(api_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                # 提取資料
                if 'member' in data:
                    batch_data = data['member']
                elif isinstance(data, list):
                    batch_data = data
                else:
                    batch_data = [data]
                
                all_resources.extend(batch_data)  # 使用 extend 而不是 append
                print(f"✅ 成功撷取 {len(batch_data)} 筆 {resource_type} 資料 (總計: {len(all_resources)})")
                
                # 檢查是否還有更多資料
                if 'totalItems' not in data or offset + limit >= data['totalItems']:
                    break
                
                offset += limit
            
            print(f"🎉 完成撷取，共 {len(all_resources)} 筆 {resource_type} 資料")
            return all_resources
            
        except requests.exceptions.RequestException as e:
            print(f"❌ API 請求錯誤: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析錯誤: {e}")
            return []
        except KeyError as e:
            print(f"❌ 資料格式錯誤，缺少必要欄位: {e}")
            return []
        except Exception as e:
            print(f"❌ 未預期的錯誤: {e}")
            return []

    @staticmethod
    def extract_placemarks_by_filter(csv_reader: PlacemarksCSVReader, folder_match: str, name_contains: str) -> List[Dict[str, Any]]:
        """根據 folder 和 name 篩選條件提取 placemarks"""
        if not csv_reader:
            return []

        filtered_placemarks = []
        for placemark in csv_reader.get_placemarks():
            folder = placemark.get('folder', '')
            name = placemark.get('name', '')
            if folder == folder_match or name_contains in name:
                filtered_placemarks.append(placemark)
        return filtered_placemarks

    @staticmethod
    def convert_placemarks_to_stations(placemarks: List[Dict[str, Any]], resource_type: str = "站點") -> List[Dict[str, Any]]:
        """將 placemarks 轉換為標準站點格式"""
        stations = []
        for placemark in placemarks:
            latitude = placemark.get('latitude')
            longitude = placemark.get('longitude')

            # 檢查座標是否為 NaN 或 None
            if pd.isna(latitude) or pd.isna(longitude) or latitude is None or longitude is None:
                print(f"⚠️  跳過無座標的{resource_type}: {placemark.get('name', 'N/A')}")
                continue
            # 處理 notes 欄位，將 NaN 轉換為空字串
            description = placemark.get('description', '')
            if pd.isna(description) or description == 'nan':
                description = ''

            station = {
                "name": placemark.get('name', ''),
                "notes": description,
                "info_source": "地圖一",
                "coordinates": {"lat": float(latitude), "lng": float(longitude)}
            }
            stations.append(station)
        return stations

    @staticmethod
    def save_json_requests(http_requests: List[Dict[str, Any]], output_file: str) -> bool:
        """保存 HTTP 請求到 JSON 檔案"""
        try:
            with open(output_file, 'w', encoding='utf-8') as jsonfile:
                json.dump(http_requests, jsonfile, ensure_ascii=False, indent=2)

            if http_requests:
                print(f"✅ 成功儲存 {len(http_requests)} 個 HTTP 請求到 {output_file}")
            else:
                print(f"✅ 成功儲存空的請求清單到 {output_file}")
            return True
        except IOError as e:
            print(f"❌ 儲存請求檔案錯誤: {e}")
            return False

    @staticmethod
    def save_kml_to_csv(stations: List[Dict[str, Any]], output_file: str, resource_type: str = "資源") -> bool:
        """保存 KML 資料到 CSV"""
        if not stations:
            print(f"❌ 沒有 KML {resource_type}資料可以儲存")
            return False

        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=['name', 'notes', 'info_source', 'lat', 'lng'])
                writer.writeheader()
                for station in stations:
                    row = {
                        'name': station.get('name', ''),
                        'notes': station.get('notes', ''),
                        'info_source': station.get('info_source', ''),
                        'lat': station.get('coordinates', {}).get('lat'),
                        'lng': station.get('coordinates', {}).get('lng')
                    }
                    writer.writerow(row)
            print(f"✅ 成功儲存 {len(stations)} 個 KML {resource_type}資料到 {output_file}")
            return True
        except IOError as e:
            print(f"❌ 儲存 KML CSV 檔案錯誤: {e}")
            return False

    @staticmethod
    def show_kml_summary(stations: List[Dict[str, Any]], resource_type: str = "資源", icon: str = "📍"):
        """顯示 KML 資料摘要"""
        if not stations:
            print(f"❌ 沒有找到任何 KML {resource_type}資料")
            return

        print(f"\n{icon} KML {resource_type}處理結果摘要:")
        print(f"總共找到: {len(stations)} 個{resource_type}")
        if len(stations) > 0:
            print(f"\n📍 {resource_type}列表:")
            for i, station in enumerate(stations[:10], 1):
                print(f"  {i}. {station['name']}")
            if len(stations) > 10:
                print(f"  ... 還有 {len(stations) - 10} 個{resource_type}")

    @staticmethod
    def get_address_from_coordinates(lat: float, lng: float) -> Optional[str]:
        """使用 Google Maps Geocoding API 獲取座標對應的地址"""
        google_api_key = os.getenv('GOOGLE_MAPS_API_KEY')
        if not google_api_key:
            print("    ⚠️  未設定 GOOGLE_MAPS_API_KEY 環境變數，跳過地址查詢")
            return None

        try:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {
                'latlng': f"{lat},{lng}",
                'key': google_api_key,
                'language': 'zh_tw'
            }

            print(f"    🗺️  查詢地址: ({lat}, {lng})")
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            if data['status'] == 'OK' and data['results']:
                address = data['results'][0]['formatted_address']
                print(f"    📍 找到地址: {address}")
                return address
            else:
                print(f"    ⚠️  無法找到地址，API 狀態: {data['status']}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"    ❌ Google Maps API 請求錯誤: {e}")
            return None
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            print(f"    ❌ Google Maps API 響應解析錯誤: {e}")
            return None


class WaterStationProcessor:
    """整合加水站處理器 - 支援 CSV 和 API 兩種資料源"""

    def __init__(self, csv_reader: Optional[PlacemarksCSVReader] = None, api_url: Optional[str] = None):
        self.csv_reader = csv_reader
        self.api_url = api_url
        self.csv_water_stations = []
        self.api_water_stations = []

    def extract_from_csv(self) -> List[Dict[str, Any]]:
        if not self.csv_reader:
            print("❌ 沒有提供 PlacemarksCSVReader 實例")
            return []

        # 篩選供水站：folder完全符合"供水站" 或 name包含"加水站"
        water_placemarks = []
        for placemark in self.csv_reader.get_placemarks():
            name = placemark.get('name', '')
            if '加水站' in name:
                water_placemarks.append(placemark)

        self.csv_water_stations = []
        seen_names = set()
        for placemark in water_placemarks:
            name = placemark.get('name', '')
            latitude = placemark.get('latitude')
            longitude = placemark.get('longitude')

            # 檢查座標是否為 NaN 或 None
            if pd.isna(latitude) or pd.isna(longitude) or latitude is None or longitude is None:
                print(f"⚠️  跳過無座標的供水站: {name}")
                continue

            # 檢查是否已處理過相同名稱
            if name in seen_names:
                print(f"⚠️  跳過重複名稱的供水站: {name}")
                continue
            seen_names.add(name)

            # 處理 notes 欄位，將 NaN 轉換為空字串
            description = placemark.get('description', '')
            if pd.isna(description) or description == 'nan':
                description = ''

            water_station = {
                "name": name,
                "notes": description,
                "info_source": "地圖一",
                "coordinates": {"lat": float(latitude), "lng": float(longitude)}
            }
            self.csv_water_stations.append(water_station)
        return self.csv_water_stations

    def extract_from_api(self) -> List[Dict[str, Any]]:
        if not self.api_url:
            print("❌ 沒有提供 API URL")
            return []
        raw_data = ProcessorUtils.fetch_api_data(self.api_url, '加水站')
        if not raw_data:
            return []
        self.api_water_stations = self._convert_api_data(raw_data)
        return self.api_water_stations

    def _convert_api_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        converted_stations = []
        for item in raw_data:
            coordinates = item.get('coordinates', {})
            lat = lng = None
            if coordinates:
                if isinstance(coordinates, dict):
                    lat = coordinates.get('lat') or coordinates.get('latitude')
                    lng = coordinates.get('lng') or coordinates.get('longitude')
                elif isinstance(coordinates, str):
                    try:
                        coords = coordinates.split(',')
                        if len(coords) >= 2:
                            lat, lng = float(coords[0].strip()), float(coords[1].strip())
                    except (ValueError, IndexError):
                        print(f"⚠️  無法解析座標字串: {coordinates}")

            station = {
                'id': item.get('id'), 'name': item.get('name'),
                'notes': item.get('notes') or item.get('description'),
                'info_source': item.get('info_source'), 'address': item.get('address'),
                'water_type': item.get('water_type'), 'opening_hours': item.get('opening_hours'),
                'is_free': item.get('is_free'), 'status': item.get('status'),
                'accessibility': item.get('accessibility'), 'lat': lat, 'lng': lng
            }
            converted_stations.append(station)
        return converted_stations

    def save_csv_to_csv(self, output_file: str, water_stations: Optional[List[Dict[str, Any]]] = None):
        data_to_save = water_stations if water_stations is not None else self.csv_water_stations
        if not data_to_save:
            print("❌ 沒有 CSV 供水站資料可以儲存")
            return
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=['name', 'notes', 'info_source', 'lat', 'lng'])
                writer.writeheader()
                for station in data_to_save:
                    row = {
                        'name': station.get('name', ''), 'notes': station.get('notes', ''),
                        'info_source': station.get('info_source', ''),
                        'lat': station.get('coordinates', {}).get('lat'),
                        'lng': station.get('coordinates', {}).get('lng')
                    }
                    writer.writerow(row)
            print(f"✅ 成功儲存 {len(data_to_save)} 個 CSV 供水站資料到 {output_file}")
        except IOError as e:
            print(f"❌ 儲存 CSV 檔案錯誤: {e}")

    def save_api_to_csv(self, output_file: str, water_stations: Optional[List[Dict[str, Any]]] = None):
        data_to_save = water_stations if water_stations is not None else self.api_water_stations
        if not data_to_save:
            print("❌ 沒有 API 加水站資料可以儲存")
            return
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['id', 'name', 'notes', 'info_source', 'address', 'water_type', 'opening_hours', 'is_free', 'status', 'accessibility', 'lat', 'lng']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for station in data_to_save:
                    row = {k: (v if v is not None else '') for k, v in station.items()}
                    writer.writerow(row)
            print(f"✅ 成功儲存 {len(data_to_save)} 個 API 加水站資料到 {output_file}")
        except IOError as e:
            print(f"❌ 儲存 API CSV 檔案錯誤: {e}")

    def show_csv_summary(self, water_stations: Optional[List[Dict[str, Any]]] = None):
        data_to_show = water_stations if water_stations is not None else self.csv_water_stations
        if not data_to_show:
            print("❌ 沒有找到任何 CSV 供水站資料")
            return
        print(f"\n🚰 CSV 供水站處理結果摘要:")
        print(f"總共找到: {len(data_to_show)} 個供水站")
        if len(data_to_show) > 0:
            print(f"\n📍 供水站列表:")
            for i, station in enumerate(data_to_show[:10], 1):
                print(f"  {i}. {station['name']}")
            if len(data_to_show) > 10:
                print(f"  ... 還有 {len(data_to_show) - 10} 個供水站")

    def show_api_summary(self, water_stations: Optional[List[Dict[str, Any]]] = None):
        data_to_show = water_stations if water_stations is not None else self.api_water_stations
        if not data_to_show:
            print("❌ 沒有找到任何 API 加水站資料")
            return
        total_count = len(data_to_show)
        with_coords = sum(1 for station in data_to_show if station['lat'] is not None and station['lng'] is not None)
        without_coords = total_count - with_coords
        print(f"\n🌐 API 加水站處理結果摘要:")
        print(f"總共找到: {total_count} 個加水站")
        print(f"有座標: {with_coords} 個")
        print(f"無座標: {without_coords} 個")
        if len(data_to_show) > 0:
            print(f"\n📍 加水站列表:")
            for i, station in enumerate(data_to_show[:10], 1):
                lat_lng = f"({station['lat']}, {station['lng']})" if station['lat'] is not None and station['lng'] is not None else "(無座標)"
                print(f"  {i}. {station['name']} {lat_lng}")
            if len(data_to_show) > 10:
                print(f"  ... 還有 {len(data_to_show) - 10} 個加水站")

    def get_csv_water_stations(self) -> List[Dict[str, Any]]:
        return self.csv_water_stations

    def get_api_water_stations(self) -> List[Dict[str, Any]]:
        return self.api_water_stations

    def sync_source_to_db(self, output_file: str = "water_stations_sync_requests.json") -> Dict[str, Any]:
        """比對 source 和 db 資料，生成同步請求的 JSON 檔案"""
        if not self.csv_water_stations:
            print("❌ 缺少 CSV 資料，無法進行同步")
            return {"updated": 0, "created": 0, "skipped": 0}

        # 建立 name 對應的索引
        csv_by_name = {station['name']: station for station in self.csv_water_stations}
        api_by_name = {station['name']: station for station in self.api_water_stations} if self.api_water_stations else {}

        updated_count = created_count = skipped_count = 0
        http_requests = []

        print(f"\n🔄 開始分析 source 和 db 資料...")

        for name, csv_station in csv_by_name.items():
            if name in api_by_name:
                # 存在於 DB 中，生成 PATCH 請求
                api_station = api_by_name[name]
                station_id = api_station.get('id')

                if not station_id:
                    print(f"⚠️  跳過無 ID 的站點: {name}")
                    skipped_count += 1
                    continue

                # 準備更新資料 - 只包含需要更新的欄位
                update_data = {}
                update_reasons = []

                # 1. 檢查是否需要更新 address (為空字串或 null)
                db_address = api_station.get('address', '')
                if not db_address or db_address.strip() == '':
                    coordinates = csv_station.get('coordinates', {})
                    lat = coordinates.get('lat')
                    lng = coordinates.get('lng')
                    if lat and lng:
                        address = ProcessorUtils.get_address_from_coordinates(lat, lng)
                        if address:
                            update_data['address'] = address
                            update_reasons.append('address')

                # 2. 檢查是否需要更新 notes
                source_notes = csv_station.get('notes', '') or ''
                db_notes = api_station.get('notes', '') or ''
                print(f"source_notes = {source_notes}")
                print(f"db_notes = {db_notes}")
                if source_notes != db_notes:
                    update_data['notes'] = source_notes
                    update_reasons.append('notes')

                # 3. 如果有欄位需要更新，添加必要的固定欄位
                if update_data:
                    # 4. 生成 PATCH 請求記錄
                    patch_request = {
                        'http_method': 'PATCH',
                        'url': f"https://guangfu250923.pttapp.cc/water_refill_stations/{station_id}",
                        'request_body': update_data,  # 直接存儲字典，不需要 json.dumps
                        'name': name,
                        'action': 'update'
                    }
                    http_requests.append(patch_request)
                    print(f"📝 生成更新請求: {name} (更新欄位: {', '.join(update_reasons)})")
                    updated_count += 1
                else:
                    # 沒有需要更新的欄位
                    print(f"ℹ️  跳過無變化的站點: {name}")
                    skipped_count += 1
            else:
                # 不存在於 DB 中，生成 POST 請求
                print(f"📝 生成創建請求: {name}")

                # 準備創建資料
                coordinates = csv_station.get('coordinates', {})
                lat = coordinates.get('lat')
                lng = coordinates.get('lng')

                # 獲取地址
                address = ""
                if lat and lng:
                    address = ProcessorUtils.get_address_from_coordinates(lat, lng) or ""

                create_data = {
                    "name": name,
                    "address": address,
                    "water_type": "drinking_water",
                    "opening_hours": "N/A",
                    "is_free": True,
                    "status": "active",
                    "accessibility": True,
                    "notes": csv_station.get('notes', ''),
                    "info_source": "地圖一",
                    "coordinates": {
                        "lat": lat,
                        "lng": lng
                    }
                }

                # 生成 POST 請求記錄
                post_request = {
                    'http_method': 'POST',
                    'url': 'https://guangfu250923.pttapp.cc/water_refill_stations/',
                    'request_body': create_data,  # 直接存儲字典，不需要 json.dumps
                    'name': name,
                    'action': 'create'
                }
                http_requests.append(post_request)
                created_count += 1

        # 保存 HTTP 請求到 JSON
        ProcessorUtils.save_json_requests(http_requests, output_file)

        summary = {
            "updated": updated_count,
            "created": created_count,
            "skipped": skipped_count,
            "total_requests": len(http_requests)
        }

        print(f"\n📊 同步分析結果摘要:")
        print(f"更新請求: {updated_count} 個")
        print(f"創建請求: {created_count} 個")
        print(f"跳過處理: {skipped_count} 個")
        print(f"總請求數: {len(http_requests)} 個")

        return summary



class MedicalStationProcessor:
    """醫療站處理器 - 支援 CSV 和 API 兩種資料源"""

    def __init__(self, csv_reader: Optional[PlacemarksCSVReader] = None, api_url: Optional[str] = None):
        self.csv_reader = csv_reader
        self.api_url = api_url
        self.csv_medical_stations = []
        self.api_medical_stations = []

    def extract_from_csv(self) -> List[Dict[str, Any]]:
        if not self.csv_reader:
            print("❌ 沒有提供 PlacemarksCSVReader 實例")
            return []

        # 篩選醫療站：folder完全符合"醫療站" 或 name包含"醫療站"
        medical_placemarks = []
        for placemark in self.csv_reader.get_placemarks():
            folder = placemark.get('folder', '')
            name = placemark.get('name', '')
            if folder == '醫療站' or '醫療站' in name:
                medical_placemarks.append(placemark)

        self.csv_medical_stations = []
        seen_names = set()
        for placemark in medical_placemarks:
            name = placemark.get('name', '')
            latitude = placemark.get('latitude')
            longitude = placemark.get('longitude')

            # 檢查座標是否為 NaN 或 None
            if pd.isna(latitude) or pd.isna(longitude) or latitude is None or longitude is None:
                print(f"⚠️  跳過無座標的醫療站: {name}")
                continue

            # 檢查是否已處理過相同名稱
            if name in seen_names:
                print(f"⚠️  跳過重複名稱的醫療站: {name}")
                continue
            seen_names.add(name)

            # 處理 notes 欄位，將 NaN 轉換為空字串
            description = placemark.get('description', '')
            if pd.isna(description) or description == 'nan':
                description = ''

            medical_station = {
                "name": name,
                "notes": description,
                "info_source": "地圖一",
                "coordinates": {"lat": float(latitude), "lng": float(longitude)}
            }
            self.csv_medical_stations.append(medical_station)
        return self.csv_medical_stations

    def extract_from_api(self) -> List[Dict[str, Any]]:
        if not self.api_url:
            print("❌ 沒有提供 API URL")
            return []
        raw_data = ProcessorUtils.fetch_api_data(self.api_url, '醫療站')
        if not raw_data:
            return []
        self.api_medical_stations = self._convert_api_data(raw_data)
        return self.api_medical_stations

    def _convert_api_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        converted_stations = []
        for item in raw_data:
            # 處理 services 欄位 (保持 JSON array 格式)
            services = item.get('services', [])
            if isinstance(services, list):
                services_str = json.dumps(services, ensure_ascii=False) if services else '[]'
            else:
                services_str = str(services) if services else '[]'

            # 處理座標資訊
            coordinates = item.get('coordinates', {})
            lat = lng = None
            if coordinates:
                if isinstance(coordinates, dict):
                    lat = coordinates.get('lat') or coordinates.get('latitude')
                    lng = coordinates.get('lng') or coordinates.get('longitude')

            station = {
                'id': item.get('id'),
                'station_type': item.get('station_type'),
                'name': item.get('name'),
                'location': item.get('location'),
                'detailed_address': item.get('detailed_address'),
                'phone': item.get('phone'),
                'status': item.get('status'),
                'notes': item.get('notes'),
                'operating_hours': item.get('operating_hours'),
                'link': item.get('link'),
                'services': services_str,
                'lat': lat,
                'lng': lng
            }
            converted_stations.append(station)
        return converted_stations

    def save_csv_to_csv(self, output_file: str, medical_stations: Optional[List[Dict[str, Any]]] = None):
        data_to_save = medical_stations if medical_stations is not None else self.csv_medical_stations
        if not data_to_save:
            print("❌ 沒有 KML 醫療站資料可以儲存")
            return
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=['name', 'notes', 'info_source', 'lat', 'lng'])
                writer.writeheader()
                for station in data_to_save:
                    row = {
                        'name': station.get('name', ''), 'notes': station.get('notes', ''),
                        'info_source': station.get('info_source', ''),
                        'lat': station.get('coordinates', {}).get('lat'),
                        'lng': station.get('coordinates', {}).get('lng')
                    }
                    writer.writerow(row)
            print(f"✅ 成功儲存 {len(data_to_save)} 個 KML 醫療站資料到 {output_file}")
        except IOError as e:
            print(f"❌ 儲存 KML CSV 檔案錯誤: {e}")

    def save_api_to_csv(self, output_file: str, medical_stations: Optional[List[Dict[str, Any]]] = None):
        data_to_save = medical_stations if medical_stations is not None else self.api_medical_stations
        if not data_to_save:
            print("❌ 沒有 API 醫療站資料可以儲存")
            return
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['id', 'name', 'detailed_address', 'lat', 'lng', 'location', 'notes', 'station_type', 'phone', 'status', 'operating_hours', 'link', 'services']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for station in data_to_save:
                    row = {k: (v if v is not None else '') for k, v in station.items()}
                    writer.writerow(row)
            print(f"✅ 成功儲存 {len(data_to_save)} 個 API 醫療站資料到 {output_file}")
        except IOError as e:
            print(f"❌ 儲存 API CSV 檔案錯誤: {e}")

    def show_csv_summary(self, medical_stations: Optional[List[Dict[str, Any]]] = None):
        data_to_show = medical_stations if medical_stations is not None else self.csv_medical_stations
        if not data_to_show:
            print("❌ 沒有找到任何 KML 醫療站資料")
            return
        print(f"\n🏥 KML 醫療站處理結果摘要:")
        print(f"總共找到: {len(data_to_show)} 個醫療站")
        if len(data_to_show) > 0:
            print(f"\n📍 醫療站列表:")
            for i, station in enumerate(data_to_show[:10], 1):
                print(f"  {i}. {station['name']}")
            if len(data_to_show) > 10:
                print(f"  ... 還有 {len(data_to_show) - 10} 個醫療站")

    def show_api_summary(self, medical_stations: Optional[List[Dict[str, Any]]] = None):
        data_to_show = medical_stations if medical_stations is not None else self.api_medical_stations
        if not data_to_show:
            print("❌ 沒有找到任何 API 醫療站資料")
            return
        total_count = len(data_to_show)
        with_location = sum(1 for station in data_to_show if station.get('location'))
        without_location = total_count - with_location
        print(f"\n🌐 API 醫療站處理結果摘要:")
        print(f"總共找到: {total_count} 個醫療站")
        print(f"有位置資訊: {with_location} 個")
        print(f"無位置資訊: {without_location} 個")
        if len(data_to_show) > 0:
            print(f"\n📍 醫療站列表:")
            for i, station in enumerate(data_to_show[:10], 1):
                location_info = f"({station.get('location', '無位置資訊')})" if station.get('location') else "(無位置資訊)"
                station_type = f"[{station.get('station_type', '未分類')}]" if station.get('station_type') else ""
                print(f"  {i}. {station_type} {station.get('name', 'N/A')} {location_info}")
            if len(data_to_show) > 10:
                print(f"  ... 還有 {len(data_to_show) - 10} 個醫療站")

    def get_csv_medical_stations(self) -> List[Dict[str, Any]]:
        return self.csv_medical_stations

    def get_api_medical_stations(self) -> List[Dict[str, Any]]:
        return self.api_medical_stations

    def sync_source_to_db(self, output_file: str = "medical_stations_sync_requests.json") -> Dict[str, Any]:
        """比對 source 和 db 資料，生成同步請求的 JSON 檔案"""
        if not self.csv_medical_stations:
            print("❌ 缺少 KML 資料，無法進行同步")
            return {"updated": 0, "created": 0, "skipped": 0}

        # 建立 name 對應的索引
        csv_by_name = {station['name']: station for station in self.csv_medical_stations}
        api_by_name = {station['name']: station for station in self.api_medical_stations} if self.api_medical_stations else {}

        updated_count = created_count = skipped_count = 0
        http_requests = []

        print(f"\n🔄 開始分析 source 和 db 醫療站資料...")

        for name, csv_station in csv_by_name.items():
            if name in api_by_name:
                # 存在於 DB 中，生成 PATCH 請求
                api_station = api_by_name[name]
                station_id = api_station.get('id')

                if not station_id:
                    print(f"⚠️  跳過無 ID 的醫療站: {name}")
                    skipped_count += 1
                    continue

                # 準備更新資料 - 只包含需要更新的欄位
                update_data = {}
                update_reasons = []

                # 1. 檢查是否需要更新座標
                source_coordinates = csv_station.get('coordinates', {})
                source_lat = source_coordinates.get('lat')
                source_lng = source_coordinates.get('lng')

                db_lat = api_station.get('lat')
                db_lng = api_station.get('lng')

                if source_lat and source_lng and (source_lat != db_lat or source_lng != db_lng):
                    update_data['coordinates'] = {"lat": source_lat, "lng": source_lng}
                    update_reasons.append('coordinates')

                # 2. 檢查是否需要更新 notes
                source_notes = csv_station.get('notes', '') or ''
                db_notes = api_station.get('notes', '') or ''
                if source_notes != db_notes:
                    print(f"db_notes = {db_notes}")
                    print(f"source_notes = {source_notes}")
                    update_data['notes'] = source_notes
                    update_reasons.append('notes')

                # 3. 檢查是否需要更新 detailed_address (為空字串或 null)
                db_address = api_station.get('detailed_address', '')
                if not db_address or db_address.strip() == '':
                    if source_lat and source_lng:
                        address = ProcessorUtils.get_address_from_coordinates(source_lat, source_lng)
                        if address:
                            update_data['detailed_address'] = address
                            update_reasons.append('detailed_address')

                # 4. 如果有欄位需要更新，生成 PATCH 請求記錄
                if update_data:
                    patch_request = {
                        'http_method': 'PATCH',
                        'url': f"https://guangfu250923.pttapp.cc/medical_stations/{station_id}",
                        'request_body': update_data,
                        'name': name,
                        'action': 'update'
                    }
                    http_requests.append(patch_request)
                    print(f"📝 生成更新請求: {name} (更新欄位: {', '.join(update_reasons)})")
                    updated_count += 1
                else:
                    # 沒有需要更新的欄位
                    print(f"ℹ️  跳過無變化的醫療站: {name}")
                    skipped_count += 1
            else:
                # 不存在於 DB 中，生成 POST 請求
                print(f"📝 生成創建請求: {name}")

                # 準備創建資料
                coordinates = csv_station.get('coordinates', {})
                lat = coordinates.get('lat')
                lng = coordinates.get('lng')

                # 獲取地址
                address = ""
                if lat and lng:
                    address = ProcessorUtils.get_address_from_coordinates(lat, lng) or ""

                create_data = {
                    "name": name,
                    "detailed_address": address,
                    "station_type": "-",
                    "location": address,  # 可以根據需要調整
                    "phone": "",
                    "status": "-",
                    "notes": csv_station.get('notes', ''),
                    "operating_hours": "",
                    "link": "",
                    "services": [],
                    "coordinates": {
                        "lat": lat,
                        "lng": lng
                    }
                }

                # 生成 POST 請求記錄
                post_request = {
                    'http_method': 'POST',
                    'url': 'https://guangfu250923.pttapp.cc/medical_stations/',
                    'request_body': create_data,
                    'name': name,
                    'action': 'create'
                }
                http_requests.append(post_request)
                created_count += 1

        # 保存 HTTP 請求到 JSON
        ProcessorUtils.save_json_requests(http_requests, output_file)

        summary = {
            "updated": updated_count,
            "created": created_count,
            "skipped": skipped_count,
            "total_requests": len(http_requests)
        }

        print(f"\n📊 醫療站同步分析結果摘要:")
        print(f"更新請求: {updated_count} 個")
        print(f"創建請求: {created_count} 個")
        print(f"跳過處理: {skipped_count} 個")
        print(f"總請求數: {len(http_requests)} 個")

        return summary


class RestroomProcessor:
    """廁所處理器 - 支援 CSV 和 API 兩種資料源"""

    def __init__(self, csv_reader: Optional[PlacemarksCSVReader] = None, api_url: Optional[str] = None):
        self.csv_reader = csv_reader
        self.api_url = api_url
        self.csv_restrooms = []
        self.api_restrooms = []

    def extract_from_csv(self) -> List[Dict[str, Any]]:
        if not self.csv_reader:
            print("❌ 沒有提供 PlacemarksCSVReader 實例")
            return []

        # 篩選廁所：folder完全符合"流動廁所" 或 name包含"廁所"
        restroom_placemarks = []
        for placemark in self.csv_reader.get_placemarks():
            folder = placemark.get('folder', '')
            name = placemark.get('name', '')
            if folder == '流動廁所' or '廁所' in name:
                restroom_placemarks.append(placemark)

        self.csv_restrooms = []
        seen_names = set()
        for placemark in restroom_placemarks:
            name = placemark.get('name', '')
            latitude = placemark.get('latitude')
            longitude = placemark.get('longitude')

            # 檢查座標是否為 NaN 或 None
            if pd.isna(latitude) or pd.isna(longitude) or latitude is None or longitude is None:
                print(f"⚠️  跳過無座標的廁所: {name}")
                continue

            # 檢查是否已處理過相同名稱
            if name in seen_names:
                print(f"⚠️  跳過重複名稱的廁所: {name}")
                continue
            seen_names.add(name)

            # 處理 notes 欄位，將 NaN 轉換為空字串
            description = placemark.get('description', '')
            if pd.isna(description) or description == 'nan':
                description = ''

            restroom = {
                "name": name,
                "notes": description,
                "info_source": "地圖一",
                "coordinates": {"lat": float(latitude), "lng": float(longitude)}
            }
            self.csv_restrooms.append(restroom)
        return self.csv_restrooms

    def extract_from_api(self) -> List[Dict[str, Any]]:
        if not self.api_url:
            print("❌ 沒有提供 API URL")
            return []
        raw_data = raw_data = ProcessorUtils.fetch_api_data(self.api_url, '廁所')
        if not raw_data:
            return []
        self.api_restrooms = self._convert_api_data(raw_data)
        return self.api_restrooms

    def _convert_api_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        converted_restrooms = []
        for item in raw_data:
            coordinates = item.get('coordinates', {})
            lat = lng = None
            if coordinates:
                if isinstance(coordinates, dict):
                    lat = coordinates.get('lat') or coordinates.get('latitude')
                    lng = coordinates.get('lng') or coordinates.get('longitude')
                elif isinstance(coordinates, str):
                    try:
                        coords = coordinates.split(',')
                        if len(coords) >= 2:
                            lat, lng = float(coords[0].strip()), float(coords[1].strip())
                    except (ValueError, IndexError):
                        print(f"⚠️  無法解析座標字串: {coordinates}")

            restroom = {
                'id': item.get('id'),
                'name': item.get('name'),
                'address': item.get('address'),
                'facility_type': item.get('facility_type'),
                'opening_hours': item.get('opening_hours'),
                'is_free': item.get('is_free'),
                'has_water': item.get('has_water'),
                'has_lighting': item.get('has_lighting'),
                'status': item.get('status'),
                'notes': item.get('notes'),
                'lat': lat,
                'lng': lng
            }
            converted_restrooms.append(restroom)
        return converted_restrooms

    def save_csv_to_csv(self, output_file: str, restrooms: Optional[List[Dict[str, Any]]] = None):
        data_to_save = restrooms if restrooms is not None else self.csv_restrooms
        if not data_to_save:
            print("❌ 沒有 KML 廁所資料可以儲存")
            return
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=['name', 'notes', 'info_source', 'lat', 'lng'])
                writer.writeheader()
                for restroom in data_to_save:
                    row = {
                        'name': restroom.get('name', ''), 'notes': restroom.get('notes', ''),
                        'info_source': restroom.get('info_source', ''),
                        'lat': restroom.get('coordinates', {}).get('lat'),
                        'lng': restroom.get('coordinates', {}).get('lng')
                    }
                    writer.writerow(row)
            print(f"✅ 成功儲存 {len(data_to_save)} 個 KML 廁所資料到 {output_file}")
        except IOError as e:
            print(f"❌ 儲存 KML CSV 檔案錯誤: {e}")

    def save_api_to_csv(self, output_file: str, restrooms: Optional[List[Dict[str, Any]]] = None):
        data_to_save = restrooms if restrooms is not None else self.api_restrooms
        if not data_to_save:
            print("❌ 沒有 API 廁所資料可以儲存")
            return
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['id', 'name', 'address', 'facility_type', 'opening_hours', 'is_free', 'has_water', 'has_lighting', 'status', 'notes', 'lat', 'lng']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for restroom in data_to_save:
                    row = {k: (v if v is not None else '') for k, v in restroom.items()}
                    writer.writerow(row)
            print(f"✅ 成功儲存 {len(data_to_save)} 個 API 廁所資料到 {output_file}")
        except IOError as e:
            print(f"❌ 儲存 API CSV 檔案錯誤: {e}")

    def show_csv_summary(self, restrooms: Optional[List[Dict[str, Any]]] = None):
        data_to_show = restrooms if restrooms is not None else self.csv_restrooms
        if not data_to_show:
            print("❌ 沒有找到任何 KML 廁所資料")
            return
        print(f"\n🚻 KML 廁所處理結果摘要:")
        print(f"總共找到: {len(data_to_show)} 個廁所")
        if len(data_to_show) > 0:
            print(f"\n📍 廁所列表:")
            for i, restroom in enumerate(data_to_show[:10], 1):
                print(f"  {i}. {restroom['name']}")
            if len(data_to_show) > 10:
                print(f"  ... 還有 {len(data_to_show) - 10} 個廁所")

    def show_api_summary(self, restrooms: Optional[List[Dict[str, Any]]] = None):
        data_to_show = restrooms if restrooms is not None else self.api_restrooms
        if not data_to_show:
            print("❌ 沒有找到任何 API 廁所資料")
            return
        total_count = len(data_to_show)
        with_coords = sum(1 for restroom in data_to_show if restroom['lat'] is not None and restroom['lng'] is not None)
        without_coords = total_count - with_coords
        print(f"\n🌐 API 廁所處理結果摘要:")
        print(f"總共找到: {total_count} 個廁所")
        print(f"有座標: {with_coords} 個")
        print(f"無座標: {without_coords} 個")
        if len(data_to_show) > 0:
            print(f"\n📍 廁所列表:")
            for i, restroom in enumerate(data_to_show[:10], 1):
                lat_lng = f"({restroom['lat']}, {restroom['lng']})" if restroom['lat'] is not None and restroom['lng'] is not None else "(無座標)"
                print(f"  {i}. {restroom['name']} {lat_lng}")
            if len(data_to_show) > 10:
                print(f"  ... 還有 {len(data_to_show) - 10} 個廁所")

    def get_csv_restrooms(self) -> List[Dict[str, Any]]:
        return self.csv_restrooms

    def get_api_restrooms(self) -> List[Dict[str, Any]]:
        return self.api_restrooms

    def sync_source_to_db(self, output_file: str = "restrooms_sync_requests.json") -> Dict[str, Any]:
        """比對 source 和 db 資料，生成同步請求的 JSON 檔案"""
        if not self.csv_restrooms:
            print("❌ 缺少 KML 資料，無法進行同步")
            return {"updated": 0, "created": 0, "skipped": 0}

        # 建立 name 對應的索引
        csv_by_name = {restroom['name']: restroom for restroom in self.csv_restrooms}
        api_by_name = {restroom['name']: restroom for restroom in self.api_restrooms} if self.api_restrooms else {}

        updated_count = created_count = skipped_count = 0
        http_requests = []

        print(f"\n🔄 開始分析 source 和 db 廁所資料...")
        print(csv_by_name.keys())
        print(len(csv_by_name.keys()))
        print(api_by_name.keys())
        print(len(api_by_name.keys()))

        index = 1
        for name, csv_restroom in csv_by_name.items():
            print([index])
            index += 1
            if name in api_by_name:
                # 存在於 DB 中，生成 PATCH 請求
                api_restroom = api_by_name[name]
                restroom_id = api_restroom.get('id')

                if not restroom_id:
                    print(f"⚠️  跳過無 ID 的廁所: {name}")
                    skipped_count += 1
                    continue

                # 準備更新資料 - 只包含需要更新的欄位
                update_data = {}
                update_reasons = []

                # 1. 檢查是否需要更新 address (為空字串或 null)
                db_address = api_restroom.get('address', '')
                if not db_address or db_address.strip() == '' or db_address.strip() == '-':
                    coordinates = csv_restroom.get('coordinates', {})
                    lat = coordinates.get('lat')
                    lng = coordinates.get('lng')
                    if lat and lng:
                        address = ProcessorUtils.get_address_from_coordinates(lat, lng)
                        if address:
                            update_data['address'] = address
                            update_reasons.append('address')

                # 2. 檢查是否需要更新 notes
                source_notes = csv_restroom.get('notes', '') or ''
                db_notes = api_restroom.get('notes', '') or ''
                if source_notes != db_notes:
                    print(f"id = {restroom_id}")
                    print(f"source_notes = {source_notes}")
                    print(f"db_notes = {db_notes}")
                    update_data['notes'] = source_notes
                    update_reasons.append('notes')

                # 3. 如果有欄位需要更新，添加必要的固定欄位
                if update_data:
                    # 4. 生成 PATCH 請求記錄
                    patch_request = {
                        'http_method': 'PATCH',
                        'url': f"https://guangfu250923.pttapp.cc/restrooms/{restroom_id}",
                        'request_body': update_data,
                        'name': name,
                        'action': 'update'
                    }
                    http_requests.append(patch_request)
                    print(f"📝 生成更新請求: {name} (更新欄位: {', '.join(update_reasons)})")
                    updated_count += 1
                else:
                    # 沒有需要更新的欄位
                    print(f"ℹ️  跳過無變化的廁所: {name}")
                    skipped_count += 1
            else:
                # 不存在於 DB 中，生成 POST 請求
                print(f"📝 生成創建請求: {name}")

                # 準備創建資料
                coordinates = csv_restroom.get('coordinates', {})
                lat = coordinates.get('lat')
                lng = coordinates.get('lng')
                notes = csv_restroom.get('notes', '')

                # 獲取地址
                address = ""
                if lat and lng:
                    address = ProcessorUtils.get_address_from_coordinates(lat, lng) or ""

                create_data = {
                    "name": name,
                    "notes": notes,
                    "address": address,
                    "facility_type": "mobile_toilet",
                    "opening_hours": "-",
                    "is_free": True,
                    "has_water": True,
                    "has_lighting": True,
                    "status": "-",
                    "coordinates": {
                        "lat": lat,
                        "lng": lng
                    }
                }

                # 生成 POST 請求記錄
                post_request = {
                    'http_method': 'POST',
                    'url': 'https://guangfu250923.pttapp.cc/restrooms/',
                    'request_body': create_data,
                    'name': name,
                    'action': 'create'
                }
                http_requests.append(post_request)
                created_count += 1

        # 保存 HTTP 請求到 JSON
        ProcessorUtils.save_json_requests(http_requests, output_file)

        summary = {
            "updated": updated_count,
            "created": created_count,
            "skipped": skipped_count,
            "total_requests": len(http_requests)
        }

        print(f"\n📊 廁所同步分析結果摘要:")
        print(f"更新請求: {updated_count} 個")
        print(f"創建請求: {created_count} 個")
        print(f"跳過處理: {skipped_count} 個")
        print(f"總請求數: {len(http_requests)} 個")

        return summary


class ShowerStationProcessor:
    """洗澡點處理器 - 支援 CSV 和 API 兩種資料源"""


    def __init__(self, csv_reader: Optional[PlacemarksCSVReader] = None, api_url: Optional[str] = None):
        self.csv_reader = csv_reader
        self.api_url = api_url
        self.csv_showers = []
        self.api_showers = []

    def extract_from_csv(self) -> List[Dict[str, Any]]:
        if not self.csv_reader:
            print("❌ 沒有提供 PlacemarksCSVReader 實例")
            return []

        # 篩選洗澡點
        shower_placemarks = []
        for placemark in self.csv_reader.get_placemarks():
            folder = placemark.get('folder', '')
            name = placemark.get('name', '')
            if '沐浴' in folder or '洗澡' in folder or '沐浴' in name or '洗澡' in name:
                shower_placemarks.append(placemark)

        self.csv_showers = []
        seen_names = set()
        for placemark in shower_placemarks:
            name = placemark.get('name', '')
            lat = placemark.get('latitude')
            lng = placemark.get('longitude')
            
            # 檢查座標是否為NaN 或 None
            if pd.isna(lat) or pd.isna(lng) or lat is None or lng is None:
                print(f"⚠️  跳過無座標的洗澡點: {name}")
                continue
            
            # 檢查是否已處理過相同名稱
            if name in seen_names:
                print(f"⚠️  跳過重複名稱的洗澡點: {name}")
                continue
            seen_names.add(name)
            
            # 處理 notes 欄位，將 NaN 轉換為空字串
            description = placemark.get('description', '')
            if pd.isna(description) or description == 'nan':
                description = ''
                
            shower = {
                "name": name,
                "notes": description,
                "info_source": "地圖一",
                "coordinates": {"lat": float(lat), "lng": float(lng)}
            }
            self.csv_showers.append(shower)
        return self.csv_showers

    def extract_from_api(self) -> List[Dict[str, Any]]:
        if not self.api_url:
            print("ℹ️ 沒有提供 API URL")
            return []
        raw_data = ProcessorUtils.fetch_api_data(self.api_url, '洗澡點')
        if not raw_data:
            return []
        self.api_showers = self._convert_api_data(raw_data)
        return self.api_showers
        
    def _convert_api_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        converted_showers = []
        for item in raw_data:
            coordinates = item.get('coordinates', {})
            lat = lng = None
            if coordinates:
                if isinstance(coordinates, dict):
                    lat = coordinates.get('lat') or coordinates.get('latitude')
                    lng = coordinates.get('lng') or coordinates.get('longitude')
                elif isinstance(coordinates, str):
                    try:
                        coords = coordinates.split(',')
                        if len(coords) >= 2:
                            lat, lng = float(coords[0].strip()), float(coords[1].strip())
                    except (ValueError, IndexError):
                        print(f"⚠️  無法解析座標字串: {coordinates}")
                        
            shower = {
                'id': item.get('id'),
                'name': item.get('name'),
                'address': item.get('address'),
                'phone': item.get('phone'),
                'facility_type': item.get('facility_type'),
                'time_slots': item.get('time_slots'),
                "available_period": item.get('available_period'),
                "pricing": item.get('pricing'),
                "info_source": item.get('info_source'),
                'is_free': item.get('is_free'),
                "contact_method": item.get('contact_method'),
                "requires_appointment": item.get('requires_appointment'),
                'status': item.get('status'),
                'notes': item.get('notes'),
                'lat': lat,
                'lng': lng
            }
            
            converted_showers.append(shower)
        return converted_showers
        
    def save_csv_to_csv(self, output_file: str, showers: Optional[List[Dict[str, Any]]] = None):
        data_to_save = showers if showers is not None else self.csv_showers
        if not data_to_save:
            print("❌ 沒有 KML 洗澡點資料可以儲存")
            return
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=['name', 'notes', 'info_source', 'lat', 'lng'])
                writer.writeheader()
                for shower in data_to_save:
                    row = {
                        'name': shower.get('name', ''), 'notes': shower.get('notes', ''),
                        'info_source': shower.get('info_source', ''),
                        'lat': shower.get('coordinates', {}).get('lat'),
                        'lng': shower.get('coordinates', {}).get('lng')
                    }
                    writer.writerow(row)
            print(f"✅ 成功儲存 {len(data_to_save)} 個 KML 洗澡點資料到 {output_file}")
        except IOError as e:
            print(f"❌ 儲存 KML CSV 檔案錯誤: {e}")
            
            
    def save_api_to_csv(self, output_file: str, showers: Optional[List[Dict[str, Any]]] = None):
        data_to_save = showers if showers is not None else self.api_showers
        if not data_to_save:
            print("❌ 沒有 API 洗澡點資料可以儲存")
            return
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['id', 'name', 'address', 'phone', 'facility_type', 'time_slots', 'available_period', 'pricing', 'info_source', 'is_free', 'contact_method', 'requires_appointment', 'status', 'notes', 'lat', 'lng']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for shower in data_to_save:
                    row = {k: (v if v is not None else '') for k, v in shower.items()}
                    writer.writerow(row)
            print(f"✅ 成功儲存 {len(data_to_save)} 個 API 洗澡點資料到 {output_file}")
        except IOError as e:
            print(f"❌ 儲存 API CSV 檔案錯誤: {e}")
            
    def show_csv_summary(self, showers: Optional[List[Dict[str, Any]]] = None):
        data_to_show = showers if showers is not None else self.csv_showers
        if not data_to_show:
            print("❌ 沒有找到任何 KML 洗澡點資料")
            return
        print(f"\n🚻 KML 洗澡點處理結果摘要:")
        print(f"總共找到: {len(data_to_show)} 個洗澡點")
        if len(data_to_show) > 0:
            print(f"\n📍 洗澡點列表:")
            for i, shower in enumerate(data_to_show[:10], 1):
                print(f"  {i}. {shower['name']}")
            if len(data_to_show) > 10:
                print(f"  ... 還有 {len(data_to_show) - 10} 個洗澡點")
    
    def show_api_summary(self, showers: Optional[List[Dict[str, Any]]] = None):
        data_to_show = showers if showers is not None else self.api_showers
        if not data_to_show:
            print("❌ 沒有找到任何 API 洗澡點資料")
            return
        total_count = len(data_to_show)
        with_coords = sum(1 for shower in data_to_show if shower['lat'] is not None and shower['lng'] is not None)
        without_coords = total_count - with_coords
        
        print(f"\n🌐 API 洗澡點處理結果摘要:")
        print(f"總共找到: {total_count} 個洗澡點")
        print(f"有座標: {with_coords} 個")
        print(f"無座標: {without_coords} 個")
        
        if len(data_to_show) > 0:
            print(f"\n📍 洗澡點列表:")
            for i, shower in enumerate(data_to_show[:10], 1):
                lat_lng = f"({shower['lat']}, {shower['lng']})" if shower['lat'] is not None and shower['lng'] is not None else "(無座標)"
                print(f"  {i}. {shower['name']} {lat_lng}")
            if len(data_to_show) > 10:
                print(f"  ... 還有 {len(data_to_show) - 10} 個洗澡點")
                
    
    def get_csv_showers(self) -> List[Dict[str, Any]]:
        return self.csv_showers
    
    def get_api_showers(self) -> List[Dict[str, Any]]:
        return self.api_showers

    def sync_source_to_db(self, output_file: str = "showers_sync_requests.json") -> Dict[str, Any]:
        """比對 source 和 db 資料，生成同步請求的 JSON 檔案"""
        if not self.csv_showers:
            print("❌ 缺少 KML 資料，無法進行同步")
            return {"updated": 0, "created": 0, "skipped": 0}
        
        # 建立 name 對應的索引
        csv_by_name = {shower['name']: shower for shower in self.csv_showers}
        api_by_name = {shower['name']: shower for shower in self.api_showers} if self.api_showers else {}
        
        updated_count = created_count = skipped_count = 0
        http_requests = []
        
        print(f"\n🔄 開始分析 source 和 db 洗澡點資料...")
        
        for name, csv_shower in csv_by_name.items():
            if name in api_by_name:
                # 存在於 DB 中，生成 PATCH 請求
                api_shower = api_by_name[name]
                shower_id = api_shower.get('id')

                if not shower_id:
                    print(f"⚠️  跳過無 ID 的洗澡點: {name}")
                    skipped_count += 1
                    continue
                
                # 準備更新資料 - 只包含需要更新的欄位
                update_data = {}
                update_reasons = []
                
                # 1. 檢查是否需要更新 address (為空字串或 null)
                db_address = api_shower.get('address', '')
                if not db_address or db_address.strip() == '' or db_address.strip() == '-':
                    coordinates = csv_shower.get('coordinates', {})
                    lat = coordinates.get('lat')
                    lng = coordinates.get('lng')
                    if lat and lng:
                        address = ProcessorUtils.get_address_from_coordinates(lat, lng)
                        if address:
                            update_data['address'] = address
                            update_reasons.append('address')
                            
                # 2. 檢查是否需要更新 notes
                source_notes = csv_shower.get('notes', '') or ''
                db_notes = api_shower.get('notes', '') or ''
                if source_notes != db_notes:
                    print(f"source_notes = {source_notes}")
                    print(f"db_notes = {db_notes}")
                    update_data['notes'] = source_notes
                    update_reasons.append('notes')
                    
                # 3. 如果有欄位需要更新，添加必要的固定欄位
                if update_data:
                    # 4. 生成 PATCH 請求記錄
                    patch_request = {
                        'http_method': 'PATCH',
                        'url': f"https://guangfu250923.pttapp.cc/shower_stations/{shower_id}",
                        'request_body': update_data,
                        'name': name,
                        'action': 'update'
                    }
                    http_requests.append(patch_request)
                    print(f"📝 生成更新請求: {name} (更新欄位: {', '.join(update_reasons)})")
                    updated_count += 1
                else:
                    # 沒有需要更新的欄位
                    print(f"ℹ️  跳過無變化的洗澡點: {name}")
                    skipped_count += 1
            else:
                # 不存在於 DB 中，生成 POST 請求
                print(f"📝 生成創建請求: {name}")

                # 準備創建資料
                coordinates = csv_shower.get('coordinates', {})
                lat = coordinates.get('lat')
                lng = coordinates.get('lng')

                # 獲取地址
                address = ""
                if lat and lng:
                    address = ProcessorUtils.get_address_from_coordinates(lat, lng) or ""
                    
                    
                create_data = {
                    "name": name,
                    "address": address,
                    "facility_type": "-",
                    "time_slots": "-",
                    "available_period": "-",
                    "requires_appointment": False,
                    "is_free": True,
                    "status": "-",
                    "coordinates": {
                        "lat": lat,
                        "lng": lng
                    }
                }
                
                # 生成 POST 請求記錄
                post_request = {
                    'http_method': 'POST',
                    'url': 'https://guangfu250923.pttapp.cc/shower_stations',
                    'request_body': create_data,
                    'name': name,
                    'action': 'create'
                }
                http_requests.append(post_request)
                created_count += 1
    
    # 保存 HTTP 請求到 JSON
        ProcessorUtils.save_json_requests(http_requests, output_file)

        summary = {
            "updated": updated_count,
            "created": created_count,
            "skipped": skipped_count,
            "total_requests": len(http_requests)
        }

        print(f"\n📊 洗澡點同步分析結果摘要:")
        print(f"更新請求: {updated_count} 個")
        print(f"創建請求: {created_count} 個")
        print(f"跳過處理: {skipped_count} 個")
        print(f"總請求數: {len(http_requests)} 個")

        return summary


def main():
    # 檢查命令列參數
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    input_file = "placemarks.csv"

    print("📊 ETL 工具 - 從 placemarks.csv 處理資料")
    print(f"📂 讀取檔案: {input_file}")
    print(f"🔧 執行模式: {mode}")

    # 讀取 CSV
    csv_reader = PlacemarksCSVReader()
    print("\n🔄 正在讀取 placemarks.csv 檔案...")
    placemarks = csv_reader.read_from_csv(input_file)
    csv_reader.show_summary()

    if not placemarks:
        print("❌ 沒有資料可以處理")
        return

    # 根據模式執行不同處理器
    if mode == "csv":
        print("🎉 CSV 讀取完成！")
        return

    if mode in ["water", "all"]:
        # 處理加水站
        water_api_url = "https://guangfu250923.pttapp.cc/water_refill_stations"
        water_processor = WaterStationProcessor(csv_reader=csv_reader, api_url=water_api_url)

        print(f"\n🚰 正在提取 CSV 供水站資料...")
        csv_water_stations = water_processor.extract_from_csv()
        water_processor.show_csv_summary()
        if csv_water_stations:
            print(f"\n💾 正在儲存 CSV 供水站 CSV...")
            water_processor.save_csv_to_csv("water_stations_source.csv")

        print(f"\n🌐 正在提取 API 加水站資料...")
        api_water_stations = water_processor.extract_from_api()
        water_processor.show_api_summary()
        if api_water_stations:
            print(f"\n💾 正在儲存 API 加水站 CSV...")
            water_processor.save_api_to_csv("water_stations_db.csv")

        # 同步 source 到 db (僅限 water 或 all 模式)
        if mode == "water" or mode == "all":
            if csv_water_stations:
                print(f"\n🔄 開始同步 source 資料到 API 資料庫...")
                sync_result = water_processor.sync_source_to_db()

    if mode in ["medical", "all"]:
        # 處理醫療站
        medical_api_url = "https://guangfu250923.pttapp.cc/medical_stations"
        medical_processor = MedicalStationProcessor(csv_reader=csv_reader, api_url=medical_api_url)

        print(f"\n🏥 正在提取 CSV 醫療站資料...")
        csv_medical_stations = medical_processor.extract_from_csv()
        medical_processor.show_csv_summary()
        if csv_medical_stations:
            print(f"\n💾 正在儲存 CSV 醫療站 CSV...")
            medical_processor.save_csv_to_csv("medical_stations_source.csv")

        print(f"\n🌐 正在提取 API 醫療站資料...")
        api_medical_stations = medical_processor.extract_from_api()
        medical_processor.show_api_summary()
        if api_medical_stations:
            print(f"\n💾 正在儲存 API 醫療站 CSV...")
            medical_processor.save_api_to_csv("medical_stations_db.csv")

        # 同步 source 到 db (僅限 medical 或 all 模式)
        if mode == "medical" or mode == "all":
            if csv_medical_stations:
                print(f"\n🔄 開始分析 source 醫療站資料到 API 資料庫...")
                sync_result = medical_processor.sync_source_to_db()

    if mode in ["restroom", "all"]:
        # 處理廁所
        restroom_api_url = "https://guangfu250923.pttapp.cc/restrooms"
        restroom_processor = RestroomProcessor(csv_reader=csv_reader, api_url=restroom_api_url)

        print(f"\n🚻 正在提取 CSV 廁所資料...")
        csv_restrooms = restroom_processor.extract_from_csv()
        restroom_processor.show_csv_summary()
        if csv_restrooms:
            print(f"\n💾 正在儲存 CSV 廁所 CSV...")
            restroom_processor.save_csv_to_csv("restrooms_source.csv")

        print(f"\n🌐 正在提取 API 廁所資料...")
        api_restrooms = restroom_processor.extract_from_api()
        restroom_processor.show_api_summary()
        if api_restrooms:
            print(f"\n💾 正在儲存 API 廁所 CSV...")
            restroom_processor.save_api_to_csv("restrooms_db.csv")

        # 同步 source 到 db (僅限 restroom 或 all 模式)
        if mode == "restroom" or mode == "all":
            if csv_restrooms:
                print(f"\n🔄 開始分析 source 廁所資料到 API 資料庫...")
                sync_result = restroom_processor.sync_source_to_db()

    if mode in ["shower", "all"]:
        # 處理洗澡點
        shower_api_url = "https://guangfu250923.pttapp.cc/shower_stations"
        shower_processor = ShowerStationProcessor(csv_reader=csv_reader, api_url=shower_api_url)
        
        print(f"\n🚿 正在提取 CSV 洗澡點資料...")
        csv_showers = shower_processor.extract_from_csv()
        shower_processor.show_csv_summary()
        
        if csv_showers:
            print(f"\n💾 正在儲存 CSV 洗澡點 CSV...")
            shower_processor.save_csv_to_csv("shower_stations_source.csv")
            
        print(f"\n🌐 正在提取 API 洗澡點資料...")
        api_showers = shower_processor.extract_from_api()
        shower_processor.show_api_summary()
        if api_showers:
            print(f"\n💾 正在儲存 API 洗澡點 CSV...")
            shower_processor.save_api_to_csv("shower_stations_db.csv")

        # 同步 source 到 db (僅限 shower 或 all 模式)
        if mode == "shower" or mode == "all":
            if csv_showers:
                print(f"\n🔄 開始分析 source 洗澡點資料到 API 資料庫...")
                sync_result = shower_processor.sync_source_to_db()

    print("🎉 處理完成！")

if __name__ == "__main__":
    main()