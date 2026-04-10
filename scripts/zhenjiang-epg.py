#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镇江电视台电视 EPG 爬虫（复用浏览器实例，含计时）
"""

import datetime
import time
import os
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from epg_common import merge_and_write

TV_CHANNELS = {
    "镇江新闻综合": "https://epg.sports8.cc/2118/",
    "镇江教育民生": "https://epg.sports8.cc/2119/",
    "镇江资讯频道": "https://epg.sports8.cc/2120/",
    "镇江影视频道": "https://epg.sports8.cc/2121/",
}

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

def get_week_dates():
    today = datetime.datetime.now().date()
    monday = today - datetime.timedelta(days=today.weekday())
    return [monday + datetime.timedelta(days=i) for i in range(7)]

def fetch_week_programs(channel_name, base_url, week_dates, driver):
    """使用同一个 driver 抓取某频道一周的节目单"""
    programs = []
    for idx, date_obj in enumerate(week_dates):
        day_num = idx + 1
        url = f"{base_url}{day_num}.htm"
        try:
            driver.get(url)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div#epgInfo"))
            )
            items = driver.find_elements(By.CSS_SELECTOR, "div#epgInfo p")
            day_progs = []
            for item in items:
                time_elem = item.find_element(By.CSS_SELECTOR, "em.time")
                time_str = time_elem.text.strip()
                title = item.text.replace(time_str, '').strip()
                if not title:
                    continue
                try:
                    hour, minute = map(int, time_str.split(':'))
                    start_dt = datetime.datetime(date_obj.year, date_obj.month, date_obj.day, hour, minute)
                    day_progs.append((start_dt, title))
                except:
                    continue
            day_progs.sort(key=lambda x: x[0])
            programs.extend(day_progs)
            print(f"  {WEEKDAY_NAMES[idx]}: {len(day_progs)} 个节目")
        except Exception as e:
            print(f"  {WEEKDAY_NAMES[idx]}: 失败 - {e}")
        time.sleep(0.3)
    return programs

def add_end_times(programs):
    result = []
    for i, (start, title) in enumerate(programs):
        if i + 1 < len(programs):
            end = programs[i+1][0]
        else:
            end = start + datetime.timedelta(minutes=30)
        result.append({'title': title, 'start_dt': start, 'end_dt': end})
    return result

def main():
    print()
    print("=" * 50)
    print(f"      开始执行时间（UTC）: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    start_time = time.time()
    output_file = "epg.xml"   # 输出到根目录
    week_dates = get_week_dates()
    all_new_channels = []
    all_new_programs = []

    # 配置 Chrome
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--silent')
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--ignore-ssl-errors')
    chrome_options.add_argument('--allow-insecure-localhost')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(options=chrome_options)
    try:
        for ch_name, base_url in TV_CHANNELS.items():
            print(f"\n正在抓取 {ch_name} ...")
            weekly_programs = fetch_week_programs(ch_name, base_url, week_dates, driver)
            if weekly_programs:
                weekly_programs.sort(key=lambda x: x[0])
                enriched = add_end_times(weekly_programs)
                all_new_channels.append((ch_name, ch_name))
                for prog in enriched:
                    all_new_programs.append({
                        'start': prog['start_dt'].strftime("%Y%m%d%H%M%S +0800"),
                        'stop': prog['end_dt'].strftime("%Y%m%d%H%M%S +0800"),
                        'channel': ch_name,
                        'title': prog['title']
                    })
                print(f"{ch_name} 共抓取 {len(enriched)} 个节目")
            else:
                print(f"{ch_name} 未抓取到任何数据")
    finally:
        driver.quit()

    if all_new_programs:
        merge_and_write(output_file, all_new_channels, all_new_programs)
        elapsed = time.time() - start_time
        print(f"\n🎉 抓取完成！总耗时: {elapsed:.2f} 秒")
    else:
        print("❌ 未抓取到镇江电视数据")

if __name__ == "__main__":
    main()