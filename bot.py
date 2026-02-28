import asyncio
from playwright.async_api import async_playwright
import telebot
import time

# ================== CONFIG ==================

TOKEN = "7864236625:AAEj66g9NjqGTplyf4UoLczTP77wj76UIaY"

SHORTS_CHANNEL = "-1002524650614"
MEDIUM_CHANNEL = "-1002575035304"
LONG_CHANNEL = "-1002509561008"

MAX_VIDEOS = 200

# ============================================

bot = telebot.TeleBot(TOKEN)

visited = set()
queue = []
collected = []
running = False


# ================== CRAWLER ==================

async def crawl_site(start_url):
    global running, visited, queue, collected

    visited.clear()
    queue.clear()
    collected.clear()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        page = await browser.new_page()
        media_urls = set()

        # Capture network responses
        async def handle_response(response):
            try:
                url = response.url.lower()

                if any(ext in url for ext in [".mp4", ".m3u8", ".webm"]):
                    media_urls.add(response.url)

                content_type = response.headers.get("content-type", "")
                if "video" in content_type:
                    media_urls.add(response.url)

            except:
                pass

        page.on("response", handle_response)

        queue.append(start_url)

        while queue and len(collected) < MAX_VIDEOS and running:

            current_url = queue.pop(0)

            if current_url in visited:
                continue

            visited.add(current_url)

            try:
                print("Visiting:", current_url)

                await page.goto(current_url, timeout=60000)
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(5000)

                title = await page.title()

                # Try direct video tag
                duration = await page.evaluate("""
                () => {
                    const v = document.querySelector("video");
                    return v ? v.duration : null;
                }
                """)

                thumbnail = await page.evaluate("""
                () => {
                    const v = document.querySelector("video");
                    return v ? v.poster : null;
                }
                """)

                # Fallback iframe
                iframe_src = await page.evaluate("""
                () => {
                    const iframe = document.querySelector("iframe");
                    return iframe ? iframe.src : null;
                }
                """)

                if iframe_src:
                    print("Found iframe:", iframe_src)

                # Extract internal links
                links = await page.evaluate("""
                () => Array.from(document.querySelectorAll("a"))
                    .map(a => a.href)
                    .filter(h => h.includes("/video"))
                """)

                for link in links:
                    if link not in visited:
                        queue.append(link)

                # Get latest detected media
                video_src = None
                if media_urls:
                    video_src = list(media_urls)[-1]

                if video_src:

                    collected.append({
                        "title": title,
                        "duration": duration if duration else 600,
                        "video": video_src,
                        "thumbnail": thumbnail,
                        "source": current_url
                    })

                    print("Collected:", len(collected))

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
                if v["thumbnail"]:
                    bot.send_photo(channel, v["thumbnail"])

                bot.send_video(channel, v["video"], caption=caption)

                time.sleep(2)

            except Exception as e:
                print("Send error:", e)

    send_list(shorts, SHORTS_CHANNEL)
    send_list(medium, MEDIUM_CHANNEL)
    send_list(long, LONG_CHANNEL)

    bot.reply_to(message, "Videos sent to channels.")


print("Bot Running...")
bot.infinity_polling()
