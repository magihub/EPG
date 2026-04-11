#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立测试脚本：抓取镇江广播节目单（基于 DOM 解析）
"""

import datetime
import time
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==================== 配置 ====================
RADIO_URL = "https://www.zjmc.tv/broadcastTvs.html?menuCode=zhj004"
HEADLESS = True          # 无头模式
RETRIES = 2              # 重试次数
WAIT_TIME = 30           # 等待超时秒数

# ==================== 清理 Chrome 进程 ====================
def kill_chrome_processes():
    """清理残留的 Chrome 进程（Windows）"""
    try:
        os.system('taskkill /f /im chrome.exe 2>nul')
        os.system('taskkill /f /im chromedriver.exe 2>nul')
        print("已清理残留 Chrome 进程")
        time.sleep(1)
    except:
        pass

# ==================== 抓取广播节目 ====================
def fetch_radio_programs():
    print("\n抓取镇江广播节目单...")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--silent')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(30)
    
    try:
        driver.get("https://www.zjmc.tv/broadcastTvs.html?menuCode=zhj004")
        time.sleep(5)
        
        # 等待 Vue 数据加载
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return window.pageData && window.pageData.liveList && window.pageData.liveList.length > 0")
        )
        
        # 获取频道列表（只有3个）
        channels = driver.execute_script("return window.pageData.liveList")
        print(f"找到 {len(channels)} 个频道")
        
        for idx, ch in enumerate(channels, 1):
            ch_id = ch['id']
            ch_name = ch['title']
            
            # 显示名称
            display_name = ch_name
            print(f"\n频道 {idx}: {display_name}")
            
            # 点击频道
            driver.execute_script(f"""
                var divs = document.querySelectorAll('.swiper-slide');
                for(var i=0; i<divs.length; i++) {{
                    if(divs[i].getAttribute('data-id') == '{ch_id}') {{
                        divs[i].click();
                        break;
                    }}
                }}
            """)
            time.sleep(2)
            
            # 获取节目列表
            programs = driver.execute_script("return window.pageData.programList")
            if programs:
                print(f"  获取到 {len(programs)} 个节目:")
                for prog in programs:
                    start = prog.get('startTime', '')
                    title = prog.get('programName', '')
                    if start and title:
                        print(f"    {start[11:16]} - {title}")
            else:
                print("  无节目数据")
        
    finally:
        driver.quit()

if __name__ == "__main__":
    kill_chrome_processes()
    fetch_radio_programs()