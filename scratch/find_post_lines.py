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

            # Find post element (main or article or dialog)
            post_info = await page.evaluate("""() => {
                const results = [];
                // Find all elements that look like action buttons or stat counts
                for (const el of document.querySelectorAll('div[role="main"], div[role="dialog"]:not([aria-label="Messenger"])')) {
                    const text = el.innerText || '';
                    if (text.includes('BÌNH CHỌN') || text.includes('Ngô Quyền')) {
                        // Scan for lines with counts
                        const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
                        return lines.slice(50, 150);
                    }
                }
                return ['Post not found in dialogs'];
            }""")
            print("Post lines:")
            for l in post_info:
                print(" ", repr(l))

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
