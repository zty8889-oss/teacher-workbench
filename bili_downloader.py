#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站番剧/视频下载器（修复版）
依赖: pip install requests
用法: python3 bili_downloader.py <B站链接>
"""

import requests, re, json, os, sys, time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}

def extract_json(text, start_marker):
    """从页面提取 JSON 对象（处理嵌套花括号）"""
    idx = text.find(start_marker)
    if idx < 0: return None
    start = idx + len(start_marker)
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{': depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i+1])
    return None

def parse_bangumi(url):
    """解析番剧页面，返回视频流地址"""
    r = requests.get(url, headers=HEADERS, timeout=15)
    
    # 方案1: 从 playurlSSRData 提取（番剧页面）
    data = extract_json(r.text, "playurlSSRData = ")
    if data and data.get("status") == 200:
        vi = data["data"]["result"]["video_info"]
        dash = vi.get("dash", {})
        durl = vi.get("durl", [])
        # 获取标题
        ep_info = data["data"]["result"].get("episode_id_info", {})
        title = ep_info.get("index_title", "") or ep_info.get("title", "视频")
        
        if durl:
            # 单文件（含音频）
            return {
                "type": "single",
                "title": title,
                "url": durl[0]["url"],
                "size": durl[0].get("size", 0),
                "quality": vi.get("format", "未知"),
            }
        elif dash:
            v = max(dash["video"], key=lambda v: v.get("height", 0) * 10000 + v.get("bandwidth", 0))
            a = max(dash["audio"], key=lambda a: a.get("bandwidth", 0))
            vu = v.get("baseUrl") or v.get("base_url", "")
            au = a.get("baseUrl") or a.get("base_url", "")
            return {
                "type": "dash",
                "title": title,
                "video_url": vu,
                "audio_url": au,
                "height": v.get("height", 0),
                "quality": vi.get("format", "未知"),
                "vsize": v.get("size", 0),
                "asize": a.get("size", 0),
            }
    
    # 方案2: 从 __NEXT_DATA__ 提取（通用页面）
    nd = extract_json(r.text, '<script id="__NEXT_DATA__" type="application/json">')
    if nd:
        queries = nd.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
        for q in queries:
            qk = json.dumps(q.get("queryKey", []))
            if "season" in qk or "playurl" in qk.lower():
                state = q.get("state", {}).get("data", {})
                if state:
                    # 递归查找 playurl
                    return _find_playurl(state, "番剧")
    
    # 方案3: 普通视频（BV/AV号）
    m = re.search(r'window\.__playinfo__\s*=\s*({.*?});?\s*</script>', r.text, re.S)
    if m:
        pi = json.loads(m.group(1))
        data = pi.get("data", {})
        dash = data.get("dash", {})
        if dash and dash.get("video"):
            v = max(dash["video"], key=lambda v: v.get("height", 0) * 10000 + v.get("bandwidth", 0))
            a = max(dash["audio"], key=lambda a: a.get("bandwidth", 0))
            vu = v.get("baseUrl") or v.get("base_url", "")
            au = a.get("baseUrl") or a.get("base_url", "")
            title = _extract_title(r.text)
            return {
                "type": "dash", "title": title or "视频",
                "video_url": vu, "audio_url": au,
                "height": v.get("height", 0), "quality": f"{v.get('height',0)}p",
                "vsize": v.get("size", 0), "asize": a.get("size", 0),
            }
    
    return None

def _find_playurl(obj, title="视频"):
    """递归查找 playurl 数据"""
    if isinstance(obj, dict):
        if "dash" in obj and "video" in obj.get("dash", {}):
            d = obj["dash"]
            v = max(d["video"], key=lambda v: v.get("height", 0) * 10000 + v.get("bandwidth", 0))
            a = max(d["audio"], key=lambda a: a.get("bandwidth", 0))
            vu = v.get("baseUrl") or v.get("base_url", "")
            au = a.get("baseUrl") or a.get("base_url", "")
            return {"type": "dash", "title": title, "video_url": vu, "audio_url": au,
                    "height": v.get("height", 0), "quality": f"{v.get('height',0)}p",
                    "vsize": v.get("size", 0), "asize": a.get("size", 0)}
        for k, v in obj.items():
            r = _find_playurl(v, k)
            if r: return r
    elif isinstance(obj, list):
        for item in obj:
            r = _find_playurl(item, title)
            if r: return r
    return None

def _extract_title(html):
    m = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
    return m.group(1).replace('-哔哩哔哩', '').replace('-bilibili', '').strip() if m else None

def download_file(url, out_path, label=""):
    """下载文件"""
    r = requests.get(url, headers=HEADERS, stream=True, timeout=(12, 300))
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))
    dl = 0
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(65536):
            if chunk:
                f.write(chunk)
                dl += len(chunk)
                if total > 0:
                    pct = dl * 100 // total
                    print(f"\r   {label}: {pct}% ({dl//1024//1024}MB/{total//1024//1024}MB)", end="")
    size = os.path.getsize(out_path) / 1024 / 1024
    print(f"\n   ✅ {label}: {size:.1f}MB")
    return True

def main():
    if len(sys.argv) < 2:
        print("用法: python3 bili_downloader.py <B站链接>")
        sys.exit(1)
    
    url = sys.argv[1]
    print(f"🔍 解析: {url}")
    
    info = parse_bangumi(url)
    if not info:
        print("❌ 无法解析视频地址")
        sys.exit(1)
    
    print(f"\n📺 {info['title']}")
    print(f"🎬 画质: {info['quality']} ({info.get('height', '?')}p)")
    
    has_ffmpeg = False
    try:
        import shutil
        has_ffmpeg = shutil.which("ffmpeg") is not None
    except: pass
    
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', info['title'])
    out_dir = os.path.join(os.path.expanduser("~"), "Downloads", "B站番剧")
    os.makedirs(out_dir, exist_ok=True)
    
    if info['type'] == 'single':
        out_file = os.path.join(out_dir, f"{safe_name}.mp4")
        print(f"\n⬇️ 下载中... ({info.get('size', 0)//1024//1024}MB)")
        download_file(info['url'], out_file, "下载")
        print(f"\n✅ 完成: {out_file}")
    
    elif info['type'] == 'dash':
        v_file = os.path.join(out_dir, f"{safe_name}_video.mp4")
        a_file = os.path.join(out_dir, f"{safe_name}_audio.m4a")
        out_file = os.path.join(out_dir, f"{safe_name}.mp4")
        vs = info.get('vsize', 0) // 1024 // 1024
        a_s = info.get('asize', 0) // 1024 // 1024
        print(f"\n⬇️ 音视频分离 (视频 {vs}MB + 音频 {a_s}MB)")
        
        download_file(info['video_url'], v_file, "视频")
        
        if has_ffmpeg:
            download_file(info['audio_url'], a_file, "音频")
            print("\n🔗 ffmpeg 合并中...")
            import subprocess
            r = subprocess.run(["ffmpeg", "-y", "-i", v_file, "-i", a_file,
                                "-c:v", "copy", "-c:a", "aac", "-strict", "experimental", out_file],
                               capture_output=True, text=True, timeout=600)
            os.remove(v_file)
            os.remove(a_file)
            if r.returncode == 0:
                print(f"✅ 完成: {out_file} ({os.path.getsize(out_file)//1024//1024}MB)")
            else:
                print(f"❌ 合并失败: {r.stderr[-200:]}")
        else:
            os.rename(v_file, out_file) if os.path.exists(v_file) else None
            print(f"\n⚠️ 无 ffmpeg，只有视频流（无声音）")
            print(f"✅ 完成: {out_file}")

if __name__ == "__main__":
    main()
