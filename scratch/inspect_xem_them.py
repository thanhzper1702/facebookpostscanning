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

            # Let's inspect the buttons with text 'Xem thêm'
            xem_them_info = await page.evaluate("""() => {
                const buttons = document.querySelectorAll('div[role="button"], span');
                const list = [];
                for (const b of buttons) {
                    const t = (b.innerText || '').trim();
                    if (t === 'Xem thêm' || t.startsWith('Xem thêm') || t.includes('bình luận')) {
                        const r = b.getBoundingClientRect();
                        list.push({
                            text: t,
                            tag: b.tagName,
                            role: b.getAttribute('role'),
                            aria: b.getAttribute('aria-label'),
                            html: b.outerHTML.substring(0, 150),
                            rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }
                        });
                    }
                }
                return list;
            }""")
            print(f"Total matching buttons: {len(xem_them_info)}")
            for idx, item in enumerate(xem_them_info):
                if item['rect']['w'] > 0 and item['rect']['h'] > 0:
                    print(f"[{idx}] text={item['text']!r}, tag={item['tag']}, role={item['role']}, rect={item['rect']}")

            # Let's see what happens if we click buttons that are in the comments section (y > 600)
            print("\nTesting clicks on visible 'Xem thêm' buttons in comments area:")
            for idx, item in enumerate(xem_them_info):
                if item['rect']['w'] > 0 and item['rect']['h'] > 0 and item['rect']['y'] > 600:
                    print(f"Trying to click button [{idx}]: {item['text']!r} at {item['rect']}...")
                    articles_before = await page.locator('div[role="article"]').count()
                    await page.mouse.click(item['rect']['x'] + item['rect']['w']/2, item['rect']['y'] + item['rect']['h']/2)
                    await asyncio.sleep(2)
                    articles_after = await page.locator('div[role="article"]').count()
                    print(f"  Result: articles count: {articles_before} -> {articles_after}")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
