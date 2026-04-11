import os
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def fetch_radio_programs():
    print("\n抓取镇江广播节目单...")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--silent')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    # ========== 代理配置（仅在 GitHub Actions 环境中） ==========
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        proxy_ip = os.environ.get('TINY_PROXY_IP')
        proxy_port = os.environ.get('TINY_PROXY_PORT')
        if proxy_ip and proxy_port:
            chrome_options.add_argument(f'--proxy-server=http://{proxy_ip}:{proxy_port}')
            print(f"已为 Chrome 设置代理: {proxy_ip}:{proxy_port}")
        else:
            print("警告: 运行在 GitHub Actions 环境，但未配置代理环境变量")
    else:
        print("本地运行，不设置代理")
    # =========================================================

    # 禁用图片加载
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option("prefs", prefs)
        
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(60)
    
    try:
        driver.get("https://www.zjmc.tv/broadcastTvs.html?menuCode=zhj004")
        # 等待页面加载完成
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        # 等待 Vue 数据加载
        WebDriverWait(driver, 60).until(
            lambda d: d.execute_script("return window.pageData && window.pageData.liveList && window.pageData.liveList.length > 0")
        )
        channels = driver.execute_script("return window.pageData.liveList")
        print(f"找到 {len(channels)} 个频道")
        
        for idx, ch in enumerate(channels, 1):
            ch_id = ch['id']
            ch_name = ch['title']
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
            programs = driver.execute_script("return window.pageData.programList")
            if programs:
                print(f"\n频道 {idx}: {ch_name}")
                for prog in programs:
                    start = prog.get('startTime', '')
                    title = prog.get('programName', '')
                    if start and title:
                        print(f"    {start[11:16]} - {title}")
            else:
                print(f"\n频道 {idx}: {ch_name} 无节目")
    finally:
        driver.quit()

if __name__ == "__main__":
    fetch_radio_programs()