import asyncio
from playwright.async_api import async_playwright

FB_SESSION_DIR = r"d:\postercontest\fb_session"
POST_URL = "https://www.facebook.com/share/p/1JWAbvVLEm/"

async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=FB_SESSION_DIR,
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--disable-notifications"],
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            print("Navigating to user post URL...")
            await page.goto(POST_URL, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)
            print("Current URL:", page.url)

            # Inspect post action buttons and numbers
            post_stats = await page.evaluate("""() => {
                const res = [];
                for (const el of document.querySelectorAll('div[role="button"], span')) {
                    const aria = el.getAttribute('aria-label') || '';
                    const txt = (el.innerText || '').trim();
                    if (/thích|yêu thích|bình luận|chia sẻ/i.test(aria) || /thích|yêu thích|bình luận|chia sẻ/i.test(txt)) {
                        if (txt.length < 50 || aria.length < 80) {
                            res.push({
                                tag: el.tagName,
                                role: el.getAttribute('role'),
                                aria: aria,
                                text: txt.replace(/\\n/g, ' ')
                            });
                        }
                    }
                }
                return res;
            }""")
            print("Post stats found:")
            for s in post_stats:
                print(" ", s)

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
