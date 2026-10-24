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

            # Test finding and clicking reaction trigger using JavaScript scrollIntoView + click
            click_result = await page.evaluate("""() => {
                // Find all candidate reaction buttons on the page with coordinates
                const candidates = [];
                for (const el of document.querySelectorAll('div[role="button"], span[role="toolbar"]')) {
                    const aria = el.getAttribute('aria-label') || '';
                    if (
                        aria.includes('Thích:') || 
                        aria.includes('Yêu thích:') || 
                        aria.includes('Xem ai đã bày tỏ cảm xúc') ||
                        (aria.includes('người') && !aria.includes('bình luận') && !aria.includes('chia sẻ'))
                    ) {
                        const r = el.getBoundingClientRect();
                        // Ignore hidden elements with 0 width or height
                        if (r.width > 0 && r.height > 0) {
                            candidates.push({ el, aria, rect: { x: r.x, y: r.y, w: r.width, h: r.height } });
                        }
                    }
                }
                
                if (candidates.length === 0) {
                    return { success: false, reason: 'No visible candidates found' };
                }

                // Pick the candidate that has 'Xem ai đã bày tỏ cảm xúc' or 'Yêu thích:' or highest y
                candidates.sort((a, b) => b.rect.y - a.rect.y);
                const target = candidates[0];
                target.el.scrollIntoView({ block: 'center', behavior: 'instant' });
                target.el.click();
                return { success: true, aria: target.aria, rect: target.rect };
            }""")
            print("JS Click Result:", click_result)

            # Wait and check for dialog with tabs
            modal = None
            for step in range(12):
                await asyncio.sleep(0.5)
                # Find dialog that actually has role="tab"
                dialogs = await page.locator('div[role="dialog"]').all()
                for d in dialogs:
                    tab_count = await d.locator('div[role="tab"], [role="tab"]').count()
                    if tab_count > 0:
                        modal = d
                        print(f"SUCCESS: Found reaction modal with {tab_count} tabs at step {step}!")
                        break
                if modal:
                    break

            if not modal:
                print("JS click did not open modal, trying mouse click at bounding box...")
                if click_result.get('success'):
                    # Refresh bounding box after scroll
                    rect = await page.evaluate("""() => {
                        const el = document.querySelector('div[role="button"][aria-label*="Yêu thích:"], div[role="button"][aria-label*="Thích:"]');
                        if (el) {
                            el.scrollIntoView({ block: 'center', behavior: 'instant' });
                            const r = el.getBoundingClientRect();
                            return { x: r.x + r.width/2, y: r.y + r.height/2 };
                        }
                        return null;
                    }""")
                    if rect:
                        print(f"Mouse clicking at: {rect}")
                        await page.mouse.click(rect['x'], rect['y'])
                        for step in range(10):
                            await asyncio.sleep(0.5)
                            dialogs = await page.locator('div[role="dialog"]').all()
                            for d in dialogs:
                                tab_count = await d.locator('div[role="tab"], [role="tab"]').count()
                                if tab_count > 0:
                                    modal = d
                                    print(f"SUCCESS via mouse click: Found {tab_count} tabs!")
                                    break
                            if modal:
                                break

            assert modal is not None, "Failed to open reaction modal!"

            # Check tabs
            tabs = await modal.locator('div[role="tab"], [role="tab"]').all()
            for idx, t in enumerate(tabs):
                aria = await t.get_attribute("aria-label") or ""
                txt = await t.inner_text() or ""
                print(f"  Tab {idx}: aria={aria!r}, txt={txt!r}")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
