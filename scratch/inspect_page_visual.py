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

            # Screenshot 1: initial view
            await page.screenshot(path="scratch/page_top.png")
            print("Saved scratch/page_top.png")

            # Scroll down to comments
            await page.mouse.wheel(0, 1000)
            await asyncio.sleep(2)
            await page.screenshot(path="scratch/page_comments.png")
            print("Saved scratch/page_comments.png")

            # Let's inspect what elements have scrollbars or where the comments are:
            scrollables = await page.evaluate("""() => {
                const results = [];
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if (el.scrollHeight > el.clientHeight + 100 && el.clientHeight > 200) {
                        const s = window.getComputedStyle(el);
                        if (s.overflowY === 'auto' || s.overflowY === 'scroll') {
                            results.push({
                                tag: el.tagName,
                                role: el.getAttribute('role'),
                                class: el.className,
                                scrollHeight: el.scrollHeight,
                                clientHeight: el.clientHeight,
                                scrollTop: el.scrollTop
                            });
                        }
                    }
                }
                return results;
            }""")
            print(f"Scrollable elements found: {len(scrollables)}")
            for s in scrollables:
                print(" ", s)

            # Let's also see what text appears below the comments:
            post_text_blocks = await page.evaluate("""() => {
                const el = document.querySelector('div[role="main"]') || document.body;
                return el.innerText.split('\\n').filter(t => t.trim().length > 0).slice(0, 50);
            }""")
            print("\nFirst 50 lines of main content:")
            for l in post_text_blocks:
                print("  |", l)

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
