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

            # Let's open the reaction modal
            triggers = [
                'div[role="button"][aria-label*="người"]:not([aria-label*="bình luận"]):not([aria-label*="chia sẻ"])',
                'div[role="button"][aria-label*="Thích:"]',
                'div[role="button"][aria-label*="Yêu thích:"]',
                'div[role="button"]:has(img[alt="Thích"])',
                'div[role="button"]:has(img[alt="Like"])',
                'div[role="button"]:has(img[alt="Yêu thích"])',
                'span[role="toolbar"][aria-label*="Xem ai đã bày tỏ cảm xúc"]',
            ]

            reaction_modal = None
            for sel in triggers:
                loc = page.locator(sel)
                count = await loc.count()
                if count > 0:
                    for i in range(count):
                        el = loc.nth(i)
                        try:
                            try:
                                await el.scroll_into_view_if_needed(timeout=1000)
                            except Exception:
                                pass
                            await el.click(timeout=2500, force=True)
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
                                                break
                                if reaction_modal:
                                    break
                        except Exception as e:
                            print(f"Trigger {sel} error: {e}")
                        if reaction_modal:
                            break
                if reaction_modal:
                    break

            if not reaction_modal:
                print("ERROR: reaction modal not found!")
                return

            print("SUCCESS: Found reaction modal!")
            tabs = await reaction_modal.locator('div[role="tab"], [role="tab"]').all()
            print(f"Found {len(tabs)} tabs.")
            for i, t in enumerate(tabs):
                aria = await t.get_attribute("aria-label") or ""
                txt = await t.inner_text() or ""
                html = await t.inner_html() or ""
                print(f"\n--- TAB [{i}] ---")
                print(f"aria-label: {aria.encode('utf-8', errors='replace')}")
                print(f"inner_text: {txt.encode('utf-8', errors='replace')}")
                print(f"html snippet: {html[:150].encode('utf-8', errors='replace')}")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
