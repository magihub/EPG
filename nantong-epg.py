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

def fetch_channels_and_programs(menu_code, name, retries=3):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import time

    for attempt in range(retries):
        driver = None
        try:
            url = f"https://www.rdxmt.com/pc.html?topid={menu_code}"
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(30)
            driver.get(url)
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
            # 你的数据提取逻辑...
            # 如果成功，返回 channels, programs
            return channels, programs
        except Exception as e:
            print(f"抓取失败 ({name}): {e}")
            # 尝试保存当前页面状态（如果 driver 已创建）
            if driver:
                try:
                    with open("page_source.html", "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    driver.save_screenshot("debug.png")
                    print("已保存页面源码 page_source.html 和截图 debug.png")
                except Exception as save_err:
                    print(f"保存调试信息失败: {save_err}")
            return None, None
            time.sleep(10)
        finally:
            if driver:
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