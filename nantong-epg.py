import json
import datetime
import time
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os
import requests

API_URL = "https://web.ntjoy.com/website/external/externalService"

# 固定签名参数（从成功的 curl 命令中提取）
FIXED_SIGN = "914f958127d0791d8edfa52ae11d990e"
FIXED_TST = 1775627561657

def fetch_api(service: str, params_dict: dict):
    """使用固定签名发送 POST 请求"""
    payload = {
        'service': service,
        'params': json.dumps(params_dict, separators=(',', ':')),  # 紧凑格式
        'apiVersion': '1.0',
        'terminalType': 'website',
        'butelAppkey': 'webntjoy',
        'butelTst': FIXED_TST,
        'butelSign': FIXED_SIGN
    }
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': 'https://www.ntjoy.com',
        'Referer': 'https://www.ntjoy.com/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0'
    }
    try:
        resp = requests.post(API_URL, data=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            result = resp.json()
            if result.get('state') == 1000:
                return result.get('data')
            else:
                print(f"  API错误: {result.get('message')}")
                return None
        else:
            print(f"  HTTP {resp.status_code}")
            return None
    except Exception as e:
        print(f"  请求异常: {e}")
        return None

def fetch_channels(menu_code: str):
    print(f"正在获取 {menu_code} 频道列表...")
    data = fetch_api("getMenuContentList", {"menuId": menu_code, "idx": 0, "size": 50})
    if data and 'rows' in data:
        channels = [{'id': row['id'], 'name': row['title']} for row in data['rows']]
        print(f"  发现 {len(channels)} 个频道")
        return channels
    else:
        print("  获取频道列表失败")
        return []

def fetch_programs(channel_id: str, channel_name: str):
    print(f"  正在获取 {channel_name} 节目单...")
    data = fetch_api("getBroadcastList", {"id": channel_id})
    programs = []
    if data and isinstance(data, list):
        for item in data:
            start = item.get('startTime')
            end = item.get('endTime')
            title = item.get('programName')
            if start and end and title:
                programs.append({
                    'title': title,
                    'start_time': start.replace(' ', '') + ' +0800',
                    'end_time': end.replace(' ', '') + ' +0800',
                    'desc': item.get('remark', '')
                })
        print(f"    获取 {len(programs)} 条节目")
    else:
        print("    无节目数据")
    return programs

def merge_into_epg(all_channels, all_programs, output_file="epg.xml"):
    # 请复制您原有的 merge_into_epg 函数（这里简单实现一个）
    if os.path.exists(output_file):
        try:
            tree = ET.parse(output_file)
            tv = tree.getroot()
        except:
            tv = ET.Element("tv")
    else:
        tv = ET.Element("tv")
    
    # 添加频道
    existing_ids = {ch.get('id') for ch in tv.findall('channel')}
    for ch in all_channels:
        if ch['id'] not in existing_ids:
            ch_elem = ET.SubElement(tv, "channel", id=ch['id'])
            name_elem = ET.SubElement(ch_elem, "display-name", lang="zh")
            name_elem.text = ch['name']
    
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
    print(f"✅ 已合并写入 {output_file}")

def main():
    print("开始抓取南通电视+广播 EPG")
    all_channels = []
    all_programs = []
    for menu_code, name in [("ntw005", "电视"), ("ntw006", "广播")]:
        print(f"\n--- 处理 {name} ---")
        channels = fetch_channels(menu_code)
        if not channels:
            continue
        all_channels.extend(channels)
        for ch in channels:
            progs = fetch_programs(ch['id'], ch['name'])
            for p in progs:
                p['channel_id'] = ch['id']
            all_programs.extend(progs)
        time.sleep(0.5)
    
    if all_programs:
        merge_into_epg(all_channels, all_programs)
    else:
        print("未获取到任何节目数据")

if __name__ == "__main__":
    main()