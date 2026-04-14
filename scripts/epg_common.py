#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EPG 通用函数：解析现有 XML、合并写入、节目结束时间计算
"""

import re
import os
import datetime
import xml.etree.ElementTree as ET
from datetime import timedelta

def parse_existing_xml(filepath):
    """解析现有的 epg.xml 文件，返回 (channels_dict, programs_list)"""
    if not os.path.exists(filepath):
        return {}, []
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        channels = {}
        for ch in root.findall('channel'):
            ch_id = ch.get('id')
            dn = ch.find('display-name')
            if ch_id:
                channels[ch_id] = dn.text if dn is not None else ch_id
        programs = []
        for prog in root.findall('programme'):
            start = prog.get('start')
            stop = prog.get('stop')
            channel = prog.get('channel')
            title_elem = prog.find('title')
            title = title_elem.text if title_elem is not None else ''
            if start and stop and channel:
                programs.append({
                    'start': start,
                    'stop': stop,
                    'channel': channel,
                    'title': title
                })
        return channels, programs
    except Exception as e:
        print(f"解析现有XML失败: {e}")
        return {}, []

def add_end_times(programs):
    """
    为节目列表补充结束时间（下一个节目的开始时间，最后一个节目到次日 00:00:00）
    programs: list of (start_dt, title)  按时间排序后的元组列表
    返回: list of dict with keys: title, start_dt, end_dt
    """
    result = []
    for i, (start, title) in enumerate(programs):
        if i + 1 < len(programs):
            end = programs[i+1][0]
        else:
            # 最后一个节目，结束时间设为次日 00:00:00
            end = start.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
        result.append({
            'title': title,
            'start_dt': start,
            'end_dt': end
        })
    return result

def merge_and_write(output_file, new_channels, new_programs, generator_name="广播电视 EPG 爬虫工具"):
    """
    合并现有 epg.xml 与新数据，写入文件（带缩进，无多余空行）
    new_channels: list of (channel_id, display_name)
    new_programs: list of dict with keys: start, stop, channel, title
    generator_name: 默认生成器名称（仅在文件不存在时使用）
    """
    # 读取现有数据
    exist_channels, exist_programs = parse_existing_xml(output_file)
    
    # 确定最终使用的 generator-info-name
    final_gen_name = generator_name
    if os.path.exists(output_file):
        try:
            tree = ET.parse(output_file)
            root = tree.getroot()
            gen = root.get('generator-info-name')
            if gen:
                final_gen_name = gen
        except:
            pass
    
    # 分离非新频道的旧数据（新频道完全替换）
    new_channel_ids = [ch_id for ch_id, _ in new_channels]
    other_channels = {ch_id: disp for ch_id, disp in exist_channels.items()
                      if ch_id not in new_channel_ids}
    other_programs = [p for p in exist_programs
                      if p['channel'] not in new_channel_ids]
    
    # 合并频道
    all_channels = dict(other_channels)
    for ch_id, disp in new_channels:
        all_channels[ch_id] = disp
    
    # 合并节目
    all_programs = other_programs + new_programs
    
    """     # 去除过滤
    
    # ========== 新增：过滤过期节目，只保留今天及未来 N 天 ==========
    from datetime import datetime, timedelta
    today = datetime.now().date()
    future_days = 1  # 保留未来 N 天
    future_limit = today + timedelta(days=future_days)
    
    filtered_programs = []
    for prog in all_programs:
        try:
            # 从 start 字段提取日期（格式 "20260412060000 +0800"）
            date_str = prog['start'][:8]
            prog_date = datetime.strptime(date_str, "%Y%m%d").date()
            if today <= prog_date <= future_limit:
                filtered_programs.append(prog)
            else:
                print(f"丢弃过期节目: {prog['channel']} {prog['start']}")
        except:
            # 如果解析失败，保留（容错）
            filtered_programs.append(prog)
    all_programs = filtered_programs  
    
    """    
    
    # ========== 新增：排序，确保输出顺序稳定 ==========
    # 对频道按 ID 排序
    # all_channels = dict(sorted(all_channels.items()))         # 此方法的排序规则是 FM106.1在FM91.8之前

    # all_channels = dict(sorted(all_channels.items(), key=lambda x: sort_channels(x[0])))         # 此方法的排序规则是 FM106.1在FM99.9之后


    # 先提取所有城市名（从广播频道）
    cities = set()
    for ch_id in all_channels.keys():
        if 'FM' in ch_id or 'AM' in ch_id:
            city = re.match(r'^([\u4e00-\u9fa5]+)', ch_id).group(1)
            cities.add(city)

    # 然后定义排序函数
    def sort_channels(channel_id):
        # 确定城市
        city = None
        for c in cities:
            if channel_id.startswith(c):
                city = c
                break
        if not city:
            city = ''  # fallback
        # 判断类型
        if 'FM' in channel_id or 'AM' in channel_id:
            freq = float(re.search(r'(\d+(?:\.\d+)?)', channel_id).group(1))
            return (city, 1, freq, channel_id)
        else:
            return (city, 0, 0, channel_id)
        
    sorted_channels = sorted(all_channels.items(), key=lambda x: sort_channels(x[0])) 
    
    # 排序测试打印
    # print("排序后的前20个频道:")
    # for ch_id, disp in sorted_channels[:20]:
    #     print(f"  {ch_id} -> {disp}")
    
    # 对频道按显示名称排序（而不是 ID）
    # all_channels = dict(sorted(all_channels.items(), key=lambda item: item[1]))
    
    # 对节目按 (频道, 开始时间) 排序
    # all_programs.sort(key=lambda x: (x['channel'], x['start']))
    # ==============================================

    
    # 生成 XML 树
    tv = ET.Element("tv")
    tv.set("generator-info-name", final_gen_name)
    
    # 排序频道
    for ch_id, disp in sorted_channels:                 # 生成 XML 时直接遍历排序后的列表，FM106.1在FM91.8之后
    # for ch_id, disp in all_channels.items():         # 此方法的排序规则是 FM106.1在FM91.8之前        
        channel = ET.SubElement(tv, "channel", id=ch_id)
        dn = ET.SubElement(channel, "display-name", lang="zh")
        dn.text = disp

    # 按照 sorted_channels 的顺序输出节目
    for ch_id, disp in sorted_channels:
        # 筛选出当前频道的所有节目
        channel_programs = [p for p in all_programs if p['channel'] == ch_id]
        # 按开始时间排序（已经排好，但为了安全）
        channel_programs.sort(key=lambda x: x['start'])
        for prog in channel_programs:
            programme = ET.SubElement(tv, "programme",
                                      start=prog['start'],
                                      stop=prog['stop'],
                                      channel=ch_id)
            title_elem = ET.SubElement(programme, "title", lang="zh")
            title_elem.text = prog['title']
        
    '''
    for prog in all_programs:
        programme = ET.SubElement(tv, "programme",
                                  start=prog['start'],
                                  stop=prog['stop'],
                                  channel=prog['channel'])
        title_elem = ET.SubElement(programme, "title", lang="zh")
        title_elem.text = prog['title']
     '''
     
    # 添加缩进（Python 3.9+）
    ET.indent(tv, space="  ", level=0)
    
    # 转换为字符串
    xml_str = ET.tostring(tv, encoding="utf-8").decode("utf-8")
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(xml_str)
    print(f"✅ 已合并保存至 {output_file} (总频道: {len(all_channels)}, 总节目: {len(all_programs)})")
    
def print_header():
    """打印统一的开始执行时间头"""
    print()
    print("=" * 32)
    print(f"开始执行时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 32)
