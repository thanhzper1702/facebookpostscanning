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

            # Let's find reaction modal
            triggers = [
                'div[role="button"][aria-label*="người"]:not([aria-label*="bình luận"])',
                'div[role="button"][aria-label*="Thích:"]',
                'div[role="button"][aria-label*="Yêu thích:"]',
                'span[role="toolbar"][aria-label*="Xem ai đã bày tỏ cảm xúc"]',
                'div[role="button"]:has(span[role="toolbar"])',
            ]

            reaction_modal = None
            for sel in triggers:
                loc = page.locator(sel)
                count = await loc.count()
                print(f"Selector {sel!r}: count={count}")
                for i in range(count):
                    el = loc.nth(i)
                    try:
                        print(f"  Attempting click on {sel} (index {i})...")
                        # Scroll into view if needed
                        try:
                            await el.scroll_into_view_if_needed(timeout=1000)
                        except Exception:
                            pass
                        await el.click(timeout=2500, force=True)

                        # Check for reaction modal
                        for _ in range(8):
                            await asyncio.sleep(0.5)
                            for d in await page.locator('div[role="dialog"]').all():
                                tabs = await d.locator('div[role="tab"], [role="tab"]').all()
                                if len(tabs) >= 2:
                                    t_labels = []
                                    for t in tabs:
                                        a = await t.get_attribute("aria-label") or ""
                                        txt = await t.inner_text() or ""
                                        t_labels.append((a + " " + txt).lower())
                                    comb = " ".join(t_labels)
                                    if any(k in comb for k in ["yêu thích", "love", "thích", "like", "tất cả"]):
                                        if not any(k in comb for k in ["chưa đọc", "cộng đồng"]):
                                            reaction_modal = d
                                            print(f"  -> SUCCESS: Reaction modal found with {len(tabs)} tabs!")
                                            break
                            if reaction_modal:
                                break
                    except Exception as ex:
                        print(f"  Error clicking: {ex}")
                    if reaction_modal:
                        break
                if reaction_modal:
                    break

            assert reaction_modal is not None, "Failed to open reaction modal!"
            print("REACTION MODAL CONFIRMED OPEN!")

            tabs = await reaction_modal.locator('div[role="tab"], [role="tab"]').all()
            for idx, t in enumerate(tabs):
                aria = await t.get_attribute("aria-label") or ""
                txt = await t.inner_text() or ""
                print(f"  Tab {idx}: aria={aria!r}, txt={txt!r}")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
