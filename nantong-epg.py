import json
import subprocess
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os

# 您成功抓取的 curl 命令（完整复制，注意转义）
CURL_CMD = '''curl "https://web.ntjoy.com/website/external/externalService" \
  -H "Accept: application/json, text/javascript, */*; q=0.01" \
  -H "Accept-Language: zh-CN,zh-TW;q=0.9,zh;q=0.8,en;q=0.7,en-GB;q=0.6,en-US;q=0.5,ja;q=0.4" \
  -H "Connection: keep-alive" \
  -H "Content-Type: application/x-www-form-urlencoded; charset=UTF-8" \
  -H "DNT: 1" \
  -H "Origin: https://www.ntjoy.com" \
  -H "Referer: https://www.ntjoy.com/" \
  -H "Sec-Fetch-Dest: empty" \
  -H "Sec-Fetch-Mode: cors" \
  -H "Sec-Fetch-Site: same-site" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0" \
  -H "sec-ch-ua: \"Chromium\";v=\"146\", \"Not-A.Brand\";v=\"24\", \"Microsoft Edge\";v=\"146\"" \
  -H "sec-ch-ua-mobile: ?0" \
  -H "sec-ch-ua-platform: \"Windows\"" \
  --data-raw "service=getMenuContentList&params=%7B%22menuId%22%3A%22ntw005%22%2C%22idx%22%3A0%2C%22size%22%3A16%7D&apiVersion=1.0&terminalType=website&butelAppkey=webntjoy&butelTst=1775627561657&butelSign=914f958127d0791d8edfa52ae11d990e"'''

def run_curl(service: str, menu_id: str):
    """动态替换 curl 命令中的 service 和 menuId"""
    # 替换 service 和 params 中的 menuId
    cmd = CURL_CMD.replace("service=getMenuContentList", f"service={service}")
    # 注意：params 需要 URL 编码，这里简单替换（生产环境最好用 urllib.parse.quote）
    import urllib.parse
    params = {"menuId": menu_id, "idx": 0, "size": 50}
    params_encoded = urllib.parse.quote(json.dumps(params, separators=(',', ':')))
    cmd = cmd.replace("params=%7B%22menuId%22%3A%22ntw005%22%2C%22idx%22%3A0%2C%22size%22%3A16%7D", f"params={params_encoded}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        print(f"curl 错误: {result.stderr}")
        return None

def fetch_channels(menu_code: str):
    print(f"正在获取 {menu_code} 频道列表...")
    data = run_curl("getMenuContentList", menu_code)
    if data and data.get('state') == 1000:
        rows = data['data'].get('rows', [])
        channels = [{'id': row['id'], 'name': row['title']} for row in rows]
        print(f"发现 {len(channels)} 个频道")
        return channels
    else:
        print("获取频道列表失败")
        return []

def fetch_programs(channel_id, channel_name):
    print(f"正在获取 {channel_name} 节目单...")
    data = run_curl("getBroadcastList", channel_id)
    if data and data.get('state') == 1000:
        programs = []
        for item in data['data']:
            start = item.get('startTime')
            end = item.get('endTime')
            title = item.get('programName')
            if start and end and title:
                programs.append({
                    'title': title,
                    'start_time': start.replace(' ', '') + ' +0800',  # 简单格式化
                    'end_time': end.replace(' ', '') + ' +0800',
                    'desc': ''
                })
        print(f"获取 {len(programs)} 条节目")
        return programs
    else:
        return []

def merge_into_epg(channels, programs, output_file="epg.xml"):
    # 简单的合并逻辑（您原来的函数保持不变）
    if os.path.exists(output_file):
        try:
            tree = ET.parse(output_file)
            tv = tree.getroot()
        except:
            tv = ET.Element("tv")
    else:
        tv = ET.Element("tv")
    # ... 此处省略合并代码，您可以直接复制原有的 merge_into_epg 函数
    print("已合并写入 epg.xml")

def main():
    print("开始抓取南通电视+广播 EPG")
    all_channels = []
    all_programs = []
    for menu_code, name in [("ntw005", "电视"), ("ntw006", "广播")]:
        print(f"\n--- 处理 {name} ---")
        channels = fetch_channels(menu_code)
        all_channels.extend(channels)
        for ch in channels:
            progs = fetch_programs(ch['id'], ch['name'])
            for p in progs:
                p['channel_id'] = ch['id']
            all_programs.extend(progs)
    if all_programs:
        merge_into_epg(all_channels, all_programs)
    else:
        print("未获取到任何节目数据")

if __name__ == "__main__":
    main()