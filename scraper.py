"""
Facebook Contest Scoring & Anti-Spam Tool - Automation & Scraping Engine
========================================================================
- Xử lý triệt để bất đồng bộ (async/await), khắc phục lỗi coroutine has no len().
- Khử cơ chế phân mảnh văn bản và ký tự ẩn (zero-width spaces) của Facebook.
- Lọc bỏ các khối mồi nhử (honeypot blockquote) và phần tử giao diện hệ thống.
- Tích hợp Bộ lọc Đa tầng 5 Lớp: Phân tích Tên (khử lặp chữ GenZ, viết tắt) + 
  Quét ngược URL Slug + Phát hiện ID Clone mới tạo (615...) + Tín hiệu Bạn chung.
"""

import os
import re
import json
import asyncio
import logging
import urllib.parse
from typing import Dict, List, Any, Optional, Callable, Set, Tuple

logger = logging.getLogger("fb_scraper")
logging.basicConfig(level=logging.INFO)

FB_SESSION_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "fb_session"))
os.makedirs(FB_SESSION_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Danh sách lọc từ khóa giao diện, thời gian và nút hành động
# ---------------------------------------------------------------------------
UI_BLOCKLIST_SUBSTRINGS = [
    "facebook", "online", "chỉ báo trạng thái", "trạng thái online", "active now",
    "đang hoạt động", "hoạt động", "ngày", "giờ", "phút", "giây", "tuần", "tháng",
    "năm", "vừa xong", "hôm qua", "hôm nay", "just now", "yesterday", "bạn chung",
    "mutual friend", "nhắn tin", "thêm bạn bè", "bỏ theo dõi", "theo dõi", "message",
    "send message", "add friend", "phản hồi", "thích", "lượt thích", "chia sẻ",
    "lượt chia sẻ", "bình luận", "xem thêm", "like", "love", "reply", "share",
    "trường thpt", "quảng bá", "quảng cáo", "giphy", "xem ai đã", "bày tỏ cảm xúc",
    "thương thương", "haha", "wow", "buồn", "phẫn nộ", "whatsapp", "messenger",
    "sao chép liên kết", "gửi bằng messenger"
]

NON_USER_SLUGS = {
    "posts", "watch", "groups", "events", "photo.php", "photos",
    "hashtag", "browse", "messages", "share", "sharer.php", "login",
    "recover", "help", "settings", "policies", "privacy", "pages",
    "reel", "stories", "permalink.php", "story.php", "live", "about",
    "ad_center", "photo", "l.php", "sharer"
}

# ---------------------------------------------------------------------------
# Hệ thống Nhận diện Tài khoản Việt Nam vs. Acc Clone/Bot (từ filters.py)
# ---------------------------------------------------------------------------
from filters import verify_vietnamese_account


def clean_extracted_name(raw_text: str) -> Optional[str]:
    """
    Khử các ký tự tàng hình (zero-width, combining grapheme joiner)
    và ghép nối các token tên bị Facebook bẻ dòng/phân mảnh.
    """
    if not raw_text:
        return None

    cleaned = re.sub(r"[\u200B-\u200D\uFEFF\u00AD\u2060\u180E\u034F]", "", raw_text)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    valid_tokens = []
    for line in lines:
        if not line:
            continue
        lower = line.lower()
        if any(b in lower for b in UI_BLOCKLIST_SUBSTRINGS):
            continue
        valid_tokens.append(line)

    if not valid_tokens:
        return None

    full_name = " ".join(valid_tokens)
    full_name = re.sub(r"\s+", " ", full_name).strip()

    if len(full_name) <= 1:
        return None
    if re.match(r"^[\d\s\W_]+$", full_name, re.UNICODE):
        return None
    if any(b in full_name.lower() for b in UI_BLOCKLIST_SUBSTRINGS):
        return None

    return full_name


def clean_profile_url(raw_url: str) -> str:
    """Chuẩn hóa liên kết trang cá nhân Facebook."""
    if not raw_url:
        return ""

    raw_url = raw_url.strip()
    if raw_url.startswith("/"):
        raw_url = f"https://www.facebook.com{raw_url}"
    elif not raw_url.startswith("http"):
        raw_url = f"https://www.facebook.com/{raw_url}"

    raw_url = re.sub(
        r"^https?://(m|touch|web|mbasic)\.facebook\.com",
        "https://www.facebook.com",
        raw_url,
        flags=re.IGNORECASE,
    )

    try:
        parsed = urllib.parse.urlparse(raw_url)
        path = parsed.path.rstrip("/")
        query = urllib.parse.parse_qs(parsed.query)

        if "profile.php" in path:
            uid = query.get("id", [""])[0]
            return f"https://www.facebook.com/profile.php?id={uid}" if uid else ""

        if "/people/" in path:
            return f"https://www.facebook.com{re.sub(r'/+$', '', path)}"

        slug = path.lstrip("/").split("/")[0].lower() if path.lstrip("/") else ""
        if not slug or slug in NON_USER_SLUGS:
            return ""

        return f"https://www.facebook.com/{slug}"
    except Exception:
        return ""


def structure_category_users(items: List[Dict[str, Any]], is_comment: bool = False) -> List[Dict[str, Any]]:
    """Gom nhóm tương tác theo tài khoản duy nhất và truyền đủ URL + Social Proof."""
    grouped: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for item in items:
        clean_url = clean_profile_url(item.get("profile_url", ""))
        clean_name = clean_extracted_name(item.get("account_name", ""))

        if not clean_url or not clean_name:
            continue

        count = int(item.get("interaction_count", 1))
        has_social_proof = bool(item.get("has_social_proof", False))

        if clean_url not in grouped:
            if is_comment:
                # Bình luận: Không lọc theo tên tiếng Việt, chỉ ghi nhận người dùng
                is_valid = True
                reason = "Bình luận hợp lệ"
            else:
                # Cảm xúc (Reactions): Truyền đủ clean_name, clean_url, has_social_proof sang bộ lọc VN
                is_valid, reason = verify_vietnamese_account(
                    clean_name,
                    profile_url=clean_url,
                    has_social_proof=has_social_proof,
                )
            grouped[clean_url] = {
                "account_name": clean_name,
                "profile_url": clean_url,
                "count": 0,
                "is_valid": is_valid,
                "reason": reason or "Hợp lệ",
                "has_social_proof": has_social_proof,
            }
            order.append(clean_url)
        else:
            if has_social_proof:
                grouped[clean_url]["has_social_proof"] = True

        grouped[clean_url]["count"] += count

    return [
        {
            "account_name": grouped[u]["account_name"],
            "profile_url": grouped[u]["profile_url"],
            "interaction_count": grouped[u]["count"],
            "is_valid": grouped[u]["is_valid"],
            "reason": grouped[u]["reason"],
            "has_social_proof": grouped[u]["has_social_proof"],
        }
        for u in order
    ]


# ---------------------------------------------------------------------------
# Quản lý phiên đăng nhập (Admin Session)
# ---------------------------------------------------------------------------
class FacebookSessionManager:
    @staticmethod
    def is_session_saved() -> bool:
        return os.path.exists(FB_SESSION_DIR) and len(os.listdir(FB_SESSION_DIR)) > 0

    @staticmethod
    async def launch_login_browser():
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            effective_headless = False
            if sys.platform != "win32" and not os.environ.get("DISPLAY"):
                effective_headless = True

            context = await p.chromium.launch_persistent_context(
                user_data_dir=FB_SESSION_DIR,
                headless=effective_headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-notifications",
                ],
                no_viewport=True,
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://www.facebook.com", wait_until="domcontentloaded")
            try:
                while len(context.pages) > 0 and not page.is_closed():
                    await asyncio.sleep(1)
            except Exception:
                pass
            finally:
                await context.close()


def extract_role_count(html_content: str, role: str) -> int:
    """Bóc tách chính xác số lượng từ khối nút có role tương ứng."""
    idx = html_content.find(f'data-ad-rendering-role="{role}"')
    if idx != -1:
        snippet = html_content[idx:idx + 3500]
        m = re.search(r'dir="auto">\s*([\d,\.]+)\s*</span>', snippet)
        if m:
            val = re.sub(r'[^\d]', '', m.group(1))
            if val:
                return int(val)
    return 0


def parse_post_html(html_content: str, post_url: str = "") -> Dict[str, Any]:
    """
    Bóc tách trực tiếp và toàn diện dữ liệu từ mã nguồn HTML của bài viết Facebook.
    """
    title_match = re.search(r'<h2[^>]*>(.*?)</h2>', html_content, re.DOTALL)
    post_title = ""
    if title_match:
        post_title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
        post_title = re.sub(r'\s+', ' ', post_title)

    reactions_count = extract_role_count(html_content, "like_button")
    comments_count = extract_role_count(html_content, "comment_button")
    shares_count = extract_role_count(html_content, "share_button")

    if shares_count == 0:
        share_m = re.search(r'aria-label="[^"]*Chia sẻ[^"]*"[^>]*>.*?dir="auto">\s*([\d,\.]+)\s*</span>', html_content, re.DOTALL)
        if not share_m:
            share_m = re.search(r'aria-label="[^"]*Chia sẻ[^"]*"[^>]*>\s*([\d,\.]+)\s*<', html_content)
        if share_m:
            try:
                shares_count = int(re.sub(r'[^\d]', '', share_m.group(1)))
            except Exception:
                pass

    breakdown: Dict[str, int] = {}
    breakdowns_matches = re.findall(r'aria-label="([^"]+?:\s*[\d,\.]+\s*người)"', html_content)
    for b in breakdowns_matches:
        parts = b.split(':')
        if len(parts) == 2:
            r_type = parts[0].strip()
            r_num = int(re.sub(r'[^\d]', '', parts[1]))
            breakdown[r_type] = r_num

    raw_comments: List[Dict[str, Any]] = []
    articles = list(re.finditer(r'<div[^>]*?role="article"[^>]*?>', html_content))
    for m in articles:
        tag = m.group(0)
        aria_m = re.search(r'aria-label="([^"]+)"', tag)
        aria_label = aria_m.group(1) if aria_m else ""

        name = None
        name_m = re.search(r'(?:Bình luận dưới tên|Comment by)\s+(.+?)(?:\s+vào\s+|\s+\d+\s+|$)', aria_label)
        if name_m:
            name = clean_extracted_name(name_m.group(1).strip())

        snippet = html_content[m.start():m.start() + 25000]
        links = re.findall(r'<a\s+[^>]*?href="([^"]+)"[^>]*?>(.*?)</a>', snippet, re.DOTALL)
        profile_url = ""
        for href, inner in links:
            if 'permalink.php' in href:
                continue
            cleaned = clean_profile_url(href)
            if cleaned:
                profile_url = cleaned
                if not name:
                    clean_inner = re.sub(r'<[^>]+>', ' ', inner)
                    name = clean_extracted_name(clean_inner)
                break

        if name and profile_url:
            raw_comments.append({
                "account_name": name,
                "profile_url": profile_url,
                "interaction_type": "Comment"
            })

    comments_structured = structure_category_users(raw_comments, is_comment=True)

    return {
        "post_url": post_url or "Local HTML File",
        "post_title": post_title,
        "reactions": [],
        "reactions_total": reactions_count or sum(breakdown.values()),
        "reactions_breakdown": breakdown,
        "comments": comments_structured,
        "comments_total": comments_count or len(comments_structured),
        "shares": [],
        "shares_total": shares_count,
        "status": "success",
    }


# ---------------------------------------------------------------------------
# Trình tự động hóa Playwright Scraper
# ---------------------------------------------------------------------------
class FacebookScraper:
    def __init__(self, session_dir: str = FB_SESSION_DIR, headless: bool = False):
        self.session_dir = session_dir
        self.headless = headless

    async def scrape_post(
        self,
        post_url: str,
        progress_cb: Optional[Callable[[str, int, str, Dict[str, Any]], Any]] = None,
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {
            "reactions": [],
            "comments": [],
            "shares": [],
            "post_url": post_url,
            "status": "in_progress",
        }

        async def report(stage: str, percent: int, msg: str):
            logger.info(f"[{percent}%] {stage}: {msg}")
            if progress_cb:
                r_len = len(results["reactions"]) if isinstance(results.get("reactions"), list) else 0
                c_len = len(results["comments"]) if isinstance(results.get("comments"), list) else 0
                s_len = len(results["shares"]) if isinstance(results.get("shares"), list) else 0

                res = progress_cb(
                    stage,
                    percent,
                    msg,
                    {"reactions": r_len, "comments": c_len, "shares": s_len},
                )
                if asyncio.iscoroutine(res):
                    await res

        if not post_url.startswith("http://") and not post_url.startswith("https://"):
            local_path = post_url
            if not os.path.isabs(local_path):
                local_path = os.path.abspath(os.path.join(os.path.dirname(__file__), post_url))

            if os.path.exists(local_path) and (local_path.endswith(".html") or local_path.endswith(".htm")):
                await report("parsing_html", 30, f"Phát hiện file HTML ({os.path.basename(local_path)}). Đang bóc tách...")
                try:
                    with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    data = parse_post_html(content, post_url=post_url)
                    await report("complete", 100, f"Đã đọc file HTML: {len(data['comments'])} bình luận, {data['reactions_total']} cảm xúc, {data['shares_total']} chia sẻ!")
                    return data
                except Exception as e:
                    logger.error(f"Lỗi đọc file HTML: {e}", exc_info=True)
                    await report("error", 100, f"Lỗi đọc file HTML: {e}")
                    return {"reactions": [], "comments": [], "shares": [], "status": "error", "post_url": post_url}

        from playwright.async_api import async_playwright

        await report("init", 5, "Khởi động trình duyệt Playwright...")

        effective_headless = self.headless
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            effective_headless = True

        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.session_dir,
                headless=effective_headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-notifications",
                ],
                viewport={"width": 1280, "height": 900},
            )
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                await report("navigating", 15, "Đang mở URL bài viết Facebook...")
                await page.goto(post_url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(2)

                try:
                    dom_metrics = await page.evaluate("""() => {
                        let shares = 0;
                        const shareBtn = document.querySelector('div[role="button"][aria-label*="Chia sẻ"], div[role="button"][aria-label*="chia sẻ"]');
                        if (shareBtn) {
                            const num = parseInt((shareBtn.innerText || '').replace(/\\D/g, ''));
                            if (!isNaN(num) && num > 0) shares = num;
                        }
                        return { shares };
                    }""")
                    page_html = await page.content()
                    overview = parse_post_html(page_html, post_url=post_url)
                    results["post_title"] = overview.get("post_title", "")
                    results["reactions_total"] = overview.get("reactions_total", 0)
                    results["reactions_breakdown"] = overview.get("reactions_breakdown", {})
                    results["comments_total"] = overview.get("comments_total", 0)
                    results["shares_total"] = dom_metrics.get("shares") or overview.get("shares_total", 0)
                except Exception as ex:
                    logger.warning(f"Lỗi đọc thông số tổng quan: {ex}")

                # 1. QUÉT CẢM XÚC (REACTIONS: CẢ LIKE & LOVE)
                await report("reactions", 25, "Đang mở hộp thoại Cảm xúc (Like & Love)...")
                results["reactions"] = await self._extract_reactions(
                    page,
                    report,
                    overview_breakdown=results.get("reactions_breakdown", {}),
                    overview_total=results.get("reactions_total", 0),
                )

                # 2. QUÉT BÌNH LUẬN (COMMENTS)
                await report("comments", 65, "Đang cuộn tải toàn bộ danh sách Bình luận...")
                results["comments"] = await self._extract_comments(page, report)

                results["shares"] = []
                results["shares_total"] = 0

                await report("complete", 100, "Thu thập và phân tích dữ liệu bài viết hoàn tất!")
                results["status"] = "success"

            except Exception as e:
                logger.error(f"Lỗi trong quá trình cào: {e}", exc_info=True)
                await report("error", 100, f"Thất bại: {str(e)}")
                results["status"] = "error"
            finally:
                await context.close()

        return results

    async def _find_reaction_or_content_modal(self, page):
        """Tìm chính xác modal bảng cảm xúc hoặc chia sẻ (bỏ qua popup chat ngầm)."""
        dialogs = await page.locator('div[role="dialog"]').all()
        if not dialogs:
            return None
        for d in reversed(dialogs):
            try:
                chat_check = await d.evaluate("""el => {
                    const text = (el.innerText || '').toLowerCase();
                    return text.includes('thiếu lịch sử chat') || text.includes('nhập mã pin') || text.includes('đoạn chat');
                }""")
                if chat_check:
                    continue
                return d
            except Exception:
                continue
        return dialogs[-1] if dialogs else None

    async def extract_users_from_modal(
        self,
        modal_el,
        page,
        interaction_type: str = "Unknown",
        report_fn: Optional[Callable[[int, int], Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Trích xuất đầy đủ danh sách tài khoản trong modal kèm tín hiệu Bạn chung (Social Proof).
        """
        raw_users: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()
        stagnant = 0
        prev_len = 0

        if page:
            try:
                box = await modal_el.bounding_box()
                if box:
                    await page.mouse.move(box['x'] + box['width'] / 2, box['y'] + min(box['height'] / 2, 350))
            except Exception:
                pass

        max_steps = 35
        for step in range(max_steps):
            # Trích xuất toàn bộ thẻ link trong modal kèm kiểm tra "bạn chung"
            batch = await modal_el.evaluate("""el => {
                const links = Array.from(el.querySelectorAll('a[role="link"]'));
                const res = [];
                for (const a of links) {
                    if (a.closest('blockquote')) continue;
                    const href = a.getAttribute('href') || '';
                    const text = a.innerText || '';
                    if (href && text && !href.includes('permalink.php')) {
                        const row = a.closest('div[data-visualcompletion="ignore-dynamic"], li') || a.parentElement?.parentElement;
                        const rowText = (row ? row.innerText : '').toLowerCase();
                        const hasSocialProof = rowText.includes('bạn chung') || rowText.includes('mutual friend');
                        res.push({ href, text, hasSocialProof });
                    }
                }
                return res;
            }""")

            for item in batch:
                clean_url = clean_profile_url(item["href"])
                clean_name = clean_extracted_name(item["text"])
                if clean_url and clean_name and clean_url not in seen_urls:
                    seen_urls.add(clean_url)
                    raw_users.append(
                        {
                            "account_name": clean_name,
                            "profile_url": clean_url,
                            "interaction_type": interaction_type,
                            "has_social_proof": bool(item.get("hasSocialProof", False)),
                        }
                    )
            curr_len = len(raw_users)
            if report_fn:
                try:
                    res_r = report_fn(curr_len, curr_len)
                    if asyncio.iscoroutine(res_r):
                        await res_r
                except Exception:
                    pass

            if curr_len == prev_len:
                stagnant += 1
                if stagnant >= 5:
                    break
                await modal_el.evaluate("""el => {
                    const scrollable = Array.from(el.querySelectorAll('div')).find(d => {
                        const s = window.getComputedStyle(d);
                        return (s.overflowY === 'auto' || s.overflowY === 'scroll') && d.scrollHeight > d.clientHeight;
                    }) || el;
                    scrollable.scrollTop = Math.max(0, scrollable.scrollTop - 250);
                }""")
                await asyncio.sleep(0.3)
            else:
                stagnant = 0

            prev_len = curr_len

            await modal_el.evaluate("""el => {
                const scrollable = Array.from(el.querySelectorAll('div')).find(d => {
                    const s = window.getComputedStyle(d);
                    return (s.overflowY === 'auto' || s.overflowY === 'scroll') && d.scrollHeight > d.clientHeight;
                }) || el;
                scrollable.scrollTop = scrollable.scrollHeight;
                scrollable.dispatchEvent(new Event('scroll', { bubbles: true }));
            }""")
            if page:
                try:
                    await page.mouse.wheel(0, 800)
                except Exception:
                    pass

            await asyncio.sleep(0.65)

        return raw_users

    async def _extract_comments(self, page, report) -> List[Dict[str, Any]]:
        raw_comments: List[Dict[str, Any]] = []

        try:
            sort_clicked = await page.evaluate("""() => {
                const container = document.querySelector('div[role="dialog"]') || document.querySelector('div[role="main"]') || document.body;
                const buttons = Array.from(container.querySelectorAll('div[role="button"], span'));
                for (const b of buttons) {
                    const t = (b.innerText || '').trim();
                    if (t.length < 50 && (t === 'Phù hợp nhất' || t === 'Most relevant' || t.includes('Phù hợp nhất') || t.includes('Most relevant'))) {
                        b.click();
                        return t;
                    }
                }
                return null;
            }""")
            if sort_clicked:
                await asyncio.sleep(1.0)
                await page.evaluate("""() => {
                    const items = document.querySelectorAll('div[role="menuitem"], div[role="option"], span, div[role="button"]');
                    for (const it of items) {
                        const t = (it.innerText || '').trim();
                        if (t.length < 50 && (t === 'Tất cả bình luận' || t === 'All comments' || t.includes('Tất cả bình luận') || t.includes('All comments'))) {
                            it.click();
                            return t;
                        }
                    }
                    return null;
                }""")
                await asyncio.sleep(1.5)
        except Exception as ex:
            logger.warning(f"Lỗi khi chọn Tất cả bình luận: {ex}")

        prev_count = 0
        stagnant_count = 0
        max_steps = 35

        for step in range(max_steps):
            clicked = await page.evaluate("""() => {
                const container = document.querySelector('div[role="dialog"]') || document.querySelector('div[role="main"]') || document.body;
                const all = Array.from(container.querySelectorAll('div[role="button"], span[role="button"], span'));
                const matches = all.filter(el => {
                    const t = (el.innerText || '').trim();
                    if (t.length === 0 || t.length > 60) return false;
                    const tl = t.toLowerCase();
                    return (
                        tl.includes('xem thêm bình luận') ||
                        tl.includes('xem các bình luận') ||
                        tl.includes('bình luận trước') ||
                        tl.includes('bình luận cũ hơn') ||
                        tl.includes('câu trả lời') ||
                        tl.includes('phản hồi') ||
                        tl.includes('view more comments') ||
                        tl.includes('view previous comments')
                    );
                });

                if (matches.length > 0) {
                    matches.sort((a, b) => a.innerText.trim().length - b.innerText.trim().length);
                    const target = matches[0];
                    target.scrollIntoView({ block: 'center', behavior: 'instant' });
                    target.click();
                    return target.innerText.trim();
                }
                return null;
            }""")

            await page.evaluate("""() => {
                const container = document.querySelector('div[role="dialog"]') || document.querySelector('div[role="main"]') || document.body;
                let scrollable = null;
                const divs = [container, ...Array.from(container.querySelectorAll('div'))];
                for (const d of divs) {
                    const s = window.getComputedStyle(d);
                    if ((s.overflowY === 'auto' || s.overflowY === 'scroll') && d.scrollHeight > d.clientHeight + 50) {
                        scrollable = d;
                        break;
                    }
                }
                if (scrollable) {
                    scrollable.scrollTop += 800;
                    scrollable.dispatchEvent(new Event('scroll', { bubbles: true }));
                }
                window.scrollBy(0, 800);
            }""")

            try:
                await page.mouse.move(640, 500)
                await page.mouse.wheel(0, 800)
            except Exception:
                pass

            await asyncio.sleep(0.9)

            curr_count = await page.evaluate("() => document.querySelectorAll('div[role=\"article\"]').length")
            if curr_count > 0 and report:
                try:
                    pct = min(84, 60 + int((step / max_steps) * 24))
                    res_r = report("comments", pct, f"Đang cuộn nạp bình luận ({curr_count} bình luận đã tải)...")
                    if asyncio.iscoroutine(res_r):
                        await res_r
                except Exception:
                    pass

            if curr_count == prev_count and not clicked:
                stagnant_count += 1
                if stagnant_count >= 5:
                    break
            else:
                stagnant_count = 0
            prev_count = curr_count

        articles_data = await page.evaluate("""() => {
            const articles = Array.from(document.querySelectorAll('div[role="article"]'));
            return articles.map(art => {
                const ariaLabel = art.getAttribute('aria-label') || '';
                const links = Array.from(art.querySelectorAll('a[role="link"]')).map(l => ({
                    href: l.getAttribute('href') || '',
                    text: l.innerText || '',
                    inBlockquote: !!l.closest('blockquote')
                }));
                return { ariaLabel, links };
            });
        }""")

        for art in articles_data:
            try:
                aria_label = art["ariaLabel"]
                name = None
                m_vi = re.search(r'(?:Bình luận dưới tên|Comment by)\s+(.+?)(?:\s+vào\s+|\s+\d+\s+|$)', aria_label)
                if m_vi:
                    name = clean_extracted_name(m_vi.group(1))

                clean_url = ""
                for link in art["links"]:
                    if link["inBlockquote"]:
                        continue
                    url = clean_profile_url(link["href"])
                    if url and "permalink.php" not in url:
                        clean_url = url
                        if not name:
                            name = clean_extracted_name(link["text"])
                        break

                if name and clean_url:
                    raw_comments.append(
                        {
                            "account_name": name,
                            "profile_url": clean_url,
                            "interaction_type": "Comment",
                        }
                    )
            except Exception:
                continue

        logger.info(f"Đã trích xuất {len(raw_comments)} bình luận từ bài viết.")
        return structure_category_users(raw_comments, is_comment=True)

    async def _extract_reactions(
        self,
        page,
        report,
        overview_breakdown: Optional[Dict[str, int]] = None,
        overview_total: int = 0,
    ) -> List[Dict[str, Any]]:
        raw_reactions: List[Dict[str, Any]] = []

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
                    except Exception:
                        pass
                    if reaction_modal:
                        break
            if reaction_modal:
                break

        modal = reaction_modal
        if modal:
            await report("reactions", 22, "Đã mở bảng cảm xúc. Đang phân tích tab Yêu thích (Love) và Thích (Like)...")

            tabs = await modal.locator('div[role="tab"], [role="tab"]').all()
            logger.info(f"Tìm thấy {len(tabs)} tabs trong modal reactions.")

            tab_info = []
            for idx, t in enumerate(tabs):
                try:
                    aria = (await t.get_attribute("aria-label") or "")
                    text = (await t.inner_text() or "")
                    comb = (aria + " " + text).lower()
                    is_love = any(k in comb for k in ["yêu thích", "love", "tim", "heart"])
                    is_like = any(k in comb for k in ["thích", "like", "thumbs"]) and not is_love and not any(k in comb for k in ["tất cả", "all"])
                    is_all = any(k in comb for k in ["tất cả", "all"])
                    tab_info.append({
                        "index": idx,
                        "tab": t,
                        "aria": aria,
                        "text": text,
                        "is_love": is_love,
                        "is_like": is_like,
                        "is_all": is_all,
                    })
                except Exception:
                    pass

            # 1. QUÉT TAB YÊU THÍCH (LOVE) TRƯỚC
            love_tabs = [t for t in tab_info if t["is_love"]]
            if love_tabs:
                await report("reactions", 25, "Đang quét danh sách Yêu thích (Love)...")
                try:
                    await modal.evaluate("""el => {
                        const scrollable = Array.from(el.querySelectorAll('div')).find(d => {
                            const s = window.getComputedStyle(d);
                            return (s.overflowY === 'auto' || s.overflowY === 'scroll') && d.scrollHeight > d.clientHeight;
                        }) || el;
                        scrollable.scrollTop = 0;
                    }""")
                    await asyncio.sleep(0.3)
                    await love_tabs[0]["tab"].click(force=True)
                    await asyncio.sleep(0.8)
                    users_love = await self.extract_users_from_modal(modal, page, "Love Reaction")
                    raw_reactions.extend(users_love)
                    logger.info(f"Đã trích xuất {len(users_love)} người bày tỏ Yêu thích (Love).")
                except Exception as ex:
                    logger.warning(f"Lỗi khi đọc tab Love: {ex}")

            # 2. QUÉT TAB THÍCH (LIKE) TIẾP THEO
            try:
                await modal.evaluate("""el => {
                    const scrollable = Array.from(el.querySelectorAll('div')).find(d => {
                        const s = window.getComputedStyle(d);
                        return (s.overflowY === 'auto' || s.overflowY === 'scroll') && d.scrollHeight > d.clientHeight;
                    }) || el;
                    scrollable.scrollTop = 0;
                }""")
                await asyncio.sleep(0.4)

                fresh_tabs = await modal.locator('div[role="tab"], [role="tab"]').all()
                like_tab_target = None
                for t in fresh_tabs:
                    aria = (await t.get_attribute("aria-label") or "")
                    text = (await t.inner_text() or "")
                    comb = (aria + " " + text).lower()
                    if any(k in comb for k in ["thích", "like", "thumbs"]) and not any(k in comb for k in ["yêu thích", "love", "tất cả", "all"]):
                        like_tab_target = t
                        break

                if like_tab_target:
                    await report("reactions", 42, "Đang quét danh sách Thích (Like)...")
                    await like_tab_target.click(force=True)
                    await asyncio.sleep(0.8)
                    users_like = await self.extract_users_from_modal(modal, page, "Like Reaction")
                    raw_reactions.extend(users_like)
                    logger.info(f"Đã trích xuất {len(users_like)} người bày tỏ Thích (Like).")
                else:
                    like_tabs = [t for t in tab_info if t["is_like"]]
                    if like_tabs:
                        await report("reactions", 42, "Đang quét danh sách Thích (Like) bằng tab ban đầu...")
                        await like_tabs[0]["tab"].click(force=True)
                        await asyncio.sleep(0.8)
                        users_like = await self.extract_users_from_modal(modal, page, "Like Reaction")
                        raw_reactions.extend(users_like)
                        logger.info(f"Đã trích xuất {len(users_like)} người bày tỏ Thích (Like).")
            except Exception as ex:
                logger.warning(f"Lỗi khi đọc tab Like: {ex}")

            # 3. FALLBACK
            if not raw_reactions:
                await report("reactions", 35, "Đang đọc toàn bộ danh sách cảm xúc...")
                users_fallback = await self.extract_users_from_modal(modal, page, "Reaction")
                raw_reactions.extend(users_fallback)

            try:
                close_btn = modal.locator('div[aria-label="Đóng"], div[aria-label="Close"], [aria-label="Đóng"]').first
                if await close_btn.is_visible(timeout=800):
                    await close_btn.click(force=True)
                else:
                    await page.keyboard.press("Escape")
            except Exception:
                pass
            await asyncio.sleep(0.5)

        return structure_category_users(raw_reactions)

    async def _extract_shares(self, page, report) -> List[Dict[str, Any]]:
        return []


# ---------------------------------------------------------------------------
# Fallback Graph API & Mock Generator
# ---------------------------------------------------------------------------
class FacebookGraphAPI:
    @staticmethod
    def extract_post_id(post_url: str) -> Optional[str]:
        m = (
            re.search(r"/posts/(\d+)", post_url)
            or re.search(r"story_fbid=(\d+)", post_url)
            or re.search(r"fbid=(\d+)", post_url)
        )
        return m.group(1) if m else None

    @staticmethod
    def fetch_via_graph_api(post_id: str, access_token: str) -> Dict[str, Any]:
        return {"reactions": [], "comments": [], "shares": []}


def generate_demo_contest_data(post_url: str = "") -> Dict[str, Any]:
    return {
        "post_url": post_url or "https://www.facebook.com/demo_contest_post",
        "post_title": "🌟 BÀI VIẾT FACEBOOK MẪU - PHÂN TÍCH TƯƠNG TÁC THỰC TẾ",
        "reactions_total": 45,
        "reactions_breakdown": {"Thích": 25, "Yêu thích": 20},
        "comments_total": 15,
        "shares_total": 8,
        "reactions": [
            {"account_name": "Nguyễn Hoàng Nam", "profile_url": "https://www.facebook.com/nam.nguyen123", "interaction_type": "Love Reaction"},
            {"account_name": "Trần Thị Mai Phương", "profile_url": "https://www.facebook.com/phuong.tran456", "interaction_type": "Love Reaction"},
            {"account_name": "Binn Binn", "profile_url": "https://www.facebook.com/nm.thong1329", "interaction_type": "Love Reaction"},
            {"account_name": "Thanhh Haa", "profile_url": "https://www.facebook.com/mess.hat.9", "interaction_type": "Like Reaction"},
            {"account_name": "ThGia Han", "profile_url": "https://www.facebook.com/thghan24", "interaction_type": "Like Reaction"},
            {"account_name": "Quocss Lee", "profile_url": "https://www.facebook.com/quocss.lee", "interaction_type": "Like Reaction"},
            {"account_name": "Bi Em", "profile_url": "https://www.facebook.com/profile.php?id=61580684836111", "interaction_type": "Like Reaction"},
            {"account_name": "이채원", "profile_url": "https://www.facebook.com/kon0.miyori", "interaction_type": "Like Reaction"},
        ],
        "comments": [
            {"account_name": "Nguyễn Hoàng Nam", "profile_url": "https://www.facebook.com/nam.nguyen123", "interaction_type": "Comment"},
            {"account_name": "Trần Thị Mai Phương", "profile_url": "https://www.facebook.com/phuong.tran456", "interaction_type": "Comment"},
            {"account_name": "Ali Nguyen", "profile_url": "https://www.facebook.com/ali.nguyen.99", "interaction_type": "Comment"},
            {"account_name": "Priya Patel", "profile_url": "https://www.facebook.com/priya.patel222", "interaction_type": "Comment"},
        ],
        "shares": [],
        "status": "success",
    }