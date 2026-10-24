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
            print(f"Dialogs before: {dialogs_before}")

            # Find the reaction counter trigger inside the post dialog
            # Look for the toolbar or reaction count
            target_loc = page.locator('span[role="toolbar"][aria-label*="Xem ai đã bày tỏ cảm xúc"], div[role="button"][aria-label*="Thích:"], div[role="button"][aria-label*="Yêu thích:"]').last
            
            print("Scrolling reaction trigger into view...")
            await target_loc.scroll_into_view_if_needed(timeout=5000)
            await asyncio.sleep(1)

            box = await target_loc.bounding_box()
            print(f"Bounding box after scroll: {box}")

            print("Clicking reaction trigger...")
            await target_loc.click(force=True)
            
            reaction_modal = None
            for _ in range(10):
                await asyncio.sleep(0.5)
                curr = await page.locator('div[role="dialog"]').all()
                if len(curr) > dialogs_before:
                    reaction_modal = curr[-1]
                    break

            if reaction_modal:
                print("SUCCESS: Reaction modal opened!")
                tabs = await reaction_modal.locator('div[role="tab"], [role="tab"]').all()
                print(f"Found {len(tabs)} tabs:")
                for idx, t in enumerate(tabs):
                    aria = await t.get_attribute("aria-label") or ""
                    txt = await t.inner_text() or ""
                    print(f"  Tab {idx}: aria={aria!r}, txt={txt!r}")
            else:
                print("FAILED to open reaction modal!")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
