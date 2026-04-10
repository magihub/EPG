from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import xml.etree.ElementTree as ET
from xml.dom import minidom
from curl_cffi import requests
import datetime
import time
import sys
import os
from epg_common import merge_and_write   # 导入公共合并函数

# ==================== 配置区域 ====================
CHANNELS = [
    {
        "id": "如东新闻综合",
        "name": "如东新闻综合",
        "type": "tv",
        "url": "https://www.rdxmt.com/pc.html?topid=54172"
    },
    {
        "id": "如东FM89.6",
        "name": "如东综合广播",
        "type": "radio",
        "url": "https://www.rdxmt.com/pc.html?topid=21400",
        "api_url": "https://live.cm.jstv.com/api/Channel/ChannelInfoAudio",
        "params": {
            "channelId": 85,
            "days": 1,          # 7为一周，1为当天
            "globalId": "1244448"
        }
    }
]

# ==================== 工具函数 ====================
def format_epg_time(time_string):
    if not time_string:
        return ""
    try:
        dt = datetime.datetime.strptime(time_string.strip(), "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y%m%d%H%M%S +0800")
    except ValueError:
        return time_string

# -------------------- 电视抓取（复用 driver）--------------------
def fetch_tv_epg(channel_info, driver):
    max_attempts = 2
    wait_seconds = 5
    
    for attempt in range(1, max_attempts + 1):
        print(f"\n开始解析 {channel_info['name']} ...")
        try:
            driver.get(channel_info['url'])
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li[data-starttime]"))
            )
            li_elements = driver.find_elements(By.CSS_SELECTOR, "li[data-starttime]")
            
            # 当天版本（只抓取今天）
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            programs = []
            for li in li_elements:
                start_time_raw = li.get_attribute('data-starttime')
                if not start_time_raw:
                    continue
                if not start_time_raw.startswith(today_str):
                    continue
                end_time_raw = li.get_attribute('data-endtime')
                spans = li.find_elements(By.TAG_NAME, 'span')
                title = spans[1].get_attribute('textContent').strip() if len(spans) >= 2 else "未知节目"
                if title and start_time_raw and end_time_raw:
                    programs.append({
                        "title": title,
                        "start_time": format_epg_time(start_time_raw),
                        "end_time": format_epg_time(end_time_raw),
                        "desc": ""
                    })

            if not programs:
                print("  未能获取到节目单")
                return None

            print(f"  获取到 {len(programs)} 个节目")
            return {
                "channel_id": channel_info["id"],
                "channel_name": channel_info["name"],
                "programs": programs
            }

        except Exception as e:
            print(f"⚠️ 第 {attempt} 次抓取失败: {e}")
            if attempt < max_attempts:
                print(f"🔄 等待 {wait_seconds} 秒后重试...")
                time.sleep(wait_seconds)
            else:
                print("❌ 重试次数已用完，放弃抓取该频道")
                return None

    return None

# -------------------- 广播抓取（复用 driver 获取 token）--------------------
def extract_token_from_page(driver, url):
    driver.get(url)
    time.sleep(3)
    token = driver.execute_script("""
        let keys = ['token', 'access_token', 'jwt', 'authorization'];
        for (let key of keys) {
            let val = localStorage.getItem(key) || sessionStorage.getItem(key);
            if (val) return val;
        }
        if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.token) {
            return window.__INITIAL_STATE__.token;
        }
        return null;
    """)
    # print(f"获取到的 token 类型： {type(token).__name__ if token else 'None'}, 长度: {len(token) if token else 0}, 尾部: {token[-10:] if token else 'None'}") 
    print(f"获取到的 token 尾部: {token[-10:] if token else 'None'}")
    return token

