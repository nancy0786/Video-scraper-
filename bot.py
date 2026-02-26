import asyncio
from playwright.async_api import async_playwright
import telebot
import time

# ================== CONFIG ==================

TOKEN = ""

# --- Paste Channel IDs Below ---
SHORTS_CHANNEL = "-1002524650614"
MEDIUM_CHANNEL = "-1002575035304"
LONG_CHANNEL = "-1002509561008"

MAX_VIDEOS = 20000  # limit for safety

# ============================================

bot = telebot.TeleBot(TOKEN)

visited = set()
queue = []
collected = []

running = False


# ================== CRAWLER ==================

async def crawl_site(start_url):
    global running

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()

        queue.append(start_url)

        while queue and len(collected) < MAX_VIDEOS and running:
            url = queue.pop(0)

            if url in visited:
                continue

            visited.add(url)

            try:
                await page.goto(url, timeout=60000)
                await page.wait_for_timeout(2000)

                title = await page.title()

                # Try extracting video duration via JS
                duration = await page.evaluate("""
                () => {
                    const video = document.querySelector("video");
                    return video ? video.duration : null;
                }
                """)

                # Extract video source
                video_src = await page.evaluate("""
                () => {
                    const video = document.querySelector("video");
                    return video ? video.currentSrc : null;
                }
                """)

                # Extract thumbnail
                thumbnail = await page.evaluate("""
                () => {
                    const video = document.querySelector("video");
                    return video ? video.poster : null;
                }
                """)

                # Extract related links
                links = await page.evaluate("""
                () => {
                    let anchors = Array.from(document.querySelectorAll("a"));
                    return anchors.map(a => a.href);
                }
                """)

                for link in links:
                    if "/video" in link and link not in visited:
                        queue.append(link)

                if duration and duration > 120:  # ignore <2min
                    collected.append({
                        "title": title,
                        "duration": duration,
                        "video": video_src,
                        "thumbnail": thumbnail,
                        "source": url
                    })

                print(f"Collected: {len(collected)}")

            except Exception as e:
                print("Error:", e)

        await browser.close()


# ================== BOT COMMANDS ==================

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Send starting video URL to begin crawling.")


@bot.message_handler(func=lambda m: m.text.startswith("http"))
def begin_crawl(message):
    global running
    running = True

    url = message.text.strip()
    bot.reply_to(message, "Crawling started...")

    asyncio.run(crawl_site(url))

    bot.reply_to(message, "Crawling finished.")


@bot.message_handler(commands=['stop'])
def stop_crawl(message):
    global running
    running = False

    shorts = [v for v in collected if 120 < v["duration"] <= 300]
    medium = [v for v in collected if 300 < v["duration"] <= 900]
    long = [v for v in collected if v["duration"] > 900]

    text = f"""
Total Videos Found: {len(collected)}

Shorts (2-5 min): {len(shorts)}
Medium (5-15 min): {len(medium)}
Long (>15 min): {len(long)}
"""

    bot.reply_to(message, text)


@bot.message_handler(commands=['send'])
def send_videos(message):
    shorts = [v for v in collected if 120 < v["duration"] <= 300]
    medium = [v for v in collected if 300 < v["duration"] <= 900]
    long = [v for v in collected if v["duration"] > 900]

    def send_list(video_list, channel):
        for v in video_list:
            caption = f"""
{v['title']}

Duration: {int(v['duration']//60)} min
Source: {v['source']}

#video #content
"""
            try:
                bot.send_photo(channel, v["thumbnail"])
                bot.send_video(channel, v["video"], caption=caption)
                time.sleep(2)
            except:
                pass

    send_list(shorts, SHORTS_CHANNEL)
    send_list(medium, MEDIUM_CHANNEL)
    send_list(long, LONG_CHANNEL)

    bot.reply_to(message, "Videos sent to channels.")


print("Bot Running...")
bot.infinity_polling()
