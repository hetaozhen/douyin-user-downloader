# Douyin User Downloader  
**Batch No-Watermark Media Downloader for Douyin User Profiles**

English | [简体中文](README.md)


An automated data collection tool built on the powerful Playwright and Python engines. It enables fully automated, seamless batch scraping and downloading of **all videos** and **all image-text posts** from any specified Douyin user profile.

---

## 🌟 Key Features

- **Bypass CDN Hotlinking Restrictions**: Perfectly emulates authentic Chrome browser behavior, including core authentication headers (`User-Agent` and `Referer`), effectively resolving `403 Forbidden` errors encountered when accessing direct video streams.
- **Smart Virtual List Scrolling**: Designed for user homepage batch scraping. By injecting physical `Mouse Wheel` events and `Targeted JS Scrolling` directly into the container, it triggers Douyin's dynamic loading, ensuring 100% rendering of all content.
- **Low-Level Network Stream Monitoring**: Listens directly to the `/aweme/v1/web/aweme/post/` API packets. It ignores frontend UI lag, gracefully concluding the task only after 15 seconds of zero incoming data packets, ensuring no video is ever missed.
- **Smart Single Video / Homepage Routing**: Allows pasting raw text containing a single video share link. The app extracts the URL using `https?://[^\s]+` and automatically routes to single video mode or batch homepage mode. Single video mode downloads the video immediately and exits without scrolling.
- **Multi-Dimensional Filters**: Prompts for interactive filter criteria after entering the link. You can filter by **keyword**, **start date**, and **end date** (press Enter to skip filters).
- **Date-Based Naming Format**: Replaces the bulky work ID at the end of filenames with a publication date-time prefix in `[YYYYMMDD_HHMMSS]_[Title]` format.
- **Persistent Session Protection (Stealth Mode)**: Supports persistent Cookie storage. After the initial login, the tool defaults to a "Stealth Mode" (`Headless Mode`) for background execution. If a rare anti-bot slider captcha appears, the window can be instantly toggled for manual resolution.
- **Extreme Concurrency & Intelligent Retries**: Features a high-efficiency thread pool module. In cases of packet loss or rate-limiting, it automatically waits and retries after 2 seconds, ensuring reliability even in harsh network conditions.

---

## 🚀 Quick Start Guide

### 1. Install Dependencies
You will need Python along with the Playwright driver environment.
```bash
pip install playwright requests
playwright install chromium
```

### 2. Start Scraping!
Launch the main script in your terminal and enter the target profile link when prompted:
```bash
python douyin_user_downloader.py
```
> Or run it directly with a link:
> `python douyin_user_downloader.py "https://www.douyin.com/user/xxxxxx"`

### 3. Where is the Data?
All high-definition images and no-watermark videos are automatically categorized and archived in the `downloads/[Author Name]/` directory relative to the script location.

---

## ⚠️ Disclaimer
This project is intended for academic exchange, programming research, and personal legal data backup only. Do not use this tool for any illegal purposes or commercial gain. Please respect the copyrights and hard work of all content creators.
