from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
import datetime
import time
import os
import sys

# ==================== 配置区域 ====================
CHANNELS = [
    {
        "id": "如东新闻综合",
        "name": "如东新闻综合",
        "type": "tv",
        "url": "https://www.rdxmt.com/pc.html?topid=54172"
    },
    {
        "id": "如东综合广播",
        "name": "如东综合广播",
        "type": "radio",
        "url": "https://www.rdxmt.com/pc.html?topid=21400",
        "api_url": "https://live.cm.jstv.com/api/Channel/ChannelInfoAudio",
        "params": {
            "channelId": 85,
            "days": 7,
            "globalId": "1244448"
        }
    }
]

# ==================== 工具函数 ====================
def format_epg_time(time_string):
    if not time_string:
        return ""
    try:
        # 尝试解析 "2026-04-08 13:00:00" 格式
        dt = datetime.datetime.strptime(time_string.strip(), "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y%m%d%H%M%S +0800")
    except ValueError:
        return time_string

# -------------------- 电视抓取（无头 Chrome）--------------------
def fetch_tv_epg(channel_info):
    print(f"\n--- 开始抓取: {channel_info['name']} ---")
    print(f"访问地址: {channel_info['url']}")

    max_attempts = 2          # 最多尝试2次（第一次 + 1次重试）
    wait_seconds = 5          # 失败后等待5秒再重试

    for attempt in range(1, max_attempts + 1):
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        driver = webdriver.Chrome(options=chrome_options)

        try:
            driver.get(channel_info['url'])
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li[data-starttime]"))
            )
            li_elements = driver.find_elements(By.CSS_SELECTOR, "li[data-starttime]")
            programs = []
            for li in li_elements:
                start_time_raw = li.get_attribute('data-starttime')
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
                print("警告：未能抓取到节目单数据。")
                return None

            print(f"成功抓取到 {len(programs)} 条电视节目数据！")
            return {
                "channel_id": channel_info["id"],
                "channel_name": channel_info["name"],
                "programs": programs
            }

        except Exception as e:
            print(f"第 {attempt} 次抓取失败: {e}")
            if attempt < max_attempts:
                print(f"🔄 等待 {wait_seconds} 秒后重试...")
                time.sleep(wait_seconds)
            else:
                print("❌ 重试次数已用完，放弃抓取该频道")
                return None

        finally:
            driver.quit()

    return None   # 理论上不会走到这里，但保留

# -------------------- 广播抓取（自动获取 Token）--------------------
def extract_token_from_page(url):
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(30)  # 关键：避免无限等待
    try:
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
        print(f"获取到的 token 长度: {len(token) if token else 0}, 尾部: {token[-10:] if token else 'None'}")
        return token
    except Exception as e:
        print(f"获取 token 时失败: {e}")
        return None
    finally:
        driver.quit()

def fetch_radio_epg_with_token(channel_info):
    max_attempts = 2          # 最多尝试2次（第一次 + 1次重试）
    wait_seconds = 5          # 失败后等待5秒再重试    

    for attempt in range(1, max_attempts + 1):
        print(f"\n--- 开始抓取: {channel_info['name']} (第 {attempt} 次尝试) ---")
        print(f"访问地址: {channel_info['url']}")
        token = extract_token_from_page(channel_info['url'])   # 这个函数内部也可能失败
        if not token:
            print(f"第 {attempt} 次获取 token 失败")
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
        response = requests.get(channel_info['api_url'], params=channel_info['params'], headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"API 请求失败，状态码: {response.status_code}")
            return None

        data = response.json()

        programs = []
        # 节目列表在 data['data']['epg']['epg'] 中，每个元素有 'date' 和 'data'
        epg_days = data.get('data', {}).get('epg', {}).get('epg', [])
        if not epg_days:
            print("未找到广播节目列表")
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
            print("解析后无节目数据")
            return None

        print(f"成功抓取到 {len(programs)} 条广播节目数据！")
        return {
            "channel_id": channel_info["id"],
            "channel_name": channel_info["name"],
            "programs": programs
        }
        except Exception as e:
            print(f"第 {attempt} 次 API 请求失败: {e}")
            if attempt < max_attempts:
                time.sleep(wait_seconds)
                continue
            else:
                return None

    return None

# -------------------- 生成 XML --------------------
def generate_xmltv(epg_data_list, output_file="epg.xml"):
    if not epg_data_list:
        print("没有数据，无法生成 XML 文件")
        return False

    tv = ET.Element("tv")
    tv.set("generator-info-name", "如东EPG抓取工具")

    # 添加频道
    for epg in epg_data_list:
        channel = ET.SubElement(tv, "channel", id=epg["channel_id"])
        display_name = ET.SubElement(channel, "display-name", lang="zh")
        display_name.text = epg["channel_name"]

    # 添加节目
    for epg in epg_data_list:
        for prog in epg["programs"]:
            programme = ET.SubElement(tv, "programme",
                                      start=prog["start_time"],
                                      stop=prog["end_time"],
                                      channel=epg["channel_id"])
            title = ET.SubElement(programme, "title", lang="zh")
            title.text = prog["title"]
            if prog.get("desc"):
                desc = ET.SubElement(programme, "desc", lang="zh")
                desc.text = prog["desc"]

    xml_str = ET.tostring(tv, encoding='utf-8')
    parsed_xml = minidom.parseString(xml_str)
    pretty_xml = parsed_xml.toprettyxml(indent="  ")
    pretty_xml = pretty_xml.replace('<?xml version="1.0" ?>', '<?xml version="1.0" encoding="UTF-8"?>')
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(pretty_xml)

    print(f"\n✅ 节目单已成功保存至 {output_file}")
    return True

# ==================== 主程序 ====================
def main():
    print()
    print("=" * 50)
    # print("如东电视 & 如东广播 EPG 抓取工具")
    print(f"      程序执行时间（UTC）: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    all_epg_data = []

    # 抓取电视
    tv_epg = fetch_tv_epg(CHANNELS[0])
    if tv_epg:
        all_epg_data.append(tv_epg)

    time.sleep(2)

    # 抓取广播
    radio_epg = fetch_radio_epg_with_token(CHANNELS[1])
    if radio_epg:
        all_epg_data.append(radio_epg)

    if all_epg_data:
        generate_xmltv(all_epg_data)
        print("\n🎉 如东电视、广播均已抓取完成\n")
    else:
        print("\n⚠️ 未能抓取到任何有效数据！\n")

if __name__ == "__main__":
    main()