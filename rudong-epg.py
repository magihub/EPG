from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import xml.etree.ElementTree as ET
from xml.dom import minidom
import datetime

def format_epg_time(time_string):
    if not time_string:
        return ""
    try:
        dt = datetime.datetime.strptime(time_string.strip(), "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y%m%d%H%M%S +0800")
    except ValueError:
        return time_string

def fetch_epg_data():
    print("正在启动无头 Chrome 浏览器...")
    chrome_options = Options()
    chrome_options.add_argument('--headless')               # 无头模式
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--log-level=3')

    driver = webdriver.Chrome(options=chrome_options)

    try:
        url = "https://www.rdxmt.com/pc.html?topid=54172"
        print("正在请求网页并等待 JS 渲染数据...")
        driver.get(url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li[data-starttime]"))
        )

        li_elements = driver.find_elements(By.CSS_SELECTOR, "li[data-starttime]")

        programs = []
        for li in li_elements:
            start_time_raw = li.get_attribute('data-starttime')
            end_time_raw = li.get_attribute('data-endtime')

            spans = li.find_elements(By.TAG_NAME, 'span')
            if len(spans) >= 2:
                title = spans[1].get_attribute('textContent').strip()
            else:
                title = "未知节目"

            programs.append({
                "title": title,
                "start_time": format_epg_time(start_time_raw),
                "end_time": format_epg_time(end_time_raw),
                "desc": ""
            })

        if not programs:
            print("警告：未能匹配到节目单结构。")
            return []

        print(f"成功抓取到 {len(programs)} 条节目数据！")

        epg_list = [
            {
                "channel_id": "rudong1",
                "channel_name": "如东新闻综合",
                "programs": programs
            }
        ]
        return epg_list

    except Exception as e:
        print(f"网页抓取超时或解析失败: {e}")
        return []
    finally:
        driver.quit()

def generate_xmltv(epg_list, output_file="epg.xml"):
    if not epg_list:
        return

    tv = ET.Element("tv")

    for epg in epg_list:
        channel = ET.SubElement(tv, "channel", id=epg["channel_id"])
        display_name = ET.SubElement(channel, "display-name", lang="zh")
        display_name.text = epg["channel_name"]

    for epg in epg_list:
        for prog in epg["programs"]:
            programme = ET.SubElement(tv, "programme",
                                      start=prog["start_time"],
                                      stop=prog["end_time"],
                                      channel=epg["channel_id"])
            title = ET.SubElement(programme, "title", lang="zh")
            title.text = prog["title"]

            desc = ET.SubElement(programme, "desc", lang="zh")
            desc.text = prog.get("desc", "")

    xml_str = ET.tostring(tv, encoding='utf-8')
    parsed_xml = minidom.parseString(xml_str)
    pretty_xml = parsed_xml.toprettyxml(indent="    ")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(pretty_xml)

    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 节目单已成功提取并保存至 {output_file}")

if __name__ == "__main__":
    data = fetch_epg_data()
    if data:
        generate_xmltv(data, "epg.xml")
    else:
        print("未获取到数据，退出。")