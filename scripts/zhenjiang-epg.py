#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镇江 电视 + 广播 EPG 爬虫（复用浏览器实例）
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
    today = datetime.datetime.now().weekday()
    return today + 1

# ===== 修改：fetch_today_programs 增加重试机制 =====
def fetch_today_programs(channel_name, base_url, driver, retries=2):
    """抓取当天的节目单（支持重试）"""
    day_num = get_today_weekday_num()
    url = f"{base_url}{day_num}.htm"
    
    for attempt in range(1, retries + 1):
        try:
            driver.get(url)
            WebDriverWait(driver, 30).until(  # 超时从15秒增加到30秒
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
                    start_dt = datetime.datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
                    programs.append((start_dt, title))
                except:
                    continue
            programs.sort(key=lambda x: x[0])
            return programs
        except Exception as e:
            print(f"  抓取当天失败 (尝试 {attempt}/{retries}): {e}")
            if attempt == retries:
                return []
            time.sleep(5)  # 重试前等待5秒
    return []

# ==================== 广播抓取 ====================

# ===== 修改：fetch_radio_programs 增加重试机制 =====
def fetch_radio_programs(driver, target_date, retries=2):
    print("\n抓取镇江广播节目单...")
    if "broadcastTvs.html" not in driver.current_url:
        driver.get("https://www.zjmc.tv/broadcastTvs.html?menuCode=zhj004")
        time.sleep(5)
    else:
        driver.refresh()
        time.sleep(3)

    for attempt in range(1, retries + 1):
        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return window.pageData && window.pageData.liveList && window.pageData.liveList.length > 0")
            )
            channels = driver.execute_script("return window.pageData.liveList")
            if not channels:
                print(f"第 {attempt} 次获取频道列表为空")
                if attempt < retries:
                    time.sleep(3)
                    continue
                else:
                    return [], []

            # print(f"获取到 {len(channels)} 个广播频道")
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
                display_name = re.sub(r'^(FM|AM)\d+(\.\d+)?', '', ch_name).strip()
                all_channels.append((ch_code, display_name))
                print(f"  正在抓取 {display_name} ...")

                # 点击频道
                driver.execute_script(f"""
                    var divs = document.querySelectorAll('.swiper-slide');
                    for(var i=0; i<divs.length; i++) {{
                        if(divs[i].getAttribute('data-id') == '{ch_id}') {{
                            divs[i].click();
                            break;
                        }}
                    }}
                """)
                time.sleep(2)

                programs_data = driver.execute_script("return window.pageData.programList")
                if not programs_data:
                    print("    未获取到节目")
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
                    print("    无当天节目")
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
            if attempt < retries:
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
    output_file = "epg.xml"
    week_dates = get_week_dates()
    all_new_channels = []
    all_new_programs = []

    # 配置 Chrome
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--silent')
    chrome_options.add_argument('--ignore-ssl-errors')
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--allow-insecure-localhost')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-background-networking')
    chrome_options.add_argument('--disable-component-update')
    chrome_options.add_argument('--disable-domain-reliability')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-sync')
    chrome_options.add_argument('--disable-breakpad')
    chrome_options.add_argument('--disable-default-apps')
    chrome_options.add_argument('--disable-crash-reporter')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    # ========== 添加代理（仅在 GitHub Actions 环境中） ==========
    # ===== 新增：代理配置 =====
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        proxy_ip = os.environ.get('TINY_PROXY_IP')
        proxy_port = os.environ.get('TINY_PROXY_PORT')
        if proxy_ip and proxy_port:
            chrome_options.add_argument(f'--proxy-server=http://{proxy_ip}:{proxy_port}')
            print(f"已为 Chrome 设置代理: {proxy_ip}:{proxy_port}")
        else:
            print("未设置代理环境变量 TINY_PROXY_IP/TINY_PROXY_PORT")
    else:
        print("本地运行，不设置代理")
    # =========================================================

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(30)
    
    try:
        # ---------- 电视 ----------
        print()
        print("抓取镇江电视节目单...")    
        
        for ch_name, base_url in TV_CHANNELS.items():
            print(f"  正在解析 {ch_name} ...")
            
            # 仅抓取当天节目单（带重试）
            day_programs = fetch_today_programs(ch_name, base_url, driver, retries=2)
            if day_programs:
                day_programs.sort(key=lambda x: x[0])
                enriched = add_end_times(day_programs)
                all_new_channels.append((ch_name, ch_name))
                for prog in enriched:
                    all_new_programs.append({
                        'start': prog['start_dt'].strftime("%Y%m%d%H%M%S +0800"),
                        'stop': prog['end_dt'].strftime("%Y%m%d%H%M%S +0800"),
                        'channel': ch_name,
                        'title': prog['title']
                    })
                print(f"    获取到 {len(enriched)} 个节目")
            else:
                print(f"    未抓取到任何数据")

        # ---------- 广播 ----------
        # 广播节目单通常是当天数据，使用今天日期（带重试）
        radio_channels, radio_programs = fetch_radio_programs(driver, datetime.datetime.now().date(), retries=2)
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