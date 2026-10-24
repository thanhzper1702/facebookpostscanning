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

            dialogs_before = len(await page.locator('div[role="dialog"]').all())
            print(f"Dialogs count before click: {dialogs_before}")

            # Let's see what elements have reaction icons or text
            triggers = [
                'div[role="button"][aria-label*="người"]:not([aria-label*="bình luận"])',
                'div[role="button"]:has(img[alt="Thích"])',
                'div[role="button"]:has(img[alt="Like"])',
                'div[role="button"]:has(img[alt="Yêu thích"])',
                'div[role="button"]:has(span[role="toolbar"])',
                '[aria-label="Xem ai đã bày tỏ cảm xúc về tin này"]',
                '[data-ad-rendering-role="like_button"]',
            ]

            for sel in triggers:
                loc = page.locator(sel)
                count = await loc.count()
                print(f"Selector {sel!r}: count={count}")
                for i in range(count):
                    el = loc.nth(i)
                    try:
                        vis = await el.is_visible()
                        box = await el.bounding_box()
                        aria = await el.get_attribute("aria-label")
                        txt = (await el.inner_text()).replace('\n', ' ')
                        print(f"  [{i}] vis={vis}, aria={aria!r}, txt={txt!r}, box={box}")
                    except Exception as e:
                        print(f"  [{i}] error: {e}")

            # Also check ANY element with aria-label containing 'người' or 'bày tỏ' or 'cảm xúc'
            print("\nAll elements on page with aria-label mentioning reactions:")
            aria_els = await page.evaluate("""() => {
                const res = [];
                for (const el of document.querySelectorAll('*')) {
                    const a = el.getAttribute('aria-label') || '';
                    if (a.includes('người') || a.includes('cảm xúc') || a.includes('Thích:') || a.includes('Yêu thích:')) {
                        const r = el.getBoundingClientRect();
                        res.push({
                            tag: el.tagName,
                            role: el.getAttribute('role'),
                            aria: a,
                            rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }
                        });
                    }
                }
                return res;
            }""")
            for a in aria_els:
                print(" ", a)

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
