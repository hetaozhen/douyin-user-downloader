import os
import re
import requests
from playwright.sync_api import sync_playwright
import time
import concurrent.futures

# 初始化全局线程池，最大并发下载数可根据需求调整
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

# 记录最近一次抓取到新数据的时间
last_data_time = time.time()

DOWNLOAD_DIR = "downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def sanitize_filename(name):
    # 移除 Windows 下不合法的文件名字符，包括换行符 \n \r
    return re.sub(r'[\\/*?:"<>|\n\r]', "", name).strip()

def log_failed_download(url, filepath, error_msg):
    # 将失败记录追加写入到同目录下的 failed_downloads.txt
    try:
        with open("failed_downloads.txt", "a", encoding="utf-8") as f:
            f.write(f"文件: {filepath}\n链接: {url}\n报错: {error_msg}\n{'-'*40}\n")
    except Exception:
        pass

def download_file(url, filepath):
    max_retries = 3
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/"
    }
    for attempt in range(max_retries):
        try:
            # 增加 headers，防止视频流 CDN 因为防盗链报错 403
            response = requests.get(url, stream=True, timeout=30, headers=headers)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                print(f"  [成功] 保存到: {filepath}")
                return  # 成功后直接跳出循环
            else:
                print(f"  [警告] HTTP状态码 {response.status_code}，正在尝试重试...")
                if attempt == max_retries - 1:
                    print(f"  [彻底失败] 最终HTTP状态码 {response.status_code}")
                    log_failed_download(url, filepath, f"HTTP状态码 {response.status_code}")
                # 等待一会儿后进入下一次循环重试
                time.sleep(2)
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  [警告] 请求出错，正在尝试第 {attempt + 2} 次重新下载...")
                time.sleep(2) # 延迟2秒后重试
            else:
                print(f"  [彻底失败] 达到最大重试次数，仍报错: {e}")
                log_failed_download(url, filepath, str(e))

def handle_response(response):
    global last_data_time
    # 过滤并且只处理包含作品列表的接口请求
    if "/aweme/v1/web/aweme/post/" in response.url and response.status == 200:
        try:
            data = response.json()
            if "aweme_list" in data and len(data["aweme_list"]) > 0:
                last_data_time = time.time()  # 只要还有新数据，就刷新时间
                for item in data["aweme_list"]:
                    # 动态获取作者名字用来创建文件夹
                    author_name = item.get("author", {}).get("nickname", "未知用户")
                    author_name = sanitize_filename(author_name)
                    user_dir = os.path.join(DOWNLOAD_DIR, author_name)
                    if not os.path.exists(user_dir):
                        os.makedirs(user_dir)

                    # 获取标题、唯一ID，并进行清洗截断
                    raw_desc = item.get("desc", "无标题")
                    aweme_id = str(item.get("aweme_id", "未知ID"))
                    
                    clean_desc = sanitize_filename(raw_desc)
                    if not clean_desc:
                        clean_desc = "无标题"
                    clean_desc = clean_desc[:40] 
                    
                    # 组合成带唯一标识的文件名：标题_ID（去除括号）
                    desc = f"{clean_desc}_{aweme_id}"

                    # 1. 如果是图文
                    if item.get("images"):
                        print(f"发现图文: {desc} (共 {len(item['images'])} 张)")
                        for idx, img in enumerate(item['images']):
                            url_list = img.get("url_list", [])
                            if url_list:
                                img_url = url_list[0]
                                filename = f"{desc}_{idx+1}.jpeg"
                                filepath = os.path.join(user_dir, filename)
                                if not os.path.exists(filepath):
                                    executor.submit(download_file, img_url, filepath)
                                else:
                                    pass # 已存在则跳过

                    # 2. 如果是视频
                    elif item.get("video"):
                        play_addr = item["video"].get("play_addr", {}).get("url_list", [])
                        if play_addr:
                            video_url = play_addr[0]
                            print(f"发现视频: {desc}")
                            filename = f"{desc}.mp4"
                            filepath = os.path.join(user_dir, filename)
                            if not os.path.exists(filepath):
                                executor.submit(download_file, video_url, filepath)
                            else:
                                pass # 已存在则跳过
        except Exception as e:
            # 抓取数据解析出错不影响主流程
            pass

import sys

def is_logged_in(user_data_dir):
    # 提前启动一次检查是否含有有效会话凭证
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(user_data_dir, headless=True)
            cookies = context.cookies()
            context.close()
            for cookie in cookies:
                if cookie['name'] in ['sessionid', 'sessionid_ss', 'passport_csrf_token']:
                    return True
    except Exception:
        pass
    return False

def main():
    if len(sys.argv) > 1:
        target_url = sys.argv[1]
    else:
        target_url = input("请输入你想爬取的抖音主页链接 (例如 https://www.douyin.com/user/...): ").strip()
        
    if not target_url:
        print("未输入有效链接，程序退出。")
        return
        
    print(f"准备爬取主页: {target_url}")
    print("--------------------------------------------------")
    print("提示：浏览器弹出后：\n1. 如果出现验证码，需手动通过。\n2. 下载的数据将保存在脚本所在目录下的 downloads 文件夹。")
    print("--------------------------------------------------")
    user_data_dir = os.path.join(os.getcwd(), 'browser_data')
    # 智能检查登录状态
    run_headless = is_logged_in(user_data_dir)
    
    if run_headless:
        print("✅ 已检测到有效的历史登录状态，程序将在后台静默工作 (无弹窗)。")
        print("💡 提示：如果以后发现明明有几百个数据，但在中途提早结束了，这通常是抖音在后台暗中拦截了滑块验证码。届时你可将代码里的 headless 改回 False 打开窗口手动解锁。")
    else:
        print("⚠️ 未检测到登录状态或已过期！即将弹出浏览器，请扫码登录抖音...")
        print("--------------------------------------------------")

    # 启动 playwright 并使用持久化上下文以保存 Cookie
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=run_headless,  # 恢复自动静默模式
            viewport={'width': 1280, 'height': 800}
        )
        page = context.pages[0] if context.pages else context.new_page()
        
        # 挂载网络响应拦截器
        page.on("response", handle_response)
        
        # 打开目标页面，延长至 60 秒且只要内容加载即可，不再盲目等待完全 networkidle
        try:
            page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"⚠️ 页面加载提示（不影响抓取）: {e}")
            
        print("\n等待 8 秒，请确保页面已加载完毕...")
        time.sleep(8)
        
        print("\n准备开始全自动向下滚动...")
        global last_data_time
        last_data_time = time.time()  # 开始滚动前重置一次时间
        scroll_count = 0
        
        try:
            # 循环滚到底部，触发懒加载分页
            while True:
                scroll_count += 1
                print(f"\n往下滚动加载中 (第 {scroll_count} 拨)... ⭐ 觉得够了随时可以按 Ctrl+C 提前停止！")
                
                # 舍弃可能因为焦点丢失而失效的键盘 PageDown，改用纯鼠标滚轮 + 容器定向滑动双保险！
                
                # 保险1：模拟真实的鼠标滚轮向下大幅度猛拨
                viewport = page.viewport_size
                if viewport:
                    page.mouse.move(viewport['width'] / 2, viewport['height'] / 2)
                for _ in range(3):
                    page.mouse.wheel(0, 3000)
                    time.sleep(0.5)

                # 保险2：强制获取抖音用来装载视频瀑布流的内部路由容器，直接给它灌输滑动位移
                page.evaluate("""() => {
                    const cont = document.querySelector('.route-scroll-container') || window;
                    if (cont && cont.scrollBy) {
                        cont.scrollBy(0, 5000);
                    }
                }""")
                time.sleep(2) # 等待列表新一批内容刷出
                
                # 彻底抛弃 DOM 高度判断！改用完美的网络数据包接收时间判断。
                # 如果超过 15 秒都没监听到任何新的带有 aweme_list 的有效数据流，说明真到底了。
                idle_time = time.time() - last_data_time
                if idle_time > 15:
                    print("🎉 检测到连续 15 秒没有任何新作品数据入账。数据已经到底啦！")
                    break
                else:
                    print(f"数据持续流入中 (最后一次收到数据是在 {int(idle_time)} 秒前)...")
        except KeyboardInterrupt:
            print("\n⚠️ 收到中止指令！正在安全退出，您已抓取的数据均已自动保存... ⚠️")
        
        print("网页浏览完毕，等候所有后台下载任务完成...")
        context.close()
        
        # 等待线程池中的下载任务全部完成
        executor.shutdown(wait=True)
        print("全部抓取任务结束！")

if __name__ == "__main__":
    main()
