import json
import datetime
import time
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def setup_driver():
    """配置无头 Chrome 浏览器"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    return webdriver.Chrome(options=chrome_options)

def fetch_channels_and_programs(menu_code: str, channel_type: str):
    """根据 menuId 获取频道列表及节目单"""
    url = f"https://www.ntjoy.com/ntw/broadcastTvs.html?menuId={menu_code}"
    driver = setup_driver()
    try:
        driver.get(url)
        # 等待频道列表加载（根据实际页面结构调整选择器）
        # 常见的频道列表容器：.channel-list ul li 或 .tv-channel-list .channel-item
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".channel-list li, .tv-channel-list .channel-item"))
        )
        # 获取所有频道元素
        channel_elements = driver.find_elements(By.CSS_SELECTOR, ".channel-list li, .tv-channel-list .channel-item")
        channels = []
        for elem in channel_elements:
            # 提取频道名称和ID（根据实际页面属性调整）
            name = elem.text.strip()
            if not name:
                name = elem.find_element(By.CSS_SELECTOR, ".channel-name").text.strip()
            channel_id = elem.get_attribute("data-id") or elem.get_attribute("id")
            if name and channel_id:
                channels.append({"id": channel_id, "name": name})
        print(f"  发现 {len(channels)} 个频道")
        if not channels:
            return [], []

        all_programs = []
        for idx, ch in enumerate(channels):
            print(f"  [{idx+1}/{len(channels)}] 正在获取 {ch['name']} 节目单...")
            # 点击频道以加载节目单
            try:
                # 重新定位元素（防止过期）
                current_channel = driver.find_element(By.XPATH, f"//*[@data-id='{ch['id']}']")
                current_channel.click()
                time.sleep(1.5)  # 等待节目单加载
                # 获取节目列表（根据实际页面结构调整）
                program_items = driver.find_elements(By.CSS_SELECTOR, ".program-list .program-item, .epg-list .epg-item")
                programs = []
                for prog in program_items:
                    # 提取节目名称和时间
                    title_elem = prog.find_element(By.CSS_SELECTOR, ".program-name, .title")
                    start_elem = prog.find_element(By.CSS_SELECTOR, ".start-time, .start")
                    end_elem = prog.find_element(By.CSS_SELECTOR, ".end-time, .end")
                    title = title_elem.text.strip()
                    start = start_elem.text.strip()
                    end = end_elem.text.strip()
                    if title and start and end:
                        # 格式化时间：将 "2026-04-08 13:00:00" -> "20260408130000 +0800"
                        start_fmt = start.replace("-", "").replace(":", "").replace(" ", "") + " +0800"
                        end_fmt = end.replace("-", "").replace(":", "").replace(" ", "") + " +0800"
                        programs.append({
                            "title": title,
                            "start_time": start_fmt,
                            "end_time": end_fmt,
                            "desc": ""
                        })
                print(f"    获取 {len(programs)} 条节目")
                all_programs.extend([{**p, "channel_id": ch["id"]} for p in programs])
            except Exception as e:
                print(f"    获取 {ch['name']} 节目失败: {e}")
                continue
        return channels, all_programs
    finally:
        driver.quit()

def merge_into_epg(all_channels, all_programs, output_file="epg.xml"):
    """合并数据到 epg.xml（保留原有频道和节目）"""
    if os.path.exists(output_file):
        try:
            tree = ET.parse(output_file)
            tv = tree.getroot()
        except:
            tv = ET.Element("tv")
    else:
        tv = ET.Element("tv")
    
    # 添加新频道（避免重复）
    existing_ids = {ch.get('id') for ch in tv.findall('channel')}
    for ch in all_channels:
        if ch['id'] not in existing_ids:
            ch_elem = ET.SubElement(tv, "channel", id=ch['id'])
            name_elem = ET.SubElement(ch_elem, "display-name", lang="zh")
            name_elem.text = ch['name']
            print(f"  添加频道: {ch['name']}")
    
    # 添加节目
    for prog in all_programs:
        prog_elem = ET.SubElement(tv, "programme",
                                  start=prog['start_time'],
                                  stop=prog['end_time'],
                                  channel=prog['channel_id'])
        title = ET.SubElement(prog_elem, "title", lang="zh")
        title.text = prog['title']
        if prog.get('desc'):
            desc = ET.SubElement(prog_elem, "desc", lang="zh")
            desc.text = prog['desc']
    
    xml_str = ET.tostring(tv, encoding='utf-8')
    dom = minidom.parseString(xml_str)
    pretty = dom.toprettyxml(indent="    ", encoding='utf-8').decode('utf-8')
    pretty = pretty.replace('<?xml version="1.0" ?>', '<?xml version="1.0" encoding="UTF-8"?>')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(pretty)
    
    total_channels = len(tv.findall('channel'))
    total_programs = len(tv.findall('programme'))
    print(f"\n✅ 已合并写入 {output_file}")
    print(f"   总频道数: {total_channels}")
    print(f"   总节目数: {total_programs}")

def main():
    print("开始抓取南通电视+广播 EPG")
    all_channels = []
    all_programs = []
    for menu_code, name in [("ntw005", "电视"), ("ntw006", "广播")]:
        print(f"\n--- 处理 {name} ---")
        channels, programs = fetch_channels_and_programs(menu_code, name)
        if not channels:
            print(f"  获取{name}频道列表失败")
            continue
        all_channels.extend(channels)
        all_programs.extend(programs)
        time.sleep(1)  # 避免请求过快
    
    if all_programs:
        merge_into_epg(all_channels, all_programs)
    else:
        print("未获取到任何节目数据")

if __name__ == "__main__":
    main()