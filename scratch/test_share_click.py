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

            # Let's see what is near the reactions / comments counter
            # In Facebook desktop, above the Like/Comment/Share buttons, there is a counter bar:
            # e.g., "191 người khác", "91 bình luận", "X lượt chia sẻ"
            print("Searching for counter bar...")
            counters = await page.evaluate("""() => {
                const results = [];
                for (const el of document.querySelectorAll('span, a, div[role="button"]')) {
                    const txt = (el.innerText || '').trim();
                    if (/\\d+\\s*(bình luận|chia sẻ|người|lượt)/i.test(txt) || /^\\d+$/.test(txt)) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0 && txt.length < 50) {
                            results.push({
                                tag: el.tagName,
                                role: el.getAttribute('role'),
                                aria: el.getAttribute('aria-label'),
                                txt: txt,
                                x: Math.round(r.x),
                                y: Math.round(r.y)
                            });
                        }
                    }
                }
                return results;
            }""")
            for c in counters:
                print(f"Counter: {c['tag']} role={c['role']} aria={c['aria']!r} txt={c['txt']!r} at ({c['x']}, {c['y']})")

            # Now let's see what happens if we click the button with txt='31'
            share_btn = page.locator('div[role="button"][aria-label*="Chia sẻ"]:has-text("31")').first
            if await share_btn.count() > 0:
                print("\nClicking button with text '31'...")
                dialogs_before = len(await page.locator('div[role="dialog"]').all())
                await share_btn.scroll_into_view_if_needed()
                await share_btn.click(force=True)
                await asyncio.sleep(3)
                dialogs_after = len(await page.locator('div[role="dialog"]').all())
                print(f"Dialogs before: {dialogs_before}, after: {dialogs_after}")
                
                # Check what opened
                if dialogs_after > dialogs_before:
                    new_dialog = (await page.locator('div[role="dialog"]').all())[-1]
                    d_text = (await new_dialog.inner_text()).replace('\n', ' ')[:200]
                    print(f"New dialog text: {d_text!r}")
                else:
                    # Maybe a popup menu or flyout opened?
                    popups = await page.evaluate("""() => {
                        const menus = document.querySelectorAll('div[role="menu"], div[role="listbox"], div[data-pagelet*="Share"]');
                        return Array.from(menus).map(m => m.innerText.replace(/\\n/g, ' ').substring(0, 200));
                    }""")
                    print(f"Popups found: {popups}")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