def fetch_radio_epg_with_token(channel_info, driver):
    max_attempts = 2
    wait_seconds = 5

    for attempt in range(1, max_attempts + 1):
        print(f"\n开始解析 {channel_info['name']} ...")
        token = extract_token_from_page(driver, channel_info['url'])
        if not token:
            print(f"⚠️ 第 {attempt} 次获取 token 失败")
            if attempt < max_attempts:
                print(f"🔄 等待 {wait_seconds} 秒后重试...")
                time.sleep(wait_seconds)
                continue
            else:
                print("❌ 重试次数已用完，跳过广播抓取")
                return None

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Authorization': f'Bearer {token}',
            'Referer': channel_info['url'],
            'Accept': 'application/json, text/plain, */*'
        }
        try:
            # 直接使用 curl_cffi 的 requests.get，添加指纹伪装和忽略证书
            response = requests.get(
                channel_info['api_url'],
                params=channel_info['params'],
                headers=headers,
                timeout=15,
                impersonate="chrome120",   # 关键：模拟 Chrome 指纹
                verify=False               # 忽略 SSL 证书验证
            )
            if response.status_code != 200:
                print(f"⚠️ 第 {attempt} 次 API 请求失败，状态码: {response.status_code}")
                if attempt < max_attempts:
                    print(f"🔄 等待 {wait_seconds} 秒后重试...")
                    time.sleep(wait_seconds)
                    continue
                else:
                    return None

            data = response.json()
            programs = []
            epg_days = data.get('data', {}).get('epg', {}).get('epg', [])
            if not epg_days:
                print(f"⚠️ 第 {attempt} 次未找到广播节目列表")
                if attempt < max_attempts:
                    print(f"🔄 等待 {wait_seconds} 秒后重试...")
                    time.sleep(wait_seconds)
                    continue
                else:
                    return None

            for day in epg_days:
                for item in day.get('data', []):
                    title = item.get('programName')
                    start = item.get('startTime')
                    end = item.get('endTime')
                    if title and start and end:
                        programs.append({
                            "title": title,
                            "start_time": format_epg_time(start),
                            "end_time": format_epg_time(end),
                            "desc": item.get('remark', '')
                        })

            if not programs:
                print(f"⚠️ 第 {attempt} 次解析后无广播节目数据")
                if attempt < max_attempts:
                    print(f"🔄 等待 {wait_seconds} 秒后重试...")
                    time.sleep(wait_seconds)
                    continue
                else:
                    return None

            print(f"  获取到 {len(programs)} 个节目")
            return {
                "channel_id": channel_info["id"],
                "channel_name": channel_info["name"],
                "programs": programs
            }
        except Exception as e:
            print(f"⚠️ 第 {attempt} 次 API 请求或解析异常: {e}")
            if attempt < max_attempts:
                print(f"🔄 等待 {wait_seconds} 秒后重试...")
                time.sleep(wait_seconds)
                continue
            else:
                print("❌ 重试次数已用完，放弃广播抓取")
                return None
    return None

# ==================== 主程序 ====================
def main():
    print()
    print("=" * 50)
    print(f"      开始执行时间（UTC）: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    start_time = time.time()
    output_file = "epg.xml"
    # 新增：用于收集频道和节目数据
    all_new_channels = []
    all_new_programs = []
    # 创建 Chrome driver（只创建一次）
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--silent')
    chrome_options.add_argument('--disable-background-networking')  # 新增
    chrome_options.add_argument('--disable-component-update')      # 新增
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')    
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    driver = webdriver.Chrome(options=chrome_options)

    try:
        # 抓取电视
        tv_epg = fetch_tv_epg(CHANNELS[0], driver)
        if tv_epg:
            # 新增：收集电视频道和节目
            ch_id = tv_epg["channel_id"]
            ch_display = tv_epg["channel_name"]
            all_new_channels.append((ch_id, ch_display))
            for prog in tv_epg["programs"]:
                all_new_programs.append({
                    'start': prog['start_time'],
                    'stop': prog['end_time'],
                    'channel': ch_id,
                    'title': prog['title']
                })
        time.sleep(2)

        # 抓取广播
        radio_epg = fetch_radio_epg_with_token(CHANNELS[1], driver)
        if radio_epg:
            # 新增：收集广播频道和节目
            ch_id = radio_epg["channel_id"]
            ch_display = radio_epg["channel_name"]
            all_new_channels.append((ch_id, ch_display))
            for prog in radio_epg["programs"]:
                all_new_programs.append({
                    'start': prog['start_time'],
                    'stop': prog['end_time'],
                    'channel': ch_id,
                    'title': prog['title']
                })

    finally:
        driver.quit()

    # 使用公共合并函数写入（替换如东数据）
    if all_new_programs:
        merge_and_write(output_file, all_new_channels, all_new_programs)
        elapsed = time.time() - start_time
        print(f"\n🎉 抓取完成！总耗时: {elapsed:.2f} 秒")
    else:
        print("\n⚠️ 未能抓取到任何有效数据！")

if __name__ == "__main__":
    main()