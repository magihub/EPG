#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
苏州广电 EPG 爬虫（电视 + 广播整合版）—— 追加模式，广播ID加苏州前缀
"""

import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta
import re
import time
import os

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 电视配置
TV_URL = "https://www.csztv.cn/dspd/jmsjb/index.shtml"
TV_CHANNELS = [
    "苏州新闻综合",
    "苏州社会经济",
    "苏州文化生活",
    "苏州电影娱乐",
    "苏州生活资讯"
]

# 广播配置（原始频率 -> 显示名称）
RADIO_URL = "https://www.csztv.cn/gbpl/jmsjb/index.shtml"
RADIO_DISPLAY_RAW = {
    'FM91.1':  '苏州新闻广播',
    'AM1080':  '苏州综合广播',
    'FM96.5':  '苏州生活广播',
    'AM1521':  '苏州老年广播',
    'FM104.8': '苏州交通广播',
    'FM102.8': '苏州音乐广播',
    'FM95.7':  '苏州儿童广播',
    'AM846':   '苏州戏曲广播'
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
        base_date += timedelta(days=1)
    if hour < 0 or hour > 23:
        return None
    return datetime(base_date.year, base_date.month, base_date.day, hour, minute)

def fetch_page(url):
    for attempt in range(1, 3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.encoding = 'utf-8'
            return resp.text
        except requests.RequestException as e:
            print(f"第 {attempt} 次请求失败: {e}")
            if attempt == 2:
                raise
            time.sleep(3)

# -------------------- 电视抓取 --------------------
def get_week_dates():
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    return [monday + timedelta(days=i) for i in range(7)]

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

def add_end_times(programs):
    result = []
    for i, (start, title) in enumerate(programs):
        end = programs[i+1][0] if i+1 < len(programs) else start + timedelta(minutes=30)
        result.append({'title': title, 'start_dt': start, 'end_dt': end})
    return result

def extract_tv_programs(html, channel_index, week_dates):
    soup = BeautifulSoup(html, 'html.parser')
    tablist_id = f"tablist{channel_index+1}"
    tablist_div = soup.find('div', id=tablist_id)
    if not tablist_div:
        all_tablists = soup.find_all('div', class_='tablist')
        if channel_index < len(all_tablists):
            tablist_div = all_tablists[channel_index]
        else:
            return []
    pic_scroll = tablist_div.find('div', class_='picScroll')
    if not pic_scroll:
        return []
    days = pic_scroll.find_all('li')
    all_programs = []
    for idx, day_li in enumerate(days):
        if idx >= len(week_dates):
            break
        base_date = week_dates[idx]
        table = day_li.find('table', class_='table_solid')
        if table:
            all_programs.extend(parse_table(table, base_date))
    all_programs.sort(key=lambda x: x[0])
    return add_end_times(all_programs)

# -------------------- 广播抓取（ID加苏州前缀）--------------------
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
    base_date = datetime.now().date()
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
        ch_id = "苏州" + raw_id                # 加上前缀
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
            end_dt = programs[i+1]['start_dt'] if i+1 < len(programs) else prog['start_dt'] + timedelta(minutes=30)
            enriched.append({'title': prog['title'], 'start_dt': prog['start_dt'], 'end_dt': end_dt})
        all_programs[ch_id] = enriched
        print(f"  广播 {ch_id}: {len(enriched)} 个节目")

    return all_programs, channel_order

# -------------------- 合并现有XML --------------------
def parse_existing_xml(filepath):
    if not os.path.exists(filepath):
        return {}, []
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        channels = {}
        for ch in root.findall('channel'):
            ch_id = ch.get('id')
            dn = ch.find('display-name')
            if ch_id:
                channels[ch_id] = dn.text if dn is not None else ch_id
        programs = []
        for prog in root.findall('programme'):
            start = prog.get('start')
            stop = prog.get('stop')
            channel = prog.get('channel')
            title_elem = prog.find('title')
            title = title_elem.text if title_elem is not None else ''
            if start and stop and channel:
                programs.append({'start': start, 'stop': stop, 'channel': channel, 'title': title})
        return channels, programs
    except Exception as e:
        print(f"解析现有XML失败: {e}")
        return {}, []

def merge_and_write(output_file, tv_channels, tv_programs, radio_channels, radio_programs):
    # 读取现有
    exist_channels, exist_programs = parse_existing_xml(output_file)

    # 合并频道（去重）
    all_channels = dict(exist_channels)
    for ch_id, disp in tv_channels:
        if ch_id not in all_channels:
            all_channels[ch_id] = disp
    for ch_id, disp in radio_channels:
        if ch_id not in all_channels:
            all_channels[ch_id] = disp

    # 合并节目
    all_programs = exist_programs + tv_programs + radio_programs

    # 生成XML
    tv = ET.Element("tv")
    tv.set("generator-info-name", "苏州EPG合并至现有XML文件中")
    for ch_id, disp in all_channels.items():
        ch = ET.SubElement(tv, "channel", id=ch_id)
        dn = ET.SubElement(ch, "display-name", lang="zh")
        dn.text = disp
    for prog in all_programs:
        programme = ET.SubElement(tv, "programme",
                                  start=prog['start'],
                                  stop=prog['stop'],
                                  channel=prog['channel'])
        title_elem = ET.SubElement(programme, "title", lang="zh")
        title_elem.text = prog['title']

    xml_str = ET.tostring(tv, encoding='utf-8')
    dom = minidom.parseString(xml_str)
    pretty = dom.toprettyxml(indent="  ")
    pretty = pretty.replace('<?xml version="1.0" ?>', '<?xml version="1.0" encoding="UTF-8"?>')
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(pretty)
    print(f"✅ 合并保存至 {output_file} (总频道: {len(all_channels)}, 总节目: {len(all_programs)})")

# -------------------- 主程序 --------------------
def main():
    output_file = "epg.xml"

    # 抓取电视
    print("=" * 50)
    print("抓取苏州电视节目单...")
    tv_html = fetch_page(TV_URL)
    week_dates = get_week_dates()
    tv_channels = []
    tv_programs = []
    for idx, ch_name in enumerate(TV_CHANNELS):
        print(f"正在解析 {ch_name} ...")
        programs = extract_tv_programs(tv_html, idx, week_dates)
        if programs:
            tv_channels.append((ch_name, ch_name))
            for prog in programs:
                tv_programs.append({
                    'start': prog['start_dt'].strftime("%Y%m%d%H%M%S +0800"),
                    'stop': prog['end_dt'].strftime("%Y%m%d%H%M%S +0800"),
                    'channel': ch_name,
                    'title': prog['title']
                })
            print(f"  获取到 {len(programs)} 个节目")

    # 抓取广播（ID已加苏州前缀）
    print("\n" + "=" * 50)
    print("抓取苏州广播节目单...")
    radio_html = fetch_page(RADIO_URL)
    radio_epg, radio_order = parse_radio_programs(radio_html)
    radio_channels = []
    radio_programs = []
    for ch_id in radio_order:
        if ch_id in radio_epg:
            # 显示名称：从原始映射中获取（ch_id去掉"苏州"前缀）
            raw_id = ch_id[2:]   # 去掉"苏州"前缀，如 "苏州FM91.1" -> "FM91.1"
            display = RADIO_DISPLAY_RAW.get(raw_id, raw_id)
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
        merge_and_write(output_file, tv_channels, tv_programs, radio_channels, radio_programs)
        print("\n🎉 苏州数据已追加到 epg.xml")
    else:
        print("❌ 未抓取到任何数据")

if __name__ == "__main__":
    main()