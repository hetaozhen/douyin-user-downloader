import os
import re
import requests
from playwright.sync_api import sync_playwright
import time
import datetime
import concurrent.futures

# 初始化全局线程池，最大并发下载数可根据需求调整
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

# 记录最近一次抓取到新数据的时间
last_data_time = time.time()

# 全局筛选配置变量
FILTER_KEYWORD = ""
START_DATETIME = None
END_DATETIME = None

# 全局下载任务跟踪器列表
active_futures = []

def parse_datetime_input(input_str, is_end=False):
    input_str = input_str.strip()
    if not input_str:
        return None
    
    # 尝试解析多种常见格式
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
        "%Y%m%d"
    ]
    
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(input_str, fmt)
            # 如果只输入了日期，且是结束时间，将其设置为当天的 23:59:59
            if fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"] and is_end:
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue
            
    print(f"⚠️ 无法解析时间格式 '{input_str}'，该过滤条件将不生效。建议使用 YYYY-MM-DD 格式。")
    return None

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

def process_aweme_item(item, is_single=False):
    # 动态获取作者名字用来创建文件夹
    author_name = item.get("author", {}).get("nickname", "未知用户")
    author_name = sanitize_filename(author_name)
    user_dir = os.path.join(DOWNLOAD_DIR, author_name)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    # 获取标题与发布时间
    raw_desc = item.get("desc", "无标题")
    create_time_raw = item.get("create_time")
    
    # 1. 关键字过滤 (模糊匹配，不区分大小写)
    if not is_single and FILTER_KEYWORD and FILTER_KEYWORD.lower() not in raw_desc.lower():
        return
        
    # 2. 时间过滤
    pub_time = None
    if create_time_raw:
        try:
            pub_time = datetime.datetime.fromtimestamp(create_time_raw)
        except Exception:
            pass
            
    if not is_single and (START_DATETIME or END_DATETIME):
        if not pub_time:
            return  # 如果无法获取发布时间，则过滤掉该作品
        if START_DATETIME and pub_time < START_DATETIME:
            return
        if END_DATETIME and pub_time > END_DATETIME:
            return
            
    # 获取清洗后的标题
    clean_desc = sanitize_filename(raw_desc)
    if not clean_desc:
        clean_desc = "无标题"
    clean_desc = clean_desc[:40] 
    
    # 转换发布时间字符串用于文件名 (例如 YYYYMMDD_HHMMSS)
    if pub_time:
        time_str = pub_time.strftime("%Y%m%d_%H%M%S")
    else:
        time_str = "未知时间"
        
    # 新的文件名格式：[发布时间]_[标题]
    desc = f"{time_str}_{clean_desc}"

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
                    future = executor.submit(download_file, img_url, filepath)
                    active_futures.append(future)
                else:
                    pass # 已存在则跳过

    # 2. 如果是视频
    elif item.get("video"):
        video_url = None
        bit_rate_list = item["video"].get("bit_rate")
        if bit_rate_list and isinstance(bit_rate_list, list):
            # 过滤出含有有效播放地址的项，并按 bit_rate 降序排列
            valid_rates = []
            for r in bit_rate_list:
                if isinstance(r, dict) and r.get("play_addr", {}).get("url_list"):
                    valid_rates.append(r)
            if valid_rates:
                valid_rates.sort(key=lambda x: x.get("bit_rate", 0), reverse=True)
                highest_rate_item = valid_rates[0]
                video_url = highest_rate_item["play_addr"]["url_list"][0]
                gear = highest_rate_item.get("gear_name", "unknown")
                rate_val = highest_rate_item.get("bit_rate", 0)
                print(f"发现视频: {desc} | [最高画质] 档位: {gear} (码率: {rate_val})")
        
        # 回退至默认播放地址
        if not video_url:
            play_addr = item["video"].get("play_addr", {}).get("url_list", [])
            if play_addr:
                video_url = play_addr[0]
                print(f"发现视频 (默认画质): {desc}")

        if video_url:
            filename = f"{desc}.mp4"
            filepath = os.path.join(user_dir, filename)
            if not os.path.exists(filepath):
                future = executor.submit(download_file, video_url, filepath)
                active_futures.append(future)
            else:
                pass # 已存在则跳过

def handle_response(response):
    global last_data_time
    # 过滤并且只处理包含作品列表的接口请求
    if "/aweme/v1/web/aweme/post/" in response.url and response.status == 200:
        try:
            data = response.json()
            if "aweme_list" in data and len(data["aweme_list"]) > 0:
                last_data_time = time.time()  # 只要还有新数据，就刷新时间
                for item in data["aweme_list"]:
                    process_aweme_item(item)
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
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
        
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
        
        is_first_run = True
        
        while True:
            if len(sys.argv) > 1 and is_first_run:
                raw_input_text = sys.argv[1]
                is_first_run = False
                single_run = True
            else:
                raw_input_text = input("\n请输入你想爬取的抖音主页链接或包含单视频链接的文本 (输入 exit 或 q 退出): ").strip()
                if raw_input_text.lower() in ['exit', 'quit', 'q']:
                    print("程序已退出。")
                    break
                single_run = False
                
            # 从文本中提取 URL
            match = re.search(r'https?://[^\s]+', raw_input_text)
            if match:
                target_url = match.group(0)
            else:
                target_url = ""
                
            if not target_url:
                print("⚠️ 未从输入中提取到有效链接，请重新输入。")
                if single_run:
                    break
                continue
                
            print(f"\n正在打开链接: {target_url} ...")
            # 打开目标页面，延长至 60 秒且只要内容加载即可，不再盲目等待完全 networkidle
            try:
                page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"⚠️ 页面加载提示（不影响抓取）: {e}")
                
            print("\n等待页面加载...")
            time.sleep(5)
            
            # 判断是否跳转到了单视频页面
            if "/video/" in page.url or "/note/" in page.url:
                print("检测到单视频详情页，直接下载作品...")
                match = re.search(r'/(?:video|note)/(\d+)', page.url)
                if match:
                    aweme_id = match.group(1)
                    try:
                        data = page.evaluate(f"""async () => {{
                            const res = await fetch('/aweme/v1/web/aweme/detail/?device_platform=webapp&aid=6383&channel=channel_pc_web&aweme_id={aweme_id}');
                            return await res.json();
                        }}""")
                        if data and "aweme_detail" in data:
                            process_aweme_item(data["aweme_detail"], is_single=True)
                        else:
                            print("未找到 aweme_detail 数据。")
                    except Exception as e:
                        print(f"获取单视频数据失败: {e}")
                else:
                    print("无法从 URL 提取视频 ID。")
                
                # 等待当前单视频的下载线程完成
                if active_futures:
                    print(f"正在下载视频，等待完成...")
                    concurrent.futures.wait(active_futures)
                    active_futures.clear()
                    print("🎉 下载成功！")
                
                if single_run:
                    break
                continue
                
            print("\n检测到主页链接，开始配置筛选条件...")
            global FILTER_KEYWORD, START_DATETIME, END_DATETIME
            
            FILTER_KEYWORD = input("请输入筛选关键字 (仅下载包含该关键字的作品，直接回车不过滤): ").strip()
            
            start_str = input("请输入开始日期时间 (格式: YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS，直接回车不限制): ").strip()
            START_DATETIME = parse_datetime_input(start_str, is_end=False)
            
            end_str = input("请输入结束日期时间 (格式: YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS，直接回车不限制): ").strip()
            END_DATETIME = parse_datetime_input(end_str, is_end=True)
            
            print(f"\n准备开始全自动向下滚动主页: {target_url}")
            print("--------------------------------------------------")
            print("[当前设置的过滤条件]")
            print(f"  - 关键字: {FILTER_KEYWORD if FILTER_KEYWORD else '无'}")
            print(f"  - 开始时间: {START_DATETIME if START_DATETIME else '无'}")
            print(f"  - 结束时间: {END_DATETIME if END_DATETIME else '无'}")
            print("--------------------------------------------------")
            
            global last_data_time
            last_data_time = time.time()  # 开始滚动前重置一次时间
            scroll_count = 0
            
            try:
                # 循环滚到底部，触发懒加载分页
                while True:
                    scroll_count += 1
                    print(f"\n往下滚动加载中 (第 {scroll_count} 拨)... ⭐ 觉得够了随时可以按 Ctrl+C 提前停止！")
                    
                    # 物理滚轮与JS滑动
                    viewport = page.viewport_size
                    if viewport:
                        page.mouse.move(viewport['width'] / 2, viewport['height'] / 2)
                    for _ in range(3):
                        page.mouse.wheel(0, 3000)
                        time.sleep(0.5)
    
                    page.evaluate("""() => {
                        const cont = document.querySelector('.route-scroll-container') || window;
                        if (cont && cont.scrollBy) {
                            cont.scrollBy(0, 5000);
                        }
                    }""")
                    time.sleep(2) # 等待列表新一批内容刷出
                    
                    idle_time = time.time() - last_data_time
                    if idle_time > 15:
                        print("🎉 检测到连续 15 秒没有任何新作品数据入账。数据已经到底啦！")
                        break
                    else:
                        print(f"数据持续流入中 (最后一次收到数据是在 {int(idle_time)} 秒前)...")
            except KeyboardInterrupt:
                print("\n⚠️ 收到中止指令！正在安全退出，您已抓取的数据均已自动保存... ⚠️")
            
            print("网页浏览完毕，等候所有后台下载任务完成...")
            if active_futures:
                print(f"正在等待当前批次的 {len(active_futures)} 个下载任务完成...")
                concurrent.futures.wait(active_futures)
                active_futures.clear()
            print("主页抓取任务完成！")
            
            if single_run:
                break
        
        # 退出循环后关闭 context
        context.close()
        
    # 关闭全局线程池
    executor.shutdown(wait=True)
    print("全部抓取任务结束！")

DOWNLOAD_DIR = "downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

if __name__ == "__main__":
    main()
