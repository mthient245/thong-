"""Bot theo dõi page Facebook của trường và báo @everyone lên Discord.

Chỉ dùng thư viện chuẩn của Python 3.8+.
Cấu hình qua biến môi trường (xem README.md).
"""
import html
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET

FEED_URL = os.environ["FEED_URL"]                  # link RSS của page Facebook
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]    # webhook của kênh Discord
INTERVAL = int(os.environ.get("INTERVAL", "300"))  # giây giữa các lần kiểm tra
# Từ khóa lọc bài (để trống = báo mọi bài). Phân cách bằng dấu phẩy.
KEYWORDS = [k.strip().lower() for k in os.environ.get(
    "KEYWORDS", "rèn luyện,điểm rèn luyện,DRL,hoạt động,cộng điểm").split(",") if k.strip()]
STATE_FILE = os.environ.get("STATE_FILE", "seen.json")
UA = {"User-Agent": "Mozilla/5.0 (school-fb-discord-bot)"}


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def fetch_posts():
    """Trả về list dict(id, title, link, text) từ RSS hoặc Atom."""
    root = ET.fromstring(http(FEED_URL))
    posts = []
    for item in root.iter():
        tag = item.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        d = {}
        for ch in item:
            t = ch.tag.split("}")[-1]
            if t == "link":
                d["link"] = ch.get("href") or (ch.text or "").strip()
            elif t in ("guid", "id"):
                d["id"] = (ch.text or "").strip()
            elif t == "title":
                d["title"] = clean(ch.text)
            elif t in ("description", "summary", "content"):
                d["text"] = clean(ch.text)
        d.setdefault("link", "")
        d.setdefault("id", d["link"] or d.get("title", ""))
        d.setdefault("title", "")
        d.setdefault("text", "")
        posts.append(d)
    return posts


def matches(post):
    if not KEYWORDS:
        return True
    blob = (post["title"] + " " + post["text"]).lower()
    return any(k in blob for k in KEYWORDS)


def notify(post):
    snippet = (post["text"] or post["title"])[:300]
    content = (
        "@everyone 📢 **Page trường vừa đăng bài mới!**\n"
        f"{snippet}\n{post['link']}"
    )
    payload = {
        "content": content[:1900],
        # bắt buộc để @everyone thực sự ping
        "allowed_mentions": {"parse": ["everyone"]},
    }
    http(WEBHOOK_URL, json.dumps(payload).encode(),
         {"Content-Type": "application/json"})


def load_seen():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return set(data) if data else None
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_seen(seen):
    if not seen:
        return
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f)


def main():
    seen = load_seen()
    first_run = seen is None
    seen = seen or set()
    while True:
        try:
            posts = fetch_posts()
            if first_run:
                if not posts:
                    # feed còn trống: chờ có bài rồi mới khởi tạo, tránh báo nhầm bài cũ
                    print("Feed chưa có bài nào, chờ lần kiểm tra sau...", flush=True)
                else:
                    # lần đầu chỉ ghi nhớ bài cũ, không spam
                    seen.update(p["id"] for p in posts)
                    first_run = False
                    print(f"Khởi tạo: đã ghi nhớ {len(seen)} bài.", flush=True)
            else:
                for p in reversed(posts):  # cũ -> mới
                    if p["id"] in seen:
                        continue
                    seen.add(p["id"])
                    if matches(p):
                        notify(p)
                        print("Đã báo:", p["link"], flush=True)
            save_seen(seen)
        except Exception as e:  # không để bot chết vì lỗi mạng
            print("Lỗi:", e, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()