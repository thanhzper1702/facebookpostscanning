import asyncio
from playwright.async_api import async_playwright
import urllib.parse

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
            # Search query for the post URL or fbid
            search_url = f"https://www.facebook.com/search/posts/?q={urllib.parse.quote(POST_URL)}"
            print(f"Navigating to search URL: {search_url}")
            await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            # Check if any posts sharing this link are listed
            print("Checking search results...")
            feed_items = await page.evaluate("""() => {
                const results = [];
                // Look for user profile links who posted
                for (const a of document.querySelectorAll('a[role="link"]')) {
                    const href = a.getAttribute('href') || '';
                    const txt = (a.innerText || '').trim();
                    if (txt && !txt.includes('Menu') && !txt.includes('Facebook') && !href.includes('search') && !href.includes('permalink.php')) {
                        results.push({ href: href.split('?')[0], name: txt.replace(/\\n/g, ' ') });
                    }
                }
                return results;
            }""")
            print(f"Found {len(feed_items)} links:")
            for item in feed_items[:15]:
                print(item)

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
