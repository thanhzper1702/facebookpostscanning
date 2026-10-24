import asyncio
from playwright.async_api import async_playwright
import sys
sys.path.insert(0, r"d:\postercontest")
from scraper import parse_post_html

FB_SESSION_DIR = r"d:\postercontest\fb_session"
POST_URL = "https://www.facebook.com/permalink.php?story_fbid=122315804252064502&id=149883148199221"

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
            print("Navigating to post...")
            await page.goto(POST_URL, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            html = await page.content()
            data = parse_post_html(html, post_url=POST_URL)
            print("parse_post_html results:")
            print("reactions_total:", data.get("reactions_total"))
            print("reactions_breakdown:", data.get("reactions_breakdown"))
            print("comments_total:", data.get("comments_total"))
            print("shares_total:", data.get("shares_total"))

            # Also check if data-ad-rendering-role="share_button" exists in html
            print("data-ad-rendering-role='share_button' in html?:", 'data-ad-rendering-role="share_button"' in html)

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
