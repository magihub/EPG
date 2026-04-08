import json
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import os
from typing import List, Dict, Any

# 使用 curl_cffi 代替标准 requests（模拟浏览器指纹）
try:
    from curl_cffi import requests
    print("使用 curl_cffi 库（模拟浏览器 TLS 指纹）")
except ImportError:
    import requests
    print("使用标准 requests 库")

API_URL = "https://web.ntjoy.com/website/external/externalService"

HEADERS = {
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'Connection': 'keep-alive',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Host': 'web.ntjoy.com',
    'Origin': 'https://www.ntjoy.com',
    'Referer': 'https://www.ntjoy.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0',
    'X-Requested-With': 'XMLHttpRequest',
}

MENU_CONFIGS = [
    {"menu_code": "ntw005", "name": "电视", "channel_type": "tv"},
    {"menu_code": "ntw006", "name": "广播", "channel_type": "radio"}
]

# 全局 Session，复用连接
_session = requests.Session()
_session.headers.update(HEADERS)

def fetch_api(service: str, params_dict: Dict) -> Any:
    """使用 POST 表单方式请求"""
    payload = {'service': service, 'params': json.dumps(params_dict)}
    try:
        resp = _session.post(API_URL, data=payload, timeout=15)
        resp.encoding = 'utf-8'
        if resp.status_code == 200:
            result = resp.json()
            if result.get('state') == 1000:
                return result.get('data')
            else:
                print(f"  API错误: {result.get('message')}")
                return None
        else:
            print(f"  HTTP {resp.status_code}, 响应内容: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  请求异常: {e}")
        return None

def fetch_channels(menu_code: str) -> List[Dict]:
    print(f"\n正在获取{menu_code}频道列表...")
    params = {'menuId': menu_code, 'idx': 0, 'size': 50}
    data = fetch_api("getMenuContentList", params)
    channels = []
    if data and isinstance(data, dict) and 'rows' in data:
        for item in data['rows']:
            channels.append({
                'id': item.get('id'),
                'name': item.get('title', '未知频道'),
                'type': 'tv' if menu_code == 'ntw005' else 'radio',
                'cover': item.get('coverUrl', '')
            })
        print(f"  发现 {len(channels)} 个频道")
    else:
        print("  获取频道列表失败")
    return channels

def fetch_channel_programs(channel_id: str, channel_name: str) -> List[Dict]:
    print(f"  正在获取 {channel_name} 节目单...")
    params = {'id': channel_id}
    data = fetch_api("getBroadcastList", params)
    programs = []
    if data and isinstance(data, list):
        for item in data:
            start = item.get('startTime')
            end = item.get('endTime')
            title = item.get('programName', '')
            if start and end and title and title != '未知节目':
                programs.append({
                    'title': title,
                    'start_time': format_epg_time(start),
                    'end_time': format_epg_time(end),
                    'desc': item.get('remark', '')
                })
        print(f"    获取 {len(programs)} 条节目")
    else:
        print("    无节目数据")
    return programs

def format_epg_time(time_str: str) -> str:
    if not time_str:
        return ""
    try:
        dt = datetime.datetime.strptime(time_str.strip(), "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y%m%d%H%M%S +0800")
    except:
        return time_str

def merge_into_epg(channels: List[Dict], programs: List[Dict], output_file="epg.xml"):
    # 保持不变（你原有的合并函数）
    if os.path.exists(output_file):
        try:
            tree = ET.parse(output_file)
            tv = tree.getroot()
            print(f"已读取现有 {output_file}")
        except Exception as e:
            print(f"读取失败，创建新文件: {e}")
            tv = ET.Element("tv")
    else:
        tv = ET.Element("tv")
        print(f"创建新的 {output_file}")

    existing_ids = {ch.get('id') for ch in tv.findall('channel')}
    for ch in channels:
        if ch['id'] not in existing_ids:
            ch_elem = ET.SubElement(tv, "channel", id=ch['id'])
            name_elem = ET.SubElement(ch_elem, "display-name", lang="zh")
            name_elem.text = ch['name']
            if ch.get('cover'):
                ET.SubElement(ch_elem, "icon", src=ch['cover'])
            print(f"  添加频道: {ch['name']} ({ch['type']})")

    for prog in programs:
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
    print(f"\n开始抓取南通电视+广播 EPG - {datetime.datetime.now()}")
    all_channels = []
    all_programs = []

    for config in MENU_CONFIGS:
        print(f"\n--- 处理 {config['name']} ---")
        channels = fetch_channels(config['menu_code'])
        if not channels:
            continue
        all_channels.extend(channels)

        for idx, ch in enumerate(channels, 1):
            print(f"[{idx}/{len(channels)}] {ch['name']}")
            progs = fetch_channel_programs(ch['id'], ch['name'])
            for p in progs:
                p['channel_id'] = ch['id']
                all_programs.append(p)
            time.sleep(0.3)

    if all_programs:
        merge_into_epg(all_channels, all_programs, "epg.xml")
    else:
        print("未获取到任何节目数据")

if __name__ == "__main__":
    main()