#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
南通广播电视台 电视+广播 EPG 抓取工具
使用通用合并函数，频道ID规范命名
"""

import os
import json
import datetime
import time
from typing import List, Dict, Any
from curl_cffi import requests
from epg_common import merge_and_write   # 导入公共合并函数

# ==================== 配置区域 ====================
API_URL = "https://web.ntjoy.com/website/external/externalService"

HEADERS = {
    'accept': 'application/json, text/javascript, */*; q=0.01',
    'accept-encoding': 'gzip, deflate, br, zstd',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'origin': 'https://www.ntjoy.com',
    'referer': 'https://www.ntjoy.com/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0',
}

MENU_CONFIGS = [
    {"menu_code": "ntw005", "name": "电视", "channel_type": "tv"},
    {"menu_code": "ntw006", "name": "广播", "channel_type": "radio"}
]

# ==================== 频道ID映射表（原始ID -> 规范ID和显示名称） ====================
CHANNEL_MAPPING = {
    # 电视
    "ff8081818bcbe7c2018bcc9bf4f20015": {"id": "南通新闻综合", "display": "南通新闻综合"},
    "ff8081818bcbe7c2018bcc9cb7390018": {"id": "南通社教频道", "display": "南通社会教育"},
    "ff8081818bcbe7c2018bcc9d12f0001b": {"id": "南通公共频道", "display": "南通公共崇川"},
    # 广播
    "ff8081818bcbe7c2018bcc97451e0009": {"id": "南通FM97.0", "display": "南通综合广播"},
    "ff8081818bcbe7c2018bcc9a0de6000c": {"id": "南通FM92.9", "display": "南通交通广播"},
    "ff8081818bcbe7c2018bcc9afba60012": {"id": "南通FM106.1", "display": "南通经济广播"},
    "ff8081818bcbe7c2018bcc9a82f4000f": {"id": "南通FM91.8", "display": "南通生活广播"},
}

def get_mapped_channel(raw_id: str, raw_name: str = "", raw_cover: str = ""):
    """根据原始ID返回映射后的 (规范ID, 显示名称, 封面URL)"""
    if raw_id in CHANNEL_MAPPING:
        mapping = CHANNEL_MAPPING[raw_id]
        return mapping["id"], mapping["display"], raw_cover
    else:
        print(f"警告：未找到映射的频道 ID={raw_id}, 名称={raw_name}，将使用原始ID")
        return raw_id, raw_name, raw_cover

# ==================== API 请求 ====================
def fetch_api(service: str, params_dict: Dict, retries=2) -> Any:
    payload = {
        'service': service,
        'params': json.dumps(params_dict)
    }
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(API_URL, headers=HEADERS, data=payload, timeout=15, impersonate="chrome120")
            if response.status_code == 200:
                result = response.json()
                if result.get('state') == 1000:
                    return result.get('data')
                else:
                    print(f"  API返回错误 (state: {result.get('state')}): {result.get('message', '未知错误')}")
                    return None
            else:
                print(f"  HTTP请求失败，状态码: {response.status_code}")
                if attempt == retries:
                    return None
                time.sleep(3)
        except Exception as e:
            print(f"  第 {attempt} 次请求API时发生异常: {e}")
            if attempt == retries:
                return None
            time.sleep(3)
    return None

def fetch_channels(menu_code: str) -> List[Dict]:
    print(f"\n正在获取{menu_code}的频道列表...")
    params = {'menuId': menu_code, 'idx': 0, 'size': 50}
    data = fetch_api("getMenuContentList", params)
    channels = []
    if data and isinstance(data, dict) and 'rows' in data:
        for item in data['rows']:
            raw_id = item.get('id')
            raw_name = item.get('title', '未知频道')
            raw_cover = item.get('coverUrl', '')
            ch_id, ch_display, ch_cover = get_mapped_channel(raw_id, raw_name, raw_cover)
            channels.append({
                'id': ch_id,
                'name': ch_display,
                'type': 'tv' if menu_code == 'ntw005' else 'radio',
                'cover': ch_cover,
                'raw_id': raw_id   # 保留原始ID用于节目请求
            })
            print(f"  发现频道: {ch_display} (ID: {ch_id})")
        print(f"成功获取 {len(channels)} 个频道。")
    else:
        print(f"获取频道列表失败，返回数据: {data}")
    return channels

def fetch_channel_programs(raw_channel_id: str, channel_name: str) -> List[Dict]:
    print(f"  正在获取 {channel_name} 的节目单...")
    params = {'id': raw_channel_id}
    data = fetch_api("getBroadcastList", params)
    programs = []
    if data and isinstance(data, list):
        for item in data:
            start_time_str = item.get('startTime')
            end_time_str = item.get('endTime')
            if not start_time_str or not end_time_str:
                continue
            try:
                dt = datetime.datetime.strptime(start_time_str.strip(), "%Y-%m-%d %H:%M:%S")
                start_formatted = dt.strftime("%Y%m%d%H%M%S +0800")
                dt = datetime.datetime.strptime(end_time_str.strip(), "%Y-%m-%d %H:%M:%S")
                end_formatted = dt.strftime("%Y%m%d%H%M%S +0800")
            except:
                continue
            program = {
                'title': item.get('programName', '未知节目'),
                'start_time': start_formatted,
                'end_time': end_formatted,
                'desc': item.get('remark', ''),
                'status': item.get('status', 0),
            }
            if program['title'] != '未知节目':
                programs.append(program)
        print(f"    成功获取 {len(programs)} 条节目数据。")
    else:
        print(f"    未获取到节目数据或数据格式错误。")
    return programs

# ==================== 主任务 ====================
def main():
    print()
    print("=" * 50)
    print(f"      开始执行时间（UTC）: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    output_file = "epg.xml"    
        
    start_time = time.time()
    all_new_channels = []   # 存储 (ch_id, display_name)
    all_new_programs = []   # 存储节目字典
    
    for config in MENU_CONFIGS:
        print(f"\n--- 开始处理 {config['name']} 频道 ---")
        channels = fetch_channels(config['menu_code'])
        if not channels:
            print(f"⚠️ 未能获取 {config['name']} 频道列表，跳过。")
            continue
        
        for channel in channels:
            # 记录新频道（规范ID，显示名称）
            all_new_channels.append((channel['id'], channel['name']))
            # 抓取节目（使用原始ID请求）
            programs = fetch_channel_programs(channel['raw_id'], channel['name'])
            for prog in programs:
                all_new_programs.append({
                    'start': prog['start_time'],
                    'stop': prog['end_time'],
                    'channel': channel['id'],
                    'title': prog['title']
                })
            time.sleep(0.3)
    
    if all_new_programs:

        # 调用公共合并函数（紧凑输出，自动保留原有 generator-info-name）
        merge_and_write(output_file, all_new_channels, all_new_programs)
        elapsed = time.time() - start_time
        print(f"\n🎉 抓取完成！总耗时: {elapsed:.2f} 秒")
        return 0
    else:
        print("\n⚠️ 未抓取到任何节目数据，请检查网络或接口。")
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)