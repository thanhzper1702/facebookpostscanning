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

            # Inspect post container
            print("Searching for share elements inside the post...")
            shares_info = await page.evaluate("""() => {
                const results = [];
                // Look for elements with text "chia sẻ" or "share" or numbers followed by chia sẻ
                for (const el of document.querySelectorAll('span, div[role="button"], a')) {
                    const txt = (el.innerText || '').trim();
                    const aria = (el.getAttribute('aria-label') || '').trim();
                    if (/chia\\s*sẻ|share/i.test(txt) || /chia\\s*sẻ|share/i.test(aria)) {
                        if (txt.length < 80 && !txt.includes('Đoạn chat') && !txt.includes('thông báo')) {
                            const r = el.getBoundingClientRect();
                            results.push({
                                tag: el.tagName,
                                role: el.getAttribute('role'),
                                aria: aria,
                                text: txt.replace(/\\n/g, ' '),
                                x: Math.round(r.x),
                                y: Math.round(r.y),
                                w: Math.round(r.width),
                                h: Math.round(r.height),
                                visible: r.width > 0 && r.height > 0
                            });
                        }
                    }
                }
                return results;
            }""")
            for i, s in enumerate(shares_info):
                print(f"[{i}] {s['tag']} role={s['role']} aria={s['aria']!r} txt={s['text']!r} vis={s['visible']} (x={s['x']}, y={s['y']})")


        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
