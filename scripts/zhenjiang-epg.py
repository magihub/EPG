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
from selenium.common.exceptions import TimeoutException
from epg_common import merge_and_write, add_end_times
from curl_cffi import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ==================== 电视配置 ====================
TV_MAPPING = {
    "镇江新闻综合": {"id": "镇江1新闻综合", "url": "https://epg.sports8.cc/2118/", "display": "镇江新闻综合"},
    "镇江教育民生": {"id": "镇江2教育民生", "url": "https://epg.sports8.cc/2119/", "display": "镇江教育民生"},
    # "镇江资讯频道": {"id": "镇江3资讯频道", "url": "https://epg.sports8.cc/2120/", "display": "镇江资讯频道"},
    # "镇江影视频道": {"id": "镇江4影视频道", "url": "https://epg.sports8.cc/2121/", "display": "镇江影视频道"},
}

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

def get_week_dates():
    today = datetime.datetime.now().date()
    monday = today - datetime.timedelta(days=today.weekday())
    return [monday + datetime.timedelta(days=i) for i in range(7)]

# ==================== 电视抓取 ====================
def fetch_week_programs(channel_name, base_url, week_dates, driver, retries=2):
    """使用同一个 driver 抓取某频道一周的节目单（支持单天重试）"""
    programs = []
    for idx, date_obj in enumerate(week_dates):
        day_num = idx + 1
        url = f"{base_url}{day_num}.htm"
        for attempt in range(1, retries + 1):
            try:
                driver.get(url)
                WebDriverWait(driver, 30).until(  # 超时增加到30秒
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
                break  # 成功则跳出重试循环
            except Exception as e:
                print(f"  {WEEKDAY_NAMES[idx]} 抓取失败 (尝试 {attempt}/{retries}): {e}")
                if attempt == retries:
                    print(f"  {WEEKDAY_NAMES[idx]}: 最终失败，跳过")
                else:
                    time.sleep(3)  # 重试前等待
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
            if attempt > 1:
                driver.get(url)  # 重试前刷新页面
                time.sleep(2)            
            driver.get(url)
            WebDriverWait(driver, 60).until(  # 超时从15秒增加到30秒
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

RADIO_MAPPING = {
    "FM96.3": {"id": "镇江FM96.3", "display": "镇江文艺广播"},
    "FM88.8": {"id": "镇江FM88.8", "display": "镇江交通广播"},
    "FM104":  {"id": "镇江FM104", "display": "镇江综合广播"},
}

# ===== 修改：fetch_radio_programs 增加重试机制 =====
def fetch_radio_programs(driver, target_date, retries=2):   
    for attempt in range(1, retries + 1):
        try:
            # 访问广播页面（重试时重新加载）
            driver.get("https://www.zjmc.tv/broadcastTvs.html?menuCode=zhj004")
            driver.set_page_load_timeout(90)
            
            # 等待页面加载完成
            WebDriverWait(driver, 60).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            # 等待 Vue 数据加载
            WebDriverWait(driver, 120).until(
                lambda d: d.execute_script("return window.pageData && window.pageData.liveList && window.pageData.liveList.length > 0")
            )
            print("页面 Vue 数据已加载")
            
            # 获取频道列表
            channels = driver.execute_script("return window.pageData.liveList")
            if not channels:
                print("未获取到频道列表")
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
                    if freq in RADIO_MAPPING:
                        ch_code = RADIO_MAPPING[freq]["id"]
                        display_name = RADIO_MAPPING[freq]["display"]
                    else:
                        ch_code = f"镇江{freq}"
                        display_name = re.sub(r'^(FM|AM)\d+(\.\d+)?', '', ch_name).strip()                
                
                all_channels.append((ch_code, display_name))
                print(f"  正在抓取 {display_name} ...")
                
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
            print(f"异常类型: {type(e).__name__}, 消息: {e}")
            if attempt < retries:
                print("等待 5 秒后重试...")
                time.sleep(5)
                # 改为重新加载页面，而不是 refresh
                # driver.refresh()  # 已注释
            else:
                print("重试次数已用完，广播抓取失败")
                return [], []
    
    return [], []

# ==================== 主函数 ====================

def test_tiny_proxy(ip, port):
    for attempt in range(2):
        try:
            proxies = {"http": f"http://{ip}:{port}", "https": f"http://{ip}:{port}"}
            resp = requests.get("https://www.zjmc.tv", proxies=proxies, timeout=30, verify=False, impersonate="chrome120")
            if resp.status_code == 200:
                print(f"代理测试成功 (HTTP {resp.status_code})")
                return True
            else:
                print(f"代理测试失败 (HTTP {resp.status_code})")
        except Exception as e:
            print(f"代理测试异常 (尝试 {attempt+1}): {e}")
            if attempt == 0:
                time.sleep(5)
            else:
                return False
    return False
        
def main():
    print()
    print("=" * 50)
    print(f"        开始执行时间： {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    start_time = time.time()
    output_file = "epg.xml"
    
    # 一周日期（若需抓取一周电视，取消注释下面一行，并切换电视抓取逻辑）
    # week_dates = get_week_dates()
    all_new_channels = []
    all_new_programs = []

    # 公共 Chrome 选项（电视和广播共用基础配置）
    def get_base_chrome_options():
        opts = Options()
        opts.add_argument('--headless=new')                                 # 新版无头模式，不显示浏览器窗口
        opts.add_argument('--no-sandbox')                                   # 禁用沙箱，容器环境必需
        opts.add_argument('--log-level=3')                                  # 日志级别，只显示致命错误
        opts.add_argument('--silent')                                       # 静默模式，减少输出
        opts.add_argument('--ignore-ssl-errors')                            # 忽略 SSL 错误
        opts.add_argument('--ignore-certificate-errors')                    # 忽略证书错误
        opts.add_argument('--allow-insecure-localhost')                     # 允许不安全的 localhost
        opts.add_argument('--disable-dev-shm-usage')                        # 禁用 /dev/shm，防内存不足
        
        opts.add_argument('--disable-background-networking')                # 禁用后台网络请求
        opts.add_argument('--disable-component-update')                     # 禁用组件更新
        opts.add_argument('--disable-domain-reliability')                   # 禁用域名可靠性上报
        opts.add_argument('--disable-gpu')                                  # 禁用 GPU 加速
        opts.add_argument('--disable-gpu-sandbox')                          # 禁用 GPU 沙箱
        opts.add_argument('--disable-gpu-compositing')                      # 禁用 GPU 合成
        opts.add_argument('--disable-sync')                                 # 禁用同步服务
        opts.add_argument('--disable-breakpad')                             # 禁用崩溃报告
        opts.add_argument('--disable-default-apps')                         # 禁用默认应用
        opts.add_argument('--disable-crash-reporter')                       # 禁用崩溃报告器
        opts.add_argument('--disable-blink-features=AutomationControlled')  # 隐藏自动化特征
        
        opts.add_experimental_option('excludeSwitches', ['enable-logging']) # 禁用 DevTools 日志
        opts.add_experimental_option('useAutomationExtension', False)       # 禁用自动化扩展
        
        prefs = {"profile.managed_default_content_settings.images": 2}      # 禁用图片加载
        opts.add_experimental_option("prefs", prefs)
        
        return opts
    
    tv_driver = None
    radio_driver = None

    try:
        # ---------- 电视 driver（无代理） ----------
        tv_options = get_base_chrome_options()
     
        tv_driver = webdriver.Chrome(options=tv_options)
        tv_driver.set_page_load_timeout(30)

        print()
        print("抓取镇江电视节目单...")
                
        for ch_name, cfg in TV_MAPPING.items():
            ch_id = cfg["id"]
            base_url = cfg["url"]
            print(f"  正在解析 {ch_name} ...")
            
            # ========== 当天版本（只抓今天，推荐） ==========
            day_programs = fetch_today_programs(ch_name, base_url, tv_driver, retries=2)
            if day_programs:
                day_programs.sort(key=lambda x: x[0])
                enriched = add_end_times(day_programs)
                all_new_channels.append((ch_id, cfg["display"]))
                for prog in enriched:
                    all_new_programs.append({
                        'start': prog['start_dt'].strftime("%Y%m%d%H%M%S +0800"),
                        'stop': prog['end_dt'].strftime("%Y%m%d%H%M%S +0800"),
                        'channel': ch_id,
                        'title': prog['title']
                    })
                print(f"    获取到 {len(enriched)} 个节目")
            else:
                print(f"    未抓取到任何数据")                
            
            # ========== 原一周版本（注释，需要时可恢复） ==========
            # weekly_programs = fetch_week_programs(ch_name, base_url, week_dates, tv_driver, retries=2)
            # if weekly_programs:
            #     weekly_programs.sort(key=lambda x: x[0])
            #     enriched = add_end_times(weekly_programs)
            #     all_new_channels.append((ch_name, ch_name))
            #     for prog in enriched:
            #         all_new_programs.append({
            #             'start': prog['start_dt'].strftime("%Y%m%d%H%M%S +0800"),
            #             'stop': prog['end_dt'].strftime("%Y%m%d%H%M%S +0800"),
            #             'channel': ch_name,
            #             'title': prog['title']
            #         })
            #     print(f"{ch_name} 共抓取 {len(enriched)} 个节目")
            # else:
            #     print(f"{ch_name} 未抓取到任何数据")

        # ---------- 广播 driver（带代理，仅 Actions 环境） ----------
        radio_options = get_base_chrome_options()
        
        print("\n抓取镇江广播节目单...")
    
        if os.environ.get('GITHUB_ACTIONS') == 'true':
            proxy_ip = os.environ.get('TINY_PROXY_IP')
            proxy_port = os.environ.get('TINY_PROXY_PORT')
            if proxy_ip and proxy_port:
                if test_tiny_proxy(proxy_ip, proxy_port):
                    radio_options.add_argument(f'--proxy-server=http://{proxy_ip}:{proxy_port}')
                    # print(f"已为广播 Chrome 设置代理")
                    radio_driver = webdriver.Chrome(options=radio_options)
                    radio_driver.set_page_load_timeout(120)
                    radio_channels, radio_programs = fetch_radio_programs(radio_driver, datetime.datetime.now().date(), retries=3)
                    all_new_channels.extend(radio_channels)
                    all_new_programs.extend(radio_programs)
                else:
                    print("代理测试失败，跳过广播抓取")
            else:
                print("代理环境变量缺失，跳过广播抓取")  # 理论上不会发生
        else:
            # 本地运行，不使用代理
            radio_driver = webdriver.Chrome(options=radio_options)
            radio_driver.set_page_load_timeout(90)
            radio_channels, radio_programs = fetch_radio_programs(radio_driver, datetime.datetime.now().date(), retries=2)
            all_new_channels.extend(radio_channels)
            all_new_programs.extend(radio_programs)

    finally:
        if tv_driver:
            tv_driver.quit()
        if radio_driver:
            radio_driver.quit()

    if all_new_programs:
        merge_and_write(output_file, all_new_channels, all_new_programs)
        elapsed = time.time() - start_time
        print(f"\n🎉 抓取完成！总耗时: {elapsed:.2f} 秒")
    else:
        print("❌ 未抓取到任何数据")

if __name__ == "__main__":
    main()