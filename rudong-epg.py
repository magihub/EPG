from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import xml.etree.ElementTree as ET
from xml.dom import minidom
import datetime
import time
import requests
import json
import os
import re

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
        dt = datetime.datetime.strptime(time_string.strip(), "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y%m%d%H%M%S +0800")
    except ValueError:
        return time_string

def extract_token_from_page(url):
    """从页面中提取Authorization Token（使用 Chrome）"""
    print("  正在从页面提取Token...")
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--log-level=3')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    try:
        driver.get(url)
        time.sleep(3)
        token = driver.execute_script("""
            let token = localStorage.getItem('token') || 
                       localStorage.getItem('access_token') ||
                       sessionStorage.getItem('token') ||
                       sessionStorage.getItem('access_token');
            if (!token && window.__INITIAL_STATE__ && window.__INITIAL_STATE__.token) {
                token = window.__INITIAL_STATE__.token;
            }
            return token;
        """)
        if token:
            print(f"  成功从页面提取Token: {token[:50]}...")
            return token
        print("  未能从页面提取Token")
        return None
    except Exception as e:
        print(f"  提取Token失败: {e}")
        return None
    finally:
        driver.quit()

def fetch_radio_epg(channel_info):
    """抓取广播 EPG（优先使用环境变量中的 Token，否则自动提取）"""
    print(f"\n--- 开始抓取: {channel_info['name']} ---")
    
    # 优先从环境变量获取 Token
    token = os.environ.get('RUDONG_RADIO_TOKEN')
    if token:
        print("  使用环境变量中的 Token")
    else:
        print("  环境变量未设置，尝试从页面自动提取 Token...")
        token = extract_token_from_page(channel_info['url'])
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.rdxmt.com/',
        'Origin': 'https://www.rdxmt.com',
        'Accept': '*/*'
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
    else:
        print("  ⚠️ 无法获取 Token，跳过广播抓取")
        return None
    
    try:
        print(f"  请求API: {channel_info['api_url']}")
        resp = requests.get(channel_info['api_url'], params=channel_info['params'], headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data and 'data' in data and 'epg' in data['data']:
                epg_data = data['data']['epg']['epg']
                programs = []
                for daily_epg in epg_data:
                    for item in daily_epg.get('data', []):
                        title = item.get('programName', '')
                        start = item.get('startTime')
                        end = item.get('endTime')
                        if title and start and end:
                            programs.append({
                                "title": title,
                                "start_time": format_epg_time(start),
                                "end_time": format_epg_time(end),
                                "desc": ""
                            })
                if not programs:
                    print("  警告：未能解析到节目数据。")
                    return None
                print(f"  成功抓取到 {len(programs)} 条节目数据！")
                return {
                    "channel_id": channel_info["id"],
                    "channel_name": channel_info["name"],
                    "programs": programs
                }
            else:
                print("  API返回数据格式异常")
                return None
        elif resp.status_code == 401:
            print("  ❌ Token 已过期！请更新 GitHub Secret RUDONG_RADIO_TOKEN。")
            return None
        else:
            print(f"  API请求失败，状态码: {resp.status_code}")
            return None
    except Exception as e:
        print(f"  抓取时出错: {e}")
        return None

# -------------------- 电视部分（使用 Chrome）--------------------
def fetch_tv_epg(channel_info):
    print(f"\n--- 开始抓取: {channel_info['name']} ---")
    print(f"  访问地址: {channel_info['url']}")
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--log-level=3')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
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
            print("  警告：未能抓取到节目单数据。")
            return None
        print(f"  成功抓取到 {len(programs)} 条节目数据！")
        return {
            "channel_id": channel_info["id"],
            "channel_name": channel_info["name"],
            "programs": programs
        }
    except Exception as e:
        print(f"  抓取时出错: {e}")
        return None
    finally:
        driver.quit()

# -------------------- 生成XML --------------------
def generate_xmltv(epg_data_list, output_file="epg.xml"):
    if not epg_data_list:
        print("没有数据，无法生成 XML 文件。")
        return False
    tv = ET.Element("tv")
    tv.set("generator-info-name", "如东EPG抓取工具")
    tv.set("date", datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
    for epg in epg_data_list:
        channel = ET.SubElement(tv, "channel", id=epg["channel_id"])
        display_name = ET.SubElement(channel, "display-name", lang="zh")
        display_name.text = epg["channel_name"]
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
    pretty_xml = parsed_xml.toprettyxml(indent="    ")
    pretty_xml = pretty_xml.replace('<?xml version="1.0" ?>', '<?xml version="1.0" encoding="UTF-8"?>')
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
    print(f"\n✅ 节目单已成功保存至 {output_file}")
    return True

# ==================== 主程序 ====================
def main():
    print("=" * 50)
    print("如东电视台 & 如东广播 EPG 抓取工具")
    print(f"执行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    all_epg_data = []
    tv_epg = fetch_tv_epg(CHANNELS[0])
    if tv_epg:
        all_epg_data.append(tv_epg)
    time.sleep(2)
    radio_epg = fetch_radio_epg(CHANNELS[1])
    if radio_epg:
        all_epg_data.append(radio_epg)
    if all_epg_data:
        generate_xmltv(all_epg_data)
        print("\n🎉 所有任务完成！")
    else:
        print("\n⚠️ 未能抓取到任何数据")

if __name__ == "__main__":
    main()