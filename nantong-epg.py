import json
import datetime
import time
import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List, Dict, Any
from curl_cffi import requests  # 替换原来的 requests

# ==================== 配置区域 ====================
API_URL = "https://web.ntjoy.com/website/external/externalService"

HEADERS = {
    'accept': 'application/json, text/javascript, */*; q=0.01',
    'accept-encoding': 'gzip, deflate, br, zstd',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'origin': 'https://www.ntjoy.com',
    'referer': 'https://www.ntjoy.com/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0',
}

MENU_CONFIGS = [
    {"menu_code": "ntw005", "name": "电视", "channel_type": "tv"},
    {"menu_code": "ntw006", "name": "广播", "channel_type": "radio"}
]

def fetch_api(service: str, params_dict: Dict) -> Any:
    payload = {
        'service': service,
        'params': json.dumps(params_dict)
    }
    try:
        # 使用 curl_cffi 模拟 Chrome 120 的指纹
        response = requests.post(API_URL, headers=HEADERS, data=payload, timeout=15, impersonate="chrome120")
        if response.status_code == 200:
            result = response.json()
            if result.get('state') == 1000:
                return result.get('data')
            else:
                print(f"  API返回错误 (state: {result.get('state')}): {result.get('message', '未知错误')}")
                return None
        else:
            print(f"  HTTP请求失败，状态码: {response.status_code}")
            print(f"  响应内容: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"  请求API时发生异常: {e}")
        return None

# ... 其余函数保持不变（fetch_channels, fetch_channel_programs, format_epg_time, merge_into_epg, main）

# ==================== 抓取频道和节目 ====================
def fetch_channels(menu_code: str) -> List[Dict]:
    print(f"\n正在获取{menu_code}的频道列表...")
    params = {'menuId': menu_code, 'idx': 0, 'size': 50}
    data = fetch_api("getMenuContentList", params)
    channels = []
    if data and isinstance(data, dict) and 'rows' in data:
        for item in data['rows']:
            channel = {
                'id': item.get('id'),
                'name': item.get('title', '未知频道'),
                'type': 'tv' if menu_code == 'ntw005' else 'radio',
                'cover': item.get('coverUrl', ''),
            }
            channels.append(channel)
            print(f"  发现频道: {channel['name']} (ID: {channel['id']})")
        print(f"成功获取 {len(channels)} 个频道。")
    else:
        print(f"获取频道列表失败，返回数据: {data}")
    return channels

def fetch_channel_programs(channel_id: str, channel_name: str) -> List[Dict]:
    print(f"  正在获取 {channel_name} 的节目单...")
    params = {'id': channel_id}
    data = fetch_api("getBroadcastList", params)
    programs = []
    if data and isinstance(data, list):
        for item in data:
            program = {
                'title': item.get('programName', '未知节目'),
                'start_time': format_epg_time(item.get('startTime')),
                'end_time': format_epg_time(item.get('endTime')),
                'desc': item.get('remark', ''),
                'status': item.get('status', 0),
            }
            if program['start_time'] and program['end_time'] and program['title'] != '未知节目':
                programs.append(program)
        print(f"    成功获取 {len(programs)} 条节目数据。")
    else:
        print(f"    未获取到节目数据或数据格式错误。")
    return programs

def format_epg_time(time_str: str) -> str:
    if not time_str:
        return ""
    try:
        dt = datetime.datetime.strptime(time_str.strip(), "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y%m%d%H%M%S +0800")
    except ValueError:
        return time_str

# ==================== 合并到现有 epg.xml（不覆盖） ====================
def merge_into_epg(all_channels: List[Dict], all_programs: List[Dict], output_file="epg.xml"):
    """将南通数据合并到现有的 epg.xml 中（保留原有频道和节目，避免重复）"""
    # 如果文件存在则解析，否则创建新根
    if os.path.exists(output_file):
        try:
            tree = ET.parse(output_file)
            tv = tree.getroot()
        except:
            tv = ET.Element("tv")
            tv.set("generator-info-name", "EPG合并工具")
            tv.set("date", datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
    else:
        tv = ET.Element("tv")
        tv.set("generator-info-name", "EPG合并工具")
        tv.set("date", datetime.datetime.now().strftime("%Y%m%d%H%M%S"))

    # 记录已有频道ID
    existing_channel_ids = {ch.get('id') for ch in tv.findall('channel') if ch.get('id')}

    # 添加新频道（南通）
    for ch in all_channels:
        if ch['id'] not in existing_channel_ids:
            ch_elem = ET.SubElement(tv, "channel", id=ch['id'])
            name_elem = ET.SubElement(ch_elem, "display-name", lang="zh")
            name_elem.text = ch['name']
            if ch.get('cover'):
                ET.SubElement(ch_elem, "icon", src=ch['cover'])
            existing_channel_ids.add(ch['id'])
            print(f"  添加频道: {ch['name']}")

    # 记录已有节目（使用 channel+start+stop 作为唯一键）
    existing_programs = set()
    for prog in tv.findall('programme'):
        key = (prog.get('channel'), prog.get('start'), prog.get('stop'))
        existing_programs.add(key)

    # 添加新节目（南通）
    added_count = 0
    for prog in all_programs:
        key = (prog['channel_id'], prog['start_time'], prog['end_time'])
        if key not in existing_programs:
            prog_elem = ET.SubElement(tv, "programme",
                                      start=prog['start_time'],
                                      stop=prog['end_time'],
                                      channel=prog['channel_id'])
            title = ET.SubElement(prog_elem, "title", lang="zh")
            title.text = prog['title']
            if prog.get('desc'):
                desc = ET.SubElement(prog_elem, "desc", lang="zh")
                desc.text = prog['desc']
            existing_programs.add(key)
            added_count += 1

    # 格式化输出
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
    print(f"   本次新增节目数: {added_count}")

# ==================== 主任务 ====================
def main():
    print(f"\n{'='*50}")
    print(f"开始抓取南通任务 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    
    start_time = time.time()
    all_channels = []
    all_programs = []
    
    for config in MENU_CONFIGS:
        print(f"\n--- 开始处理 {config['name']} 频道 ---")
        channels = fetch_channels(config['menu_code'])
        if not channels:
            print(f"⚠️ 未能获取 {config['name']} 频道列表，跳过。")
            continue
        
        all_channels.extend(channels)
        
        for idx, channel in enumerate(channels, 1):
            print(f"\n[{idx}/{len(channels)}] 处理{config['name']}频道: {channel['name']}")
            programs = fetch_channel_programs(channel['id'], channel['name'])
            for prog in programs:
                prog['channel_id'] = channel['id']
                all_programs.append(prog)
            if idx < len(channels):
                time.sleep(0.3)
    
    if all_programs:
        merge_into_epg(all_channels, all_programs)
        elapsed = time.time() - start_time
        print(f"\n🎉 抓取完成！总耗时: {elapsed:.2f} 秒")
        return 0
    else:
        print("\n⚠️ 未抓取到任何节目数据，请检查网络或接口。")
        return 1

if __name__ == "__main__":
    print("=" * 50)
    print("南通广播电视台 电视+广播 EPG 抓取工具（合并模式）")
    print("=" * 50)
    exit_code = main()
    exit(exit_code)