import os
import json
import re
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright



headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/122.0.0.0 Safari/537.36',
    'Referer': 'https://www.douyin.com/',
}


def extract_short_url(text):
    share_url_pattern = r'(https?://[^\s]+)'
    match = re.search(share_url_pattern, text)
    if not match:
        raise ValueError('❌ 分享链接无效')
    return match.group(1)


def get_real_url(share_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        video_info = {}

        # 捕获xhr接口返回
        def handle_route(route, request):
            route.continue_()

        def handle_response(response):
            try:
                if 'aweme/v1/web/aweme/detail/' in response.url:
                    if response.ok:
                        json_body = response.json()
                        play_url_list = json_body['aweme_detail']['video']['play_addr']['url_list']
                        if play_url_list:
                            video_info['url'] = play_url_list[0].replace('playwm', 'play')
            except Exception as e:
                print(f'解析 aweme detail 出错: {e}')

        context.on("response", handle_response)

        context.route("**/*", handle_route)

        # 访问分享短链接
        page.goto(share_url, timeout=60000)
        page.wait_for_timeout(3000)

        # 访问跳转后的真实视频链接
        real_url = page.url
        print(f"跳转后真实URL: {real_url}")

        video_id_pattern = r'/video/(\d+)'
        match = re.search(video_id_pattern, real_url)
        if not match:
            raise ValueError('未能提取到视频ID')
        video_id = match.group(1)

        video_page_url = f"https://www.douyin.com/video/{video_id}"
        page.goto(video_page_url, timeout=60000)

        # 留足够时间让接口加载完
        page.wait_for_timeout(5000)

        if 'url' not in video_info:
            raise ValueError('未能提取到播放地址')

        browser.close()
        return video_info['url']


def extract_note_id(real_url):
    match = re.search(r'/(explore|discovery/item)/([0-9a-fA-F]+)', real_url)
    return match.group(2) if match else None


def get_video_url(real_url):
    resp = requests.get(real_url, headers=headers)
    # print("resp.text: ", resp.text)

    html_text = resp.text
    resp = requests.get(real_url, headers=headers)
    # html_text = resp.text
    #
    # # 找到所有包含 masterUrl 和 qualityType 的片段
    # pattern = r'"masterUrl"\s*:\s*"([^"]+\.mp4)".*?"qualityType"\s*:\s*"HD"'
    # match = re.search(pattern, html_text, re.DOTALL)
    # if not match:
    #     print("❌ 未找到 HD 清晰度视频链接")
    #     return None
    #
    # raw_url = match.group(1)
    # decoded_url = raw_url.encode('utf-8').decode('unicode_escape').replace("\\", "")
    # return decoded_url

    soup = BeautifulSoup(resp.text, "html.parser")
    # print("resp beautiful soup: ", soup)
    script_tag = soup.find("script", string=re.compile("window.__INITIAL_STATE__="))
    print("resp beautiful soup script tag: ", script_tag)
    if not script_tag:
        return None

    json_text = script_tag.string.strip().replace("window.__INITIAL_STATE__=", "").rstrip(";")
    json_text = json_text.replace("undefined", "null")
    print("resp json text:", json_text)

    try:
        data = json.loads(json_text)
        # print("data: ", data)
    except json.JSONDecodeError as e:
        print("❌ JSON 解析失败：", e)
        return None


    try:
        h265_streams = data["noteData"]["data"]["noteData"]["video"]["media"]["stream"]["h265"]
        if h265_streams:
            raw_url = h265_streams[0]["masterUrl"]
            if not raw_url:
                raw_url = h265_streams[0]["backupUrls"][0]
            clean_url = raw_url.encode('utf-8').decode('unicode_escape').replace("\\", "")
            return clean_url

    except Exception as e:
        print("❌ 视频地址提取失败：", e)
        return None


def download_video(video_url, filename):
    resp = requests.get(video_url, headers=headers, stream=True)
    with open(filename, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
    print(f"✅ 下载完成: {filename}")


CONFIG_FILE = "config.json"


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_user_input_gui():
    config = load_config()
    last_dir = config.get("last_save_dir", os.path.expanduser("~"))
    filename_prefix = config.get("filename_prefix", "douyin_")


    def choose_directory():
        folder = filedialog.askdirectory(title="选择保存目录", initialdir=last_dir)
        if folder:
            save_dir_var.set(folder)

    def on_confirm():
        url = url_text.get("1.0", tk.END).strip().strip()
        save_dir = save_dir_var.get().strip()

        if not url or not save_dir:
            messagebox.showerror("错误", "请填写链接并选择保存目录。")
            return

        config["last_save_dir"] = save_dir
        config["last_filename"] = filename_prefix.strip()

        save_config(config)
        root.quit()  # 关闭主窗口

    root = tk.Tk()
    root.title("视频下载设置")
    root.geometry("500x300")
    root.resizable(False, False)

    tk.Label(root, text="分享链接:").pack(pady=(15, 5))
    url_text = tk.Text(root, height=5, width=60)  # 多行输入框
    url_text.pack()

    link_btn_frame = tk.Frame(root)
    link_btn_frame.pack(pady=(5, 5))

    tk.Button(link_btn_frame, text="粘贴分享链接", command=lambda: url_text.insert(tk.END, root.clipboard_get())).pack(
        side=tk.LEFT, padx=5)
    tk.Button(link_btn_frame, text="清空分享链接", command=lambda: url_text.delete("1.0", tk.END)).pack(side=tk.LEFT,
                                                                                                        padx=5)

    tk.Label(root, text="保存目录:").pack(pady=(10, 5))
    save_dir_var = tk.StringVar(value=last_dir)
    save_dir_frame = tk.Frame(root)
    save_dir_frame.pack()
    tk.Entry(save_dir_frame, textvariable=save_dir_var, width=45).pack(side=tk.LEFT)
    tk.Button(save_dir_frame, text="浏览", command=choose_directory).pack(side=tk.LEFT, padx=5)

    tk.Button(root, text="下载", command=on_confirm, width=10).pack(pady=15)

    root.mainloop()

    return url_text.get("1.0", tk.END).strip(), save_dir_var.get().strip()
def generate_filename_with_date(prefix="video", extension="mp4"):
    now = datetime.now()
    date_str = now.strftime("%Y%m%d_%H%M%S")  # 格式化日期时间
    filename = f"{prefix}{date_str}.{extension}"
    return filename


def run_gui():
    config = load_config()
    last_dir = config.get("last_save_dir", os.path.expanduser("~"))
    filename_prefix = config.get("filename_prefix", "douyin_")

    def choose_directory():
        folder = filedialog.askdirectory(title="选择保存目录", initialdir=last_dir)
        if folder:
            save_dir_var.set(folder)

    def start_download():
        url = url_text.get("1.0", tk.END).strip()
        save_dir = save_dir_var.get().strip()

        if not url or not save_dir:
            messagebox.showerror("错误", "请填写链接并选择保存目录。")
            return

        config["last_save_dir"] = save_dir
        save_config(config)

        try:
            share_url = extract_short_url(url)
            real_url = get_real_url(share_url)

            if not save_dir.endswith(os.path.sep):
                save_dir += os.path.sep
            filename_input = filename_var.get().strip()
            filename = save_dir + generate_filename_with_date(prefix=filename_input, extension="mp4")

            download_video(real_url, filename)
            messagebox.showinfo("成功", f"✅ 下载完成：{filename}")

        except Exception as e:
            print("❌ 错误：", e)
            messagebox.showerror("下载失败", str(e))

    # === GUI 部分 ===
    root = tk.Tk()
    root.title("抖音视频下载")
    root.geometry("500x380")
    root.resizable(False, True)

    tk.Label(root, text="分享链接:").pack(pady=(15, 5))
    url_text = tk.Text(root, height=5, width=60)
    url_text.pack()

    link_btn_frame = tk.Frame(root)
    link_btn_frame.pack(pady=(5, 5))
    tk.Button(link_btn_frame, text="粘贴分享链接", command=lambda: url_text.insert(tk.END, root.clipboard_get())).pack(side=tk.LEFT, padx=5)
    tk.Button(link_btn_frame, text="清空分享链接", command=lambda: url_text.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=5)

    tk.Label(root, text="保存前缀:").pack(pady=(10, 5))
    filename_var = tk.StringVar(value=filename_prefix)
    filename_frame = tk.Frame(root)
    filename_frame.pack()
    tk.Entry(filename_frame, textvariable=filename_var, width=50).pack(side=tk.LEFT)

    tk.Label(root, text="保存目录:").pack(pady=(10, 5))
    save_dir_var = tk.StringVar(value=last_dir)
    save_dir_frame = tk.Frame(root)
    save_dir_frame.pack()
    tk.Entry(save_dir_frame, textvariable=save_dir_var, width=45).pack(side=tk.LEFT)
    tk.Button(save_dir_frame, text="浏览", command=choose_directory).pack(side=tk.LEFT, padx=5)

    tk.Button(root, text="下载", command=start_download, width=10).pack(pady=15)

    root.mainloop()


if __name__ == "__main__":
    run_gui()
