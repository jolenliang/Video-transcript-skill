# Video-transcript-skill

抖音视频口播文案 → AI 摘要 → Obsidian 笔记，一条链接全自动。

粘贴抖音分享链接给你的 AI Agent，30-90 秒后得到一篇带 **摘要 / 要点 / 标签 / 原文** 的 Markdown 笔记，自动存进你的 Obsidian。

## 一键安装（复制这句话发给你的 AI Agent）

> **帮我安装这个 skill 并配置好：https://github.com/jolenliang/Video-transcript-skill**

Agent 会自动完成克隆、环境搭建、Obsidian 目录检测。你只需要：

1. **录入两个 API Key**（Agent 会引导你在自己终端输入，不回显、不经过对话）：
   - 硅基流动 [siliconflow.cn](https://siliconflow.cn)（免费，语音转文字）
   - DeepSeek [platform.deepseek.com](https://platform.deepseek.com)（摘要加工，每条约 1 分钱）
2. **Chrome 登录一次 [douyin.com](https://www.douyin.com)**（扫码即可，用于链接解析）

装完后，粘贴任何抖音链接说「提取文案」即可。解析失败时的兜底：抖音 App 保存视频 → 直接拖给 Agent。

## 效果示例

```markdown
---
title: "下一批 AI 大公司，可能根本不是软件公司"
source: "https://www.douyin.com/video/767..."
extracted: 2026-08-29
duration: "1:39"
tags: [AI创业, 服务公司, YC, 商业模式, AI运营杠杆]
---
## 摘要
YC合伙人认为，AI创业下一波不是做软件工具，而是直接重建服务公司……
## 要点
- AI原生服务公司卖结果，而非工具或席位
- ……
## 原文
（完整逐字稿）
```

## 工作原理

```
抖音链接 → yt-dlp 下载音频（Chrome cookie）
        → 硅基流动 SenseVoice 语音转文字（免费）
        → DeepSeek 生成摘要/要点/标签
        → Markdown 写入 Obsidian 目录
```

视频和音频本身**不落盘**，只保留文字笔记。

## 系统要求

- macOS（Windows 适配计划中）
- python3 ≥ 3.9、git、Chrome

## 隐私与安全

- 两个 API Key 只存储在你本机 `~/.config/video-transcript/.env`（权限 600，仅你可读），不会进入对话记录，本仓库也不包含任何 Key
- 除调用硅基流动 / DeepSeek 官方 API 外，无任何网络请求
- 请仅用于个人学习用途的内容沉淀

## 手动安装（不使用 Agent 的备选）

见 [INSTALL.md](INSTALL.md)，按 Step 1-6 手动执行即可。

## License

MIT
