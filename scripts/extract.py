#!/usr/bin/env python3
"""抖音视频文案提取主链路（分发版，无本机硬编码路径）
用法:
  python extract.py --url "https://v.douyin.com/xxxx"
  python extract.py --file /path/to/video.mp4   # 兜底分支：手动传文件
流程: 下载音频 -> SenseVoice ASR -> pending Markdown -> Agent 后处理入 Obsidian
配置: ~/.config/video-transcript/.env (SiliconFlow API Key) + config.json (vault_dir)
"""
import argparse, hashlib, json, os, re, subprocess, sys, tempfile, time, unicodedata
from datetime import datetime
from pathlib import Path

CONFIG_DIR = Path.home() / ".config/video-transcript"
ENV_FILE = CONFIG_DIR / ".env"
CONFIG_FILE = CONFIG_DIR / "config.json"

SF_API = "https://api.siliconflow.cn/v1/audio/transcriptions"
SF_MODEL = "FunAudioLLM/SenseVoiceSmall"


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
    for k in ("SILICONFLOW_API_KEY",):
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
PENDING_DIR = CONFIG_DIR / "pending"
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
    # 写入缓存：后续环节（ASR 或 pending 写入）失败重跑时直接复用，不再请求抖音
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


def _yaml_quote(value):
    value = "" if value is None else str(value)
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def _duration_string(duration):
    duration = int(duration or 0)
    return f"{duration // 60}:{duration % 60:02d}" if duration else "未知"


def _pending_identity(platform, meta, transcript):
    identity = meta.get("url") or "|".join(
        (platform, meta.get("title", ""), meta.get("author", ""), transcript)
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]


def write_pending(pending_dir, platform, meta, transcript, extracted=None):
    """Write the complete extracted text for the Agent to process later."""
    pending_dir.mkdir(parents=True, exist_ok=True)
    extracted = extracted or datetime.now().strftime("%Y-%m-%d")
    title = meta.get("title") or ("小红书笔记" if platform == "xhs" else "抖音视频")
    suffix = _pending_identity(platform, meta, transcript)
    path = pending_dir / f"{extracted}-{slugify(title)}-{suffix}.md"
    lines = [
        "---",
        "type: video-transcript-pending",
        "status: pending",
        f"platform: {platform}",
        f"title: {_yaml_quote(title)}",
        f"author: {_yaml_quote(meta.get('author', ''))}",
        f"source: {_yaml_quote(meta.get('url', ''))}",
        f"extracted: {extracted}",
        f"duration: {_yaml_quote(_duration_string(meta.get('duration')))}",
        "---",
        "",
        "## 原始文案",
        transcript,
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def detect_platform(url):
    if "xhslink.cn" in url or "xiaohongshu.com" in url:
        return "xhs"
    return "douyin"


def notes_dir_for(vault_dir, platform):
    """笔记按平台分目录：抖音用配置的目录（默认 I-抖音文案），小红书用同级 I-小红书文案"""
    if platform == "xhs":
        return vault_dir.parent / "I-小红书文案"
    return vault_dir


def fetch_xhs_metadata(url, ffmpeg):
    """小红书笔记元数据（匿名即可，无需 cookie；有 cookie 文件则顺带使用）。
    返回 (meta, has_video, 正文)。遵守反爬纪律：失败等 30 秒只重试 1 次。"""
    cmd = [sys.executable, "-m", "yt_dlp", "-j", "--simulate", "--no-playlist",
           "--ignore-no-formats-error", "--ffmpeg-location", ffmpeg]
    if COOKIE_FILE.exists():
        cmd += ["--cookies", str(COOKIE_FILE)]
    cmd.append(url)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if p.returncode != 0 or not p.stdout.strip():
        print(f"⏳ 解析失败，等待 {RETRY_WAIT} 秒（避免触发风控）后重试最后一次...", flush=True)
        time.sleep(RETRY_WAIT)
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if p.returncode != 0 or not p.stdout.strip():
        sys.exit("❌ 小红书链接解析失败（已按反爬纪律重试 1 次仍失败）。\n"
                 "对策：\n"
                 "  1) 至少间隔几分钟后再试（短时间连续请求会被风控）\n"
                 "  2) 确认链接完整：从小红书 App 重新复制（需带 xsec_token 参数）\n"
                 "  3) 升级 yt-dlp: pip install -U yt-dlp\n"
                 f"错误详情:\n{p.stderr[-500:]}")
    d = json.loads(p.stdout.strip().splitlines()[-1])
    meta = {"title": (d.get("title") or "").split("\n")[0].strip()[:60],
            "author": d.get("uploader") or d.get("creator") or d.get("channel") or "",
            "url": d.get("webpage_url", url),
            "duration": d.get("duration") or 0}
    return meta, bool(d.get("formats")), (d.get("description") or "").strip()


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
        platform = "douyin"
        if args.url:
            url = args.url.strip()
            m = re.search(r"https?://\S*(?:douyin\.com|xhslink\.cn|xiaohongshu\.com)\S*", url)
            if m:
                url = m.group(0)
            platform = detect_platform(url)
            if platform == "xhs":
                print("⏬ 解析小红书笔记...", flush=True)
                meta, has_video, note_text = fetch_xhs_metadata(url, ffmpeg)
                if has_video:
                    print("🎬 视频笔记，下载音频...", flush=True)
                    audio, vmeta = download_audio(url, workdir, ffmpeg)
                    meta = {**meta, **{k: v for k, v in vmeta.items() if v}}
                    print(f"🎙 ASR 转写中（{audio.stat().st_size//1024}KB）...", flush=True)
                    transcript = asr(audio, env["SILICONFLOW_API_KEY"])
                else:
                    print("📝 图文笔记，提取正文...", flush=True)
                    if not note_text:
                        sys.exit("❌ 未提取到正文（笔记可能已删除或需要登录）")
                    transcript = note_text
            else:
                print("⏬ 解析并下载音频...", flush=True)
                audio, meta = download_audio(url, workdir, ffmpeg)
                print(f"🎙 ASR 转写中（{audio.stat().st_size//1024}KB）...", flush=True)
                transcript = asr(audio, env["SILICONFLOW_API_KEY"])
        else:
            print("⏬ 从本地文件提取音频...", flush=True)
            audio, meta = extract_audio_from_file(args.file, workdir, ffmpeg)
            print(f"🎙 ASR 转写中（{audio.stat().st_size//1024}KB）...", flush=True)
            transcript = asr(audio, env["SILICONFLOW_API_KEY"])
        path = write_pending(PENDING_DIR, platform, meta, transcript)
        if args.url:
            clear_cache(url)  # pending 文件成功写入后清理；失败时保留缓存供重试
        print("\n✅ 提取完成，等待 Agent 后处理")
        print(f"PENDING_FILE={path}")
        print("Agent 请读取该文件的完整内容，写入最终 Obsidian 笔记并验证成功后再删除它。")
        print(f"\n【原文预览】{transcript[:200]}...")


if __name__ == "__main__":
    main()
