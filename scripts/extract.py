#!/usr/bin/env python3
"""抖音视频文案提取主链路（分发版，无本机硬编码路径）
用法:
  python extract.py --url "https://v.douyin.com/xxxx"
  python extract.py --file /path/to/video.mp4   # 兜底分支：手动传文件
流程: 下载音频 -> SenseVoice ASR -> DeepSeek 摘要/要点/标签 -> Markdown 入 Obsidian
配置: ~/.config/video-transcript/.env (API Keys) + config.json (vault_dir)
"""
import argparse, hashlib, json, os, re, subprocess, sys, tempfile, time, unicodedata
from datetime import datetime
from pathlib import Path

CONFIG_DIR = Path.home() / ".config/video-transcript"
ENV_FILE = CONFIG_DIR / ".env"
CONFIG_FILE = CONFIG_DIR / "config.json"

SF_API = "https://api.siliconflow.cn/v1/audio/transcriptions"
SF_MODEL = "FunAudioLLM/SenseVoiceSmall"
DS_API = "https://api.deepseek.com/chat/completions"
DS_MODEL = "deepseek-chat"


def get_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("❌ 未安装 imageio-ffmpeg，请先运行 scripts/setup.sh")


def load_config():
    if not ENV_FILE.exists():
        sys.exit(f"❌ 未找到 {ENV_FILE}\n请先在终端运行: bash scripts/setup-keys.sh")
    env = {}
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    for k in ("SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY"):
        if not env.get(k):
            sys.exit(f"❌ {ENV_FILE} 缺少 {k}，请重新运行 scripts/setup-keys.sh")
    if not CONFIG_FILE.exists():
        sys.exit(f"❌ 未找到 {CONFIG_FILE}（Obsidian 目录配置），请先运行 scripts/setup.sh")
    cfg = json.loads(CONFIG_FILE.read_text())
    vault_dir = Path(os.path.expanduser(cfg.get("vault_dir", "")))
    if not vault_dir:
        sys.exit(f"❌ {CONFIG_FILE} 中 vault_dir 为空，请重新运行 scripts/setup.sh")
    return env, vault_dir


def http_post(url, headers, data=None, files=None, json_body=None, timeout=300):
    """用 urllib 发请求，零第三方依赖"""
    import urllib.request, urllib.error
    req = urllib.request.Request(url, headers=headers)
    if json_body is not None:
        req.data = json.dumps(json_body).encode()
        req.add_header("Content-Type", "application/json")
    elif files is not None:
        boundary = "----pyboundary" + os.urandom(8).hex()
        body = b""
        for k, v in (data or {}).items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, (fname, fdata, ctype) in files.items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\nContent-Type: {ctype}\r\n\r\n'.encode() + fdata + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req.data = body
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"❌ HTTP {e.code}: {e.read()[:500].decode(errors='replace')}")


def slugify(s, maxlen=30):
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r'[\\/:*?"<>|\n\r\t]', "", s).strip()
    return s[:maxlen] or "未命名"


COOKIE_FILE = CONFIG_DIR / "cookies.txt"
SETUP_COOKIES = Path(__file__).parent / "setup-cookies.sh"


CACHE_DIR = CONFIG_DIR / "cache"
RETRY_WAIT = 30  # 下载失败后重试间隔（秒），避免触发抖音风控


def _cache_paths(url):
    key = hashlib.md5(url.encode()).hexdigest()[:12]
    return CACHE_DIR / f"{key}.mp3", CACHE_DIR / f"{key}.json"


def clear_cache(url):
    """全流程成功后调用：清理该链接的音频缓存（失败时保留供重试）"""
    try:
        for p in _cache_paths(url):
            p.unlink(missing_ok=True)
        print("🧹 已清理本次音频缓存", flush=True)
    except Exception:
        pass


