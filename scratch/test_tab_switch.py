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

            triggers = [
                'div[role="button"][aria-label*="người"]:not([aria-label*="bình luận"]):not([aria-label*="chia sẻ"])',
                'div[role="button"][aria-label*="Thích:"]',
                'div[role="button"][aria-label*="Yêu thích:"]',
                'div[role="button"]:has(img[alt="Thích"])',
                'div[role="button"]:has(img[alt="Like"])',
                'div[role="button"]:has(img[alt="Yêu thích"])',
            ]

            reaction_modal = None
            for sel in triggers:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    for i in range(await loc.count()):
                        el = loc.nth(i)
                        try:
                            await el.scroll_into_view_if_needed(timeout=1000)
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
                        except Exception:
                            pass
                        if reaction_modal:
                            break
                if reaction_modal:
                    break

            if not reaction_modal:
                print("Modal not found!")
                return

            print("Modal found!")
            tabs = await reaction_modal.locator('div[role="tab"], [role="tab"]').all()
            print(f"Initial tabs count: {len(tabs)}")

            # Check tabs
            tab_info = []
            for idx, t in enumerate(tabs):
                aria = (await t.get_attribute("aria-label") or "")
                text = (await t.inner_text() or "")
                comb = (aria + " " + text).lower()
                is_love = any(k in comb for k in ["yêu thích", "love", "tim", "heart"])
                is_like = any(k in comb for k in ["thích", "like", "thumbs"]) and not is_love and not any(k in comb for k in ["tất cả", "all"])
                print(f"Tab {idx}: is_love={is_love}, is_like={is_like}, comb={comb.encode('utf-8', errors='replace')}")
                tab_info.append({"idx": idx, "tab": t, "is_love": is_love, "is_like": is_like})

            # 1. Click Love
            love_tabs = [t for t in tab_info if t["is_love"]]
            if love_tabs:
                print("Clicking Love tab...")
                await love_tabs[0]["tab"].click(force=True)
                await asyncio.sleep(2)
                # Count links
                links = await reaction_modal.evaluate("el => el.querySelectorAll('a[role=\"link\"]').length")
                print(f"Links in Love tab: {links}")

            # 2. Click Like using stored tab handle
            like_tabs = [t for t in tab_info if t["is_like"]]
            if like_tabs:
                print("Clicking Like tab with stored handle...")
                try:
                    await like_tabs[0]["tab"].click(force=True)
                    await asyncio.sleep(2)
                    links = await reaction_modal.evaluate("el => el.querySelectorAll('a[role=\"link\"]').length")
                    print(f"Links in Like tab after click: {links}")
                except Exception as e:
                    print(f"FAILED to click stored Like tab: {e}")

                # What if we re-query tabs inside the modal?
                print("Re-querying tabs...")
                fresh_tabs = await reaction_modal.locator('div[role="tab"], [role="tab"]').all()
                print(f"Fresh tabs count: {len(fresh_tabs)}")
                for idx, t in enumerate(fresh_tabs):
                    aria = (await t.get_attribute("aria-label") or "")
                    txt = (await t.inner_text() or "")
                    comb = (aria + " " + txt).lower()
                    print(f"  Fresh Tab {idx}: aria={aria.encode('utf-8', errors='replace')}, txt={txt.encode('utf-8', errors='replace')}")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
