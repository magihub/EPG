#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
苏州 电视 + 广播 EPG 爬虫（整合版）
"""

from curl_cffi import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re
import datetime
import time
import os
import ssl
import sys
from epg_common import merge_and_write, add_end_times, print_header

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 电视配置
TV_URL = "https://www.csztv.cn/dspd/jmsjb/index.shtml"
TV_MAPPING = {
    "苏州新闻综合": {"id": "苏州1新闻综合", "display": "苏州新闻综合"},
    "苏州社会经济": {"id": "苏州2社会经济", "display": "苏州社会经济"},
    "苏州文化生活": {"id": "苏州3文化生活", "display": "苏州文化生活"},
    "苏州电影娱乐": {"id": "苏州4电影娱乐", "display": "苏州电影娱乐"},
    "苏州生活资讯": {"id": "苏州5生活资讯", "display": "苏州生活资讯"},
}

# 广播配置（原始频率 -> 显示名称）
RADIO_URL = "https://www.csztv.cn/gbpl/jmsjb/index.shtml"
RADIO_MAPPING = {
    "FM91.1":  {"id": "苏州FM91.1", "display": "苏州新闻广播"},
    "AM1080":  {"id": "苏州AM1080", "display": "苏州综合广播"},
    "FM96.5":  {"id": "苏州FM96.5", "display": "苏州生活广播"},
    "AM1521":  {"id": "苏州AM1521", "display": "苏州老年广播"},
    "FM104.8": {"id": "苏州FM104.8", "display": "苏州交通广播"},
    "FM102.8": {"id": "苏州FM102.8", "display": "苏州音乐广播"},
    "FM95.7":  {"id": "苏州FM95.7", "display": "苏州儿童广播"},
    "AM846":   {"id": "苏州AM846", "display": "苏州戏曲广播"},
}

def parse_time(time_str, base_date):
    time_str = time_str.strip().replace('：', ':')
    match = re.match(r'(\d{1,2}):(\d{2})', time_str)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour >= 24:
        hour -= 24
        base_date += datetime.timedelta(days=1)
    if hour < 0 or hour > 23:
        return None
    return datetime.datetime(base_date.year, base_date.month, base_date.day, hour, minute)

def fetch_page(url, retries=3):
    # 更完整的浏览器伪装
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    }    
    
    for attempt in range(1, retries + 1):
        try:
            # 尝试不同的伪装版本
            impersonate = ["chrome110", "chrome120", "safari15_5"][(attempt-1) % 3]
            # print(f"  第 {attempt} 次尝试，伪装: {impersonate}")
            
            resp = requests.get(
                url, 
                headers=headers, 
                timeout=15, 
                impersonate=impersonate,
                verify=False
            )
            resp.encoding = 'utf-8'
            return resp.text
        except Exception as e:
            print(f"  第 {attempt} 次请求失败: {e}")
            if attempt == retries:
                raise
            time.sleep(5 * attempt)  # 递增等待

# -------------------- 电视抓取 --------------------
def get_week_dates():
    today = datetime.datetime.now().date()
    monday = today - datetime.timedelta(days=today.weekday())
    return [monday + datetime.timedelta(days=i) for i in range(7)]

def parse_table(table, base_date):
    programs = []
    rows = table.find_all('tr')[1:]
    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 2:
            continue
        time_str = cells[0].get_text().strip()
        title = cells[1].get_text().strip()
        if not time_str or not title:
            continue
        start_dt = parse_time(time_str, base_date)
        if start_dt:
            programs.append((start_dt, title))
    programs.sort(key=lambda x: x[0])
    return programs

def extract_tv_programs_week(html, channel_index, week_dates):
    soup = BeautifulSoup(html, 'html.parser')
    tablist_id = f"tablist{channel_index+1}"
    tablist_div = soup.find('div', id=tablist_id)
    if not tablist_div:
        all_tablists = soup.find_all('div', class_='tablist')
        if channel_index < len(all_tablists):
            tablist_div = all_tablists[channel_index]
        else:
            print(f"未找到第 {channel_index+1} 个频道的数据块")
            return []
    pic_scroll = tablist_div.find('div', class_='picScroll')
    if not pic_scroll:
        print(f"频道数据块中没有 .picScroll")
        return []
    days = pic_scroll.find_all('li')
    # 星期名称映射（支持周一、星期二等）
    weekday_map = {
        '星期一': 0, '周一': 0,
        '星期二': 1, '周二': 1,
        '星期三': 2, '周三': 2,
        '星期四': 3, '周四': 3,
        '星期五': 4, '周五': 4,
        '星期六': 5, '周六': 5,
        '星期日': 6, '周日': 6
    }
    # 建立日期映射：从表格中提取星期几，找到对应的 week_dates 中的日期
    all_programs = []
    for day_li in days:
        table = day_li.find('table', class_='table_solid')
        if not table:
            continue
        # 获取星期标题（通常是第一行第一列的 th）
        th = table.find('th')
        if not th:
            continue
        weekday_text = th.get_text().strip()
        # 提取星期几数字
        target_weekday = None
        for key, val in weekday_map.items():
            if key in weekday_text:
                target_weekday = val
                break
        if target_weekday is None:
            print(f"无法识别星期: {weekday_text}，跳过")
            continue
        # 找到对应的日期（week_dates 列表索引与星期几一致，因为 week_dates[0]是周一）
        if target_weekday < len(week_dates):
            base_date = week_dates[target_weekday]
        else:
            continue
        programs = parse_table(table, base_date)
        all_programs.extend(programs)
    all_programs.sort(key=lambda x: x[0])
    return add_end_times(all_programs)

# 当天版本：只抓取当前星期几对应的节目
def extract_tv_programs_today(html, channel_index):
    soup = BeautifulSoup(html, 'html.parser')
    tablist_id = f"tablist{channel_index+1}"
    tablist_div = soup.find('div', id=tablist_id)
    if not tablist_div:
        all_tablists = soup.find_all('div', class_='tablist')
        if channel_index < len(all_tablists):
            tablist_div = all_tablists[channel_index]
        else:
            print(f"未找到第 {channel_index+1} 个频道的数据块")
            return []
    pic_scroll = tablist_div.find('div', class_='picScroll')
    if not pic_scroll:
        print(f"频道数据块中没有 .picScroll")
        return []

    days = pic_scroll.find_all('li')
    # 获取当天星期几（周一=0，周日=6）
    today_weekday = datetime.datetime.now().weekday()
    # 确保索引有效
    if today_weekday >= len(days):
        print(f"当天星期索引 {today_weekday} 超出范围，跳过")
        return []

    target_li = days[today_weekday]
    table = target_li.find('table', class_='table_solid')
    if not table:
        print(f"当天表格未找到")
        return []

    base_date = datetime.datetime.now().date()
    programs = parse_table(table, base_date)
    if not programs:
        return []
    # 补充结束时间
    return add_end_times(programs)
    
# -------------------- 广播抓取 --------------------
def refine_title(title, weekday):
    title = title.strip()
    if '、' in title and ('（周六周日）' in title or '（周末）' in title):
        parts = title.split('、', 1)
        left = parts[0].strip()
        right = parts[1].strip()
        right_clean = re.sub(r'（(周六周日|周末)）$', '', right).strip()
        return right_clean if weekday in (5,6) else left
    elif '（周末）' in title:
        return re.sub(r'（周末）$', '', title).strip()
    return title

def parse_radio_programs(html):
    soup = BeautifulSoup(html, 'html.parser')
    event_list = soup.find('ul', class_='event_list')
    if not event_list:
        return {}, []
    radio_divs = event_list.find_all('div', recursive=False)
    base_date = datetime.datetime.now().date()
    weekday = base_date.weekday()
    all_programs = {}
    channel_order = []

    for div in radio_divs:
        h3 = div.find('h3')
        if not h3:
            continue
        raw = h3.get_text().strip()
        match = re.search(r'(FM|AM)\d+(\.\d+)?', raw)
        if not match:
            continue
        raw_id = match.group(0)               # 如 "FM91.1"
        
        # 从映射表中获取 id 和 display
        if raw_id in RADIO_MAPPING:
            ch_id = RADIO_MAPPING[raw_id]["id"]
            display_name = RADIO_MAPPING[raw_id]["display"]
        else:
            # 兼容未定义的频率
            ch_id = "苏州" + raw_id
            display_name = raw_id
        
        if ch_id not in all_programs:
            channel_order.append(ch_id)

        programs = []
        for li in div.find_all('li'):
            time_span = li.find('span')
            if not time_span:
                continue
            time_str = time_span.get_text().strip()
            title_p = li.find('p')
            title = title_p.get_text().strip() if title_p else li.get_text().replace(time_str, '').strip()
            if not title:
                continue
            title = refine_title(title, weekday)
            start_dt = parse_time(time_str, base_date)
            if not start_dt:
                continue
            programs.append({'title': title, 'start_dt': start_dt})

        if not programs:
            continue
        programs.sort(key=lambda x: x['start_dt'])
        enriched = []
        for i, prog in enumerate(programs):
            end_dt = programs[i+1]['start_dt'] if i+1 < len(programs) else prog['start_dt'] + datetime.timedelta(minutes=30)
            enriched.append({'title': prog['title'], 'start_dt': prog['start_dt'], 'end_dt': end_dt})
        all_programs[ch_id] = enriched
        print(f"  正在解析 {display_name} ...")        
        print(f"    获取到 {len(enriched)} 个节目")

    return all_programs, channel_order

# -------------------- 主程序 --------------------
def main():
    start_header()

    # 抓取电视
    print()
    print("抓取苏州电视节目单...")
    tv_html = fetch_page(TV_URL)
    week_dates = get_week_dates()
    tv_channels = []
    tv_programs = []
    for idx, (ch_name, cfg) in enumerate(TV_MAPPING.items()): 
        ch_id = cfg["id"]
        display_name = cfg["display"]
        print(f"  正在解析 {ch_name} ...")
        
        # 获取一周节目单
        # programs = extract_tv_programs_week(tv_html, idx, week_dates)
        
        # 获取当天节目单
        programs = extract_tv_programs_today(tv_html, idx)
                
        if programs:
            tv_channels.append((ch_id, display_name))
            for prog in programs:
                tv_programs.append({
                    'start': prog['start_dt'].strftime("%Y%m%d%H%M%S +0800"),
                    'stop': prog['end_dt'].strftime("%Y%m%d%H%M%S +0800"),
                    'channel': ch_id,
                    'title': prog['title']
                })
            print(f"    获取到 {len(programs)} 个节目")

    # 抓取广播（使用映射表）
    print("\n抓取苏州广播节目单...")
    radio_html = fetch_page(RADIO_URL)
    radio_epg, radio_order = parse_radio_programs(radio_html)
    radio_channels = []
    radio_programs = []
    for ch_id in radio_order:
        if ch_id in radio_epg:
            # 从映射表中查找显示名称（根据 ch_id 中的频率部分）
            # 由于 ch_id 已经是 "苏州FM91.1" 格式，提取频率部分
            raw_id = ch_id[2:] if ch_id.startswith('苏州') else ch_id
            # 从 RADIO_MAPPING 中获取显示名称
            if raw_id in RADIO_MAPPING:
                display = RADIO_MAPPING[raw_id]["display"]
            else:
                display = raw_id  # 回退
            radio_channels.append((ch_id, display))
            for prog in radio_epg[ch_id]:
                radio_programs.append({
                    'start': prog['start_dt'].strftime("%Y%m%d%H%M%S +0800"),
                    'stop': prog['end_dt'].strftime("%Y%m%d%H%M%S +0800"),
                    'channel': ch_id,
                    'title': prog['title']
                })

    # 合并写入
    if tv_programs or radio_programs:
        # 合并电视和广播的频道、节目
        all_new_channels = tv_channels + radio_channels
        all_new_programs = tv_programs + radio_programs
        merge_and_write(start_time, all_new_channels, all_new_programs)
    else:
        print("❌ 未抓取到任何数据")

if __name__ == "__main__":
    main()