def download_audio(url, workdir, ffmpeg):
    """yt-dlp + 导出的 cookie 文件下载音频，返回 (音频路径, 元信息dict)。
    cookie 文件由用户在终端运行 setup-cookies.sh 一次性导出（Agent 沙箱无法写钥匙串，
    自动导出会得到不完整的 cookie），过期时同样引导用户重跑该脚本。
    反爬纪律：1) 下载成功的音频按链接缓存，ASR 等后续环节失败重跑时不再请求抖音；
    2) 下载失败最多自动重试 1 次，且先等待 RETRY_WAIT 秒；仍失败即退出，不连续重试。"""
    out_tpl = str(workdir / "%(id)s.%(ext)s")
    if not COOKIE_FILE.exists():
        sys.exit(f"❌ 缺少 cookie 文件。请在你自己的终端运行一次（今后不再弹钥匙串窗口）:\n"
                 f"  bash {SETUP_COOKIES}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_audio, cached_meta = _cache_paths(url)
    if cached_audio.exists() and cached_meta.exists():
        print("♻️ 命中音频缓存，跳过下载（避免触发抖音风控）...", flush=True)
        return cached_audio, json.loads(cached_meta.read_text())
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--cookies", str(COOKIE_FILE),
        "-x", "--audio-format", "mp3",
        "--ffmpeg-location", ffmpeg,
        "--write-info-json", "--no-playlist",
        "-o", out_tpl, url,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        print(f"⏳ 下载失败，等待 {RETRY_WAIT} 秒（避免触发风控）后重试最后一次...", flush=True)
        time.sleep(RETRY_WAIT)
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        sys.exit("❌ yt-dlp 解析失败（已按反爬纪律重试 1 次仍失败）。\n"
                 "对策：\n"
                 "  1) 至少间隔几分钟后再试（短时间连续请求会被抖音临时风控）\n"
                 f"  2) 在终端重跑 cookie 导出: bash {SETUP_COOKIES}\n"
                 "  3) 仍失败则 Chrome 重新登录 douyin.com 后再跑一遍上面的命令\n"
                 "  4) 升级 yt-dlp: pip install -U yt-dlp；5) 抖音 App 保存视频后改用 --file 兜底。\n"
                 f"错误详情:\n{p.stderr[-800:]}")
    meta = {}
    infos = list(workdir.glob("*.info.json"))
    if infos:
        d = json.loads(infos[0].read_text())
        raw_title = (d.get("title") or "").split("\n")[0].strip()
        meta = {"title": raw_title[:60],
                "author": d.get("uploader") or d.get("creator") or d.get("channel") or "",
                "url": d.get("webpage_url", url), "duration": d.get("duration", 0)}
    audios = list(workdir.glob("*.mp3"))
    if not audios:
        sys.exit("❌ 未找到下载后的音频文件")
    # 写入缓存：后续环节（ASR/DeepSeek）失败重跑时直接复用，不再请求抖音
    audios[0].replace(cached_audio)
    cached_meta.write_text(json.dumps(meta, ensure_ascii=False))
    return cached_audio, meta


def extract_audio_from_file(video, workdir, ffmpeg):
    out = workdir / (Path(video).stem + ".mp3")
    subprocess.run([ffmpeg, "-y", "-i", str(video), "-vn", "-acodec", "libmp3lame", "-q:a", "4", str(out)],
                   capture_output=True, timeout=300, check=True)
    return out, {"title": Path(video).stem, "author": "", "url": "", "duration": 0}


def asr(audio_path, key, attempts=5):
    """ASR 转写。硅基流动部分后端节点不稳定，5xx 属常见临时错误，做有限次退避重试"""
    for i in range(attempts):
        try:
            resp = http_post(
                SF_API,
                headers={"Authorization": f"Bearer {key}"},
                data={"model": SF_MODEL},
                files={"file": (audio_path.name, audio_path.read_bytes(), "audio/mpeg")},
                timeout=600,
            )
            text = (resp.get("text") or "").strip()
            if not text:
                sys.exit(f"❌ ASR 返回空: {json.dumps(resp, ensure_ascii=False)[:300]}")
            return text
        except SystemExit as e:
            if "HTTP 5" in str(e) and i < attempts - 1:
                print(f"⏳ ASR 服务端临时错误（5xx），5 秒后重试（{i+1}/{attempts-1}）...", flush=True)
                time.sleep(5)
                continue
            raise


def deepseek_polish(transcript, meta, key):
    prompt = (
        "你是知识管理助手。以下是一段抖音视频的口播逐字稿，请输出 JSON（不要 markdown 代码块）：\n"
        '{"summary": "80字内摘要", "points": ["要点1","要点2","要点3"], "tags": ["标签1","标签2","标签3"], "formatted": "分段排版后的逐字稿全文"}\n'
        "要求：\n"
        "- 要点提炼 3-7 条，每条一句话；标签 3-5 个，短词；忠实原文，不虚构\n"
        "- formatted 字段：把逐字稿按语义自然分段（话题/意思转换处分段，每段 1-4 句话，段间空一行），"
        "修正明显错误的断句和标点；严禁改写、润色、删减或增补任何内容；"
        "人名、品牌、术语即使 ASR 识别有误也保持原样；英文句子保留原样\n\n"
        f"视频标题：{meta.get('title','')}\n逐字稿：\n{transcript[:20000]}"
    )
    resp = http_post(
        DS_API,
        headers={"Authorization": f"Bearer {key}"},
        json_body={"model": DS_MODEL, "messages": [{"role": "user", "content": prompt}],
                   "response_format": {"type": "json_object"}, "temperature": 0.3},
        timeout=600,
    )
    content = resp["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"summary": content[:100], "points": [], "tags": [], "formatted": ""}


def write_markdown(vault_dir, meta, transcript, polish):
    vault_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    fname = f"{date}-{slugify(meta.get('title') or '抖音视频')}.md"
    path = vault_dir / fname
    dur = meta.get("duration") or 0
    dur_str = f"{dur//60}:{dur%60:02d}" if dur else "未知"
    tags = polish.get("tags", [])
    lines = [
        "---",
        f'title: "{(meta.get("title") or "").replace(chr(34), "")}"',
        f'author: "{meta.get("author","")}"',
        f'source: "{meta.get("url","")}"',
        f"extracted: {date}",
        f"duration: \"{dur_str}\"",
        "tags: [" + ", ".join(tags) + "]",
        "---",
        "",
        "## 摘要",
        polish.get("summary", ""),
        "",
        "## 要点",
    ]
    lines += [f"- {p}" for p in polish.get("points", [])]
    # 原文优先使用 DeepSeek 分段排版版（保真，仅分段/修标点）；缺失时回退 ASR 原始文本
    lines += ["", "## 原文", polish.get("formatted") or transcript, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--url")
    g.add_argument("--file")
    args = ap.parse_args()

    env, vault_dir = load_config()
    ffmpeg = get_ffmpeg()
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        if args.url:
            url = args.url.strip()
            m = re.search(r"https?://v\.douyin\.com/\S+", url) or re.search(r"https?://\S*douyin\.com/\S+", url)
            if m:
                url = m.group(0)
            print("⏬ 解析并下载音频...", flush=True)
            audio, meta = download_audio(url, workdir, ffmpeg)
        else:
            print("⏬ 从本地文件提取音频...", flush=True)
            audio, meta = extract_audio_from_file(args.file, workdir, ffmpeg)
        print(f"🎙 ASR 转写中（{audio.stat().st_size//1024}KB）...", flush=True)
        transcript = asr(audio, env["SILICONFLOW_API_KEY"])
        print("🧠 DeepSeek 生成摘要/要点/标签...", flush=True)
        polish = deepseek_polish(transcript, meta, env["DEEPSEEK_API_KEY"])
        path = write_markdown(vault_dir, meta, transcript, polish)
        if args.url:
            clear_cache(url)  # 全流程成功才清理；任何环节失败则保留缓存供重试
        print("\n✅ 完成")
        print(f"📄 {path}")
        print(f"\n【摘要】{polish.get('summary','')}")
        if polish.get("points"):
            print("【要点】")
            for p in polish["points"]:
                print(f"  - {p}")
        print(f"【标签】{', '.join(polish.get('tags', []))}")
        print(f"\n【原文预览】{transcript[:200]}...")


if __name__ == "__main__":
    main()
