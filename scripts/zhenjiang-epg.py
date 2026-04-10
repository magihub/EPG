#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镇江电视台电视 + 广播 EPG 爬虫（复用浏览器实例，含计时）
"""

import datetime
import time
import os
import sys
import re
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from epg_common import merge_and_write, add_end_times

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from epg_common import merge_and_write

# ==================== 电视配置 ====================
TV_CHANNELS = {
    "镇江新闻综合": "https://epg.sports8.cc/2118/",
    "镇江教育民生": "https://epg.sports8.cc/2119/",
    # "镇江资讯频道": "https://epg.sports8.cc/2120/",
    # "镇江影视频道": "https://epg.sports8.cc/2121/",
}

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

def get_week_dates():
    today = datetime.datetime.now().date()
    monday = today - datetime.timedelta(days=today.weekday())
    return [monday + datetime.timedelta(days=i) for i in range(7)]

# ==================== 电视抓取 ====================
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

def get_today_weekday_num():
    """返回今天对应的周几数字（周一=1, 周日=7）"""
    today = datetime.datetime.now().weekday()  # 0=周一, 6=周日
    return today + 1

def fetch_today_programs(channel_name, base_url, driver):
    """抓取当天的节目单"""
    day_num = get_today_weekday_num()
    url = f"{base_url}{day_num}.htm"
    # print(f"  抓取当天 (周{day_num}) ...")
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div#epgInfo"))
        )
        items = driver.find_elements(By.CSS_SELECTOR, "div#epgInfo p")
        programs = []
        for item in items:
            time_elem = item.find_element(By.CSS_SELECTOR, "em.time")
            time_str = time_elem.text.strip()
            title = item.text.replace(time_str, '').strip()
            if not title:
                continue
            try:
                hour, minute = map(int, time_str.split(':'))
                # 使用今天的日期
                start_dt = datetime.datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
                programs.append((start_dt, title))
            except:
                continue
        programs.sort(key=lambda x: x[0])
        return programs
    except Exception as e:
        print(f"  抓取当天失败: {e}")
        return []
        
       
# ==================== 广播抓取 ====================

def fetch_radio_programs(driver, target_date):
    print("\n抓取镇江广播节目单...")
    # 确保当前页面是广播页
    current_url = driver.current_url
    if "broadcastTvs.html" not in current_url:
        driver.get("https://www.zjmc.tv/broadcastTvs.html?menuCode=zhj004")
        time.sleep(5)
    else:
        driver.refresh()
        time.sleep(3)

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        print(f"尝试 {attempt}/{max_attempts} 获取广播数据...")
        try:
            # 等待 jQuery 加载
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return typeof jQuery !== 'undefined'")
            )
            # 等待 Vue 数据加载
            WebDriverWait(driver, 20).until(
                lambda d: d.execute_script("return window.pageData && window.pageData.liveList && window.pageData.liveList.length > 0")
            )
            print("页面 Vue 数据已加载")

            # 获取频道列表（优先从 Vue 数据取）
            channels_js = """
                if (window.pageData && window.pageData.liveList) {
                    return window.pageData.liveList;
                } else {
                    var result = [];
                    var param = {menuId: 'zhj004', idx: 0, size: 50};
                    var request = {service: 'getMenuContentList', params: JSON.stringify(param)};
                    $.ajax({
                        url: window.staticConfig.apiUrl,
                        type: 'POST',
                        data: request,
                        async: false,
                        success: function(data) {
                            if (data.state === 1000 && data.data && data.data.rows) {
                                result = data.data.rows;
                            }
                        }
                    });
                    return result;
                }
            """
            channels = driver.execute_script(channels_js)
            if not channels:
                print(f"第 {attempt} 次获取频道列表为空")
                if attempt < max_attempts:
                    time.sleep(3)
                    continue
                else:
                    return [], []

            print(f"获取到 {len(channels)} 个广播频道")
            all_channels = []
            all_programs = []

            for ch in channels:
                ch_id = ch['id']
                ch_name = ch['title']
                freq_match = re.search(r'(FM|AM)\d+(\.\d+)?', ch_name)
                if freq_match:
                    freq = freq_match.group(0)
                    ch_code = f"镇江{freq}"
                else:
                    ch_code = ch_name
                all_channels.append((ch_code, ch_name))
                
                # 去掉频率前缀，例如 "FM96.3镇江文艺广播" -> "镇江文艺广播"
                display_name = re.sub(r'^(FM|AM)\d+(\.\d+)?', '', ch_name).strip()
                print(f"  正在解析 {display_name} ...")

                # 获取节目单（使用 requestExtApi）
                programs_js = f"""
                    var result = [];
                    var param = {{id: '{ch_id}'}};
                    var requestData = {{service: 'getBroadcastList', params: JSON.stringify(param)}};
                    if (typeof requestExtApi === 'function') {{
                        requestExtApi({{
                            url: window.staticConfig.apiUrl,
                            data: requestData,
                            success: function(data) {{
                                if (data.state === 1000 && data.data) {{
                                    result = data.data;
                                }}
                            }}
                        }});
                    }}
                    return result;
                """
                programs_data = driver.execute_script(programs_js)
                if not programs_data:
                    print(f"    未获取到节目")
                    continue

                programs = []
                for item in programs_data:
                    start_str = item.get('startTime')
                    end_str = item.get('endTime')
                    title = item.get('programName', '').strip()
                    if not start_str or not end_str or not title:
                        continue
                    try:
                        start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                        end_dt = datetime.datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                        if start_dt.date() == target_date:
                            programs.append((start_dt, title, end_dt))
                    except:
                        continue
                if not programs:
                    print(f"    无当天节目")
                    continue
                programs.sort(key=lambda x: x[0])
                for start_dt, title, end_dt in programs:
                    all_programs.append({
                        'start': start_dt.strftime("%Y%m%d%H%M%S +0800"),
                        'stop': end_dt.strftime("%Y%m%d%H%M%S +0800"),
                        'channel': ch_code,
                        'title': title
                    })
                print(f"    获取到 {len(programs)} 个节目")

            return all_channels, all_programs

        except Exception as e:
            print(f"第 {attempt} 次广播抓取失败: {e}")
            if attempt < max_attempts:
                print("等待 5 秒后重试...")
                time.sleep(5)
                driver.refresh()
            else:
                print("重试次数已用完，广播抓取失败")
                return [], []

    return [], []
    
# ==================== 主函数 ====================
def main():
    print()
    print("=" * 50)
    print(f"        开始执行时间： {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
    chrome_options.add_argument('--disable-background-networking')  # 新增
    chrome_options.add_argument('--disable-component-update')      # 新增
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(options=chrome_options)
    try:
        # ---------- 电视 ----------
    
        print()
        print("抓取镇江电视节目单...")    
        
        for ch_name, base_url in TV_CHANNELS.items():
            print(f"正在解析 {ch_name} ...")
            
            # 抓取一周节目单
            # weekly_programs = fetch_week_programs(ch_name, base_url, week_dates, driver)
            # if weekly_programs:
            #     weekly_programs.sort(key=lambda x: x[0])
            #     enriched = add_end_times(weekly_programs)
            
            # 仅抓取当天节目单
            day_programs = fetch_today_programs(ch_name, base_url, driver)
            if day_programs:
                day_programs.sort(key=lambda x: x[0])
                enriched = add_end_times(day_programs)
            # 下同
            
                all_new_channels.append((ch_name, ch_name))
                for prog in enriched:
                    all_new_programs.append({
                        'start': prog['start_dt'].strftime("%Y%m%d%H%M%S +0800"),
                        'stop': prog['end_dt'].strftime("%Y%m%d%H%M%S +0800"),
                        'channel': ch_name,
                        'title': prog['title']
                    })
                print(f"  获取到 {len(enriched)} 个节目")
            else:
                print(f"  未抓取到任何数据")

        # ---------- 广播 ----------
        # 广播节目单通常是当天数据，使用今天日期
        radio_channels, radio_programs = fetch_radio_programs(driver, datetime.datetime.now().date())
        all_new_channels.extend(radio_channels)
        all_new_programs.extend(radio_programs)

    finally:
        driver.quit()

    if all_new_programs:
        merge_and_write(output_file, all_new_channels, all_new_programs)
        elapsed = time.time() - start_time
        print(f"\n🎉 抓取完成！总耗时: {elapsed:.2f} 秒")
    else:
        print("❌ 未抓取到任何数据")

if __name__ == "__main__":
    main()