#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镇江电视台 EPG 爬虫（新闻频道 + 民生频道 + 资讯频道 + 影视频道）
基于 epg.sports8.cc 的 HTML 结构解析
读取现有 epg.xml，替换镇江频道数据，保留其他频道，输出到 epg.xml
"""

import requests
import re
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import ssl
import urllib3
import os
from epg_common import parse_existing_xml, merge_and_write
from epg_common import add_end_times, parse_existing_xml, merge_and_write

# 抑制SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 禁用SSL验证（因为证书过期）
ssl._create_default_https_context = ssl._create_unverified_context

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 频道配置：频道名称 -> (基础URL, 频道ID用于XML, 频道显示名称)
CHANNELS = {
    "镇江新闻综合": {
        "base_url": "https://epg.sports8.cc/2118/",
        "channel_id": "镇江新闻综合"
    },
    "镇江教育民生": {
        "base_url": "https://epg.sports8.cc/2119/",
        "channel_id": "镇江教育民生"
    },
    "镇江资讯频道": {
        "base_url": "https://epg.sports8.cc/2120/",
        "channel_id": "镇江资讯频道"
    },
    "镇江影视频道": {
        "base_url": "https://epg.sports8.cc/2121/",
        "channel_id": "镇江影视频道"
    }
}

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

def fetch_daily_program(url, date_obj, retries=2):
    """抓取某一天的节目单，支持重试"""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10, verify=False)
            resp.encoding = 'utf-8'
            html = resp.text
            # 继续解析...
            pattern = re.compile(r'<p class="pc_[12]"><em class="time">(\d{2}:\d{2})</em>(.*?)</p>')
            matches = re.findall(pattern, html)
            programs = []
            for time_str, title in matches:
                title = title.strip()
                if not title:
                    continue
                try:
                    hour = int(time_str.split(':')[0])
                    minute = int(time_str.split(':')[1])
                    start_dt = datetime(date_obj.year, date_obj.month, date_obj.day, hour, minute)
                    programs.append((start_dt, title))
                except:
                    continue
            programs.sort(key=lambda x: x[0])
            return programs
        except Exception as e:
            print(f"第 {attempt} 次抓取失败 {url}: {e}")
            if attempt == retries:
                return []
            time.sleep(3)


def main():
    output_file = "epg.xml"

    # 1. 抓取镇江数据
    print("=" * 50)
    print("抓取镇江电视台节目单...")
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    week_dates = [monday + timedelta(days=i) for i in range(7)]

    zhenjiang_channels = []
    zhenjiang_programs = []

    for ch_name, cfg in CHANNELS.items():
        print(f"\n正在抓取 {ch_name} ...")
        weekly_programs = []
        for day_offset in range(7):
            day_num = day_offset + 1
            url = f"{cfg['base_url']}{day_num}.htm"
            date_obj = week_dates[day_offset]
            day_programs = fetch_daily_program(url, date_obj)
            if day_programs:
                day_programs_with_end = add_end_times(day_programs)
                weekly_programs.extend(day_programs_with_end)
                print(f"  {WEEKDAY_NAMES[day_offset]}: {len(day_programs)} 个节目")
            else:
                print(f"  {WEEKDAY_NAMES[day_offset]}: 无数据")
            time.sleep(0.5)
        if weekly_programs:
            ch_id = cfg['channel_id']
            zhenjiang_channels.append((ch_id, ch_id))  # ID和显示名相同
            for prog in weekly_programs:
                zhenjiang_programs.append({
                    'start': prog['start_dt'].strftime("%Y%m%d%H%M%S +0800"),
                    'stop': prog['end_dt'].strftime("%Y%m%d%H%M%S +0800"),
                    'channel': ch_id,
                    'title': prog['title']
                })
            print(f"{ch_name} 共抓取 {len(weekly_programs)} 个电视节目")
        else:
            print(f"{ch_name} 未抓取到任何数据")

    # 2. 合并写入
    if zhenjiang_programs:
        merge_and_write(output_file, zhenjiang_channels, zhenjiang_programs)
        print("\n🎉 镇江数据已合并到 epg.xml")
    else:
        print("❌ 未抓取到镇江数据，文件未更新")

if __name__ == "__main__":
    main()