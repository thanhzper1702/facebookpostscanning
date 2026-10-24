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

            # Scroll post container to reveal the reaction counter
            target_rect = await page.evaluate("""() => {
                const candidates = [];
                for (const el of document.querySelectorAll('div[role="button"], span[role="toolbar"]')) {
                    const aria = el.getAttribute('aria-label') || '';
                    if (
                        aria.includes('Thích:') || 
                        aria.includes('Yêu thích:') || 
                        aria.includes('Xem ai đã bày tỏ cảm xúc')
                    ) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) {
                            candidates.push({ el, aria, rect: { x: r.x, y: r.y, w: r.width, h: r.height } });
                        }
                    }
                }
                if (candidates.length > 0) {
                    const target = candidates[0];
                    target.el.scrollIntoView({ block: 'center', behavior: 'instant' });
                    const r2 = target.el.getBoundingClientRect();
                    return { x: r2.x + r2.width/2, y: r2.y + r2.height/2, aria: target.aria };
                }
                return null;
            }""")

            print(f"Target reaction trigger: {target_rect}")
            assert target_rect is not None, "Target not found!"

            print(f"Clicking at ({target_rect['x']}, {target_rect['y']}) with mouse.click...")
            await page.mouse.click(target_rect['x'], target_rect['y'])

            # Poll for the REAL reaction dialog (one containing Love/Like tabs)
            reaction_modal = None
            for step in range(12):
                await asyncio.sleep(0.5)
                dialogs = await page.locator('div[role="dialog"]').all()
                for d in dialogs:
                    tabs = await d.locator('div[role="tab"], [role="tab"]').all()
                    tab_texts = []
                    for t in tabs:
                        a = await t.get_attribute("aria-label") or ""
                        txt = await t.inner_text() or ""
                        tab_texts.append(a + " " + txt)
                    
                    # A real reaction modal has tabs for Yêu thích or Thích
                    comb = " ".join(tab_texts).lower()
                    if "yêu thích" in comb or "thích" in comb or "love" in comb or "like" in comb:
                        reaction_modal = d
                        print(f"SUCCESS: Found real reaction modal with {len(tabs)} tabs at step {step}!")
                        for idx, tt in enumerate(tab_texts):
                            print(f"  Tab {idx}: {tt}")
                        break
                if reaction_modal:
                    break

            assert reaction_modal is not None, "Reaction modal failed to open!"

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
