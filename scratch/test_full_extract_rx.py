import asyncio
import os
import sys
from playwright.async_api import async_playwright

FB_SESSION_DIR = r"d:\postercontest\fb_session"
POST_URL = "https://www.facebook.com/permalink.php?story_fbid=122315804252064502&id=149883148199221"

sys.path.insert(0, r"d:\postercontest")
from scraper import FacebookScraper

async def report(stage, pct, msg, counts=None):
    print(f"[{pct}%] {stage}: {msg}")

async def main():
    scraper = FacebookScraper()
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

            print("Extracting reactions with FacebookScraper._extract_reactions...")
            res = await scraper._extract_reactions(page, report)
            print(f"Total extracted reactions: {len(res)}")
            love_count = sum(1 for r in res if "love" in r.get("reason", "").lower() or r.get("interaction_type") == "Love Reaction")
            like_count = sum(1 for r in res if "like" in r.get("reason", "").lower() or r.get("interaction_type") == "Like Reaction")
            print(f"Sample breakdown: {len(res)} total items")
            types = {}
            for r in res:
                t = r.get("interaction_type", "unknown")
                types[t] = types.get(t, 0) + 1
            print("Types count:", types)
        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
