import asyncio
from playwright.async_api import async_playwright

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

            # Let's see: on Facebook, when looking at the post, is there a text or link that says "31 lượt chia sẻ" or similar?
            # Let's inspect all text in the post dialog
            dialog = page.locator('div[role="dialog"]').first
            text = await dialog.inner_text()
            print("Dialog text snippet:")
            for line in text.splitlines():
                if any(w in line.lower() for w in ['chia sẻ', 'share', 'bình luận', 'thích', 'yêu thích']):
                    print("  Line:", repr(line.strip()))

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
