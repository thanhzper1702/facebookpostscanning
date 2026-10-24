"""
Facebook Contest Scoring & Anti-Spam Tool - FastAPI Backend Server
==================================================================
Routes:
- GET /: Main Dashboard Single Page Application
- GET /api/session-status: Check if admin Facebook login session is saved
- POST /api/open-login: Launch visible Chromium browser for Facebook admin login
- POST /api/scan: Start Facebook post scan (Playwright / Graph API / Demo mode)
- GET /api/scan-status/{task_id}: Polling status & progress
- GET /api/scan-stream/{task_id}: Server-Sent Events (SSE) live progress updates
- GET /api/results/{task_id}: Get full results, category stats, and account lists
- POST /api/override: Manually toggle an account between Valid and Invalid
- GET /api/export-excel/{task_id}: Export full audit log and statistics to Excel (.xlsx)
"""

import sys
import os
import io
import uuid
import json
import asyncio
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional

# BẮT BUỘC TRÊN WINDOWS: Ép asyncio dùng ProactorEventLoop để mở được subprocess Chromium
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

try:
    import pandas as pd
except ImportError:
    pd = None
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from scraper import FacebookSessionManager, FacebookScraper, FacebookGraphAPI, generate_demo_contest_data, parse_post_html
from filters import process_category_interactions, calculate_contest_score, clean_profile_url


logger = logging.getLogger("app")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Facebook Post Reaction & Interaction Scanner", version="2.0.0")

# Mount templates and static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# In-memory storage for scan tasks and results
SCANS_DATABASE: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Helper: Chạy Coroutine của Playwright trong ProactorEventLoop riêng trên Windows
# Giúp chống lỗi NotImplementedError 100% kể cả khi chạy bằng uvicorn --reload
# ---------------------------------------------------------------------------
def run_in_proactor_thread(coro_func, *args, **kwargs):
    """Runs an async function inside a dedicated thread with WindowsProactorEventLoopPolicy."""
    def _runner():
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(coro_func(*args, **kwargs))
        except Exception as e:
            logger.error(f"Error in background thread: {e}", exc_info=True)
        finally:
            loop.close()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class ScanRequest(BaseModel):
    post_url: str
    access_token: Optional[str] = None
    use_demo: Optional[bool] = False
    headless: Optional[bool] = False


class OverrideRequest(BaseModel):
    task_id: str
    category: str  # "reactions", "comments", "shares"
    clean_profile_url: str
    target_status: bool  # True for Valid, False for Invalid
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Background Task: Scraping & Processing Engine
# ---------------------------------------------------------------------------
async def run_scan_workflow(task_id: str, req: ScanRequest):
    """
    Executes the scan job, updates progress, filters bots & duplicates,
    and computes the final contest score.
    """
    task = SCANS_DATABASE[task_id]
    task["status"] = "processing"
    task["progress"] = 5
    task["stage"] = "init"
    task["message"] = "Initializing scan workflow..."

    async def progress_callback(stage: str, percent: int, msg: str, counts: Dict[str, Any]):
        task["stage"] = stage
        task["progress"] = percent
        task["message"] = msg
        task["counts"] = counts
        task["logs"].append({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "stage": stage,
            "percent": percent,
            "message": msg
        })

    try:
        raw_data = None

        if req.use_demo:
            await progress_callback("demo", 20, "Generating realistic contest test dataset...", {})
            await asyncio.sleep(1)
            raw_data = generate_demo_contest_data(req.post_url)
            await progress_callback("demo", 60, "Loaded test reactions, comments, and shares.", {})
            await asyncio.sleep(0.5)

        elif req.access_token:
            # Use Facebook Graph API
            await progress_callback("graph_api", 20, "Connecting to Facebook Graph API...", {})
            post_id = FacebookGraphAPI.extract_post_id(req.post_url)
            if not post_id:
                raise ValueError("Could not extract numerical Post ID from URL for Graph API.")
            
            raw_data = FacebookGraphAPI.fetch_via_graph_api(post_id, req.access_token)
            raw_data["post_url"] = req.post_url
            raw_data["status"] = "success"
            await progress_callback("graph_api", 70, "Fetched data via Facebook Graph API.", {})

        elif not req.post_url.startswith("http://") and not req.post_url.startswith("https://") and (
            req.post_url.endswith(".html") or req.post_url.endswith(".htm")
        ):
            file_path = req.post_url
            if not os.path.isabs(file_path):
                file_path = os.path.join(BASE_DIR, file_path)
            
            await progress_callback("parsing_html", 30, f"Phát hiện file HTML ({os.path.basename(file_path)}). Đang bóc tách dữ liệu...", {})
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            raw_data = parse_post_html(content, post_url=req.post_url)
            await progress_callback("parsing_html", 75, "Đã trích xuất số liệu và danh sách tương tác từ file HTML.", {
                "reactions": raw_data.get("reactions_total", 0),
                "comments": len(raw_data.get("comments", [])),
                "shares": raw_data.get("shares_total", 0)
            })

        else:
            # Playwright Automated Scraper
            scraper = FacebookScraper(headless=req.headless)
            raw_data = await scraper.scrape_post(req.post_url, progress_cb=progress_callback)

        await progress_callback("filtering", 85, "Applying Anti-Spam & Bot Name Filtering rules...", {})

        # Process each category independently
        reactions_processed = process_category_interactions(
            raw_data.get("reactions", []),
            "Like/Love Reaction",
            is_comment=False
        )

        comments_processed = process_category_interactions(
            raw_data.get("comments", []),
            "Comment",
            is_comment=True
        )

        shares_processed = process_category_interactions(
            raw_data.get("shares", []),
            "Public Share"
        )

        # Calculate Final Contest Score
        valid_reactions = reactions_processed["valid_count"]
        if valid_reactions == 0 and raw_data.get("reactions_total", 0) > 0:
            breakdown = raw_data.get("reactions_breakdown", {})
            # Ưu tiên các reaction tích cực: Thích + Yêu thích
            valid_reactions = (breakdown.get("Thích", 0) + breakdown.get("Yêu thích", 0)) or raw_data.get("reactions_total", 0)

        valid_comments = comments_processed["valid_count"]

        score_data = calculate_contest_score(
            valid_reactions=valid_reactions,
            valid_comments=valid_comments,
            valid_shares=0
        )

        task["status"] = "completed"
        task["progress"] = 100
        task["message"] = "Analysis completed successfully!"
        task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task["results"] = {
            "post_url": req.post_url,
            "post_title": raw_data.get("post_title", ""),
            "reactions_total": (
                raw_data.get("reactions_total", 0)
                or sum(raw_data.get("reactions_breakdown", {}).values())
                or reactions_processed["total_extracted"]
            ),
            "reactions_breakdown": raw_data.get("reactions_breakdown", {}),
            "comments_total": raw_data.get("comments_total", 0),
            "shares_total": raw_data.get("shares_total", 0),
            "score": score_data,
            "reactions": reactions_processed,
            "comments": comments_processed,
            "shares": shares_processed
        }

    except Exception as e:
        logger.error(f"Error in scan workflow for task {task_id}: {e}", exc_info=True)
        task["status"] = "failed"
        task["progress"] = 100
        task["error"] = str(e)
        task["message"] = f"Scan failed: {str(e)}"
        task["logs"].append({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "stage": "error",
            "percent": 100,
            "message": str(e)
        })


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """Renders the main dashboard page."""
    session_saved = FacebookSessionManager.is_session_saved()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"session_saved": session_saved}
    )


@app.get("/api/session-status")
async def get_session_status():
    """Returns whether Facebook admin session cookies/state exist."""
    saved = FacebookSessionManager.is_session_saved()
    return {
        "saved": saved,
        "session_dir": os.path.abspath("fb_session")
    }


@app.post("/api/open-login")
async def open_admin_login():
    """
    Launches visible Playwright Chromium browser inside a dedicated Proactor thread
    so the admin can authenticate and store session cookies in fb_session.
    """
    run_in_proactor_thread(FacebookSessionManager.launch_login_browser)
    return {
        "status": "browser_launched",
        "message": "Browser window launched. Please log in to Facebook and solve any 2FA/prompts. When finished, you may close the window or keep it open."
    }


@app.post("/api/scan")
async def start_scan(req: ScanRequest):
    """Initiates an asynchronous scan job for a Facebook Post URL."""
    if not req.post_url and not req.use_demo:
        raise HTTPException(status_code=400, detail="Facebook Post URL is required.")

    task_id = str(uuid.uuid4())
    SCANS_DATABASE[task_id] = {
        "task_id": task_id,
        "post_url": req.post_url or "https://www.facebook.com/demo_contest_post",
        "status": "pending",
        "progress": 0,
        "stage": "queued",
        "message": "Task queued for processing...",
        "counts": {"reactions": 0, "comments": 0, "shares": 0},
        "logs": [],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": None
    }

    run_in_proactor_thread(run_scan_workflow, task_id, req)

    return {
        "task_id": task_id,
        "status": "queued",
        "message": "Scan job has been queued."
    }


@app.get("/api/scan-status/{task_id}")
async def get_scan_status(task_id: str):
    """Polls status and live progress for a scan job."""
    if task_id not in SCANS_DATABASE:
        raise HTTPException(status_code=404, detail="Task ID not found.")
    
    task = SCANS_DATABASE[task_id]
    return {
        "task_id": task_id,
        "status": task["status"],
        "progress": task["progress"],
        "stage": task["stage"],
        "message": task["message"],
        "counts": task.get("counts", {}),
        "logs": task.get("logs", [])[-10:],  # last 10 logs
        "has_results": task["status"] == "completed"
    }


@app.get("/api/scan-stream/{task_id}")
async def stream_scan_progress(task_id: str):
    """Server-Sent Events (SSE) endpoint for real-time progress streaming."""
    if task_id not in SCANS_DATABASE:
        raise HTTPException(status_code=404, detail="Task ID not found.")

    async def event_generator():
        while True:
            if task_id not in SCANS_DATABASE:
                break
            task = SCANS_DATABASE[task_id]
            data = json.dumps({
                "status": task["status"],
                "progress": task["progress"],
                "stage": task["stage"],
                "message": task["message"],
                "counts": task.get("counts", {}),
                "error": task.get("error")
            })
            yield f"data: {data}\n\n"

            if task["status"] in ["completed", "failed"]:
                break
            await asyncio.sleep(0.8)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/results/{task_id}")
async def get_scan_results(task_id: str):
    """Returns the finalized statistics, scoring breakdown, and accounts."""
    if task_id not in SCANS_DATABASE:
        raise HTTPException(status_code=404, detail="Task ID not found.")
    
    task = SCANS_DATABASE[task_id]
    if task["status"] != "completed" or not task.get("results"):
        return JSONResponse(
            status_code=202,
            content={"status": task["status"], "progress": task["progress"], "message": task["message"]}
        )

    return task["results"]


@app.post("/api/override")
async def override_account_status(req: OverrideRequest):
    """
    Manually overrides an account's classification (Valid <-> Invalid).
    Instantly recalculates the category counts and Final Contest Score in real time.
    """
    if req.task_id not in SCANS_DATABASE:
        raise HTTPException(status_code=404, detail="Task ID not found.")

    task = SCANS_DATABASE[req.task_id]
    if task.get("status") != "completed" or not task.get("results"):
        raise HTTPException(status_code=400, detail="Cannot override an incomplete task.")

    cat_key = req.category.lower()
    if cat_key not in ["reactions", "comments", "shares"]:
        raise HTTPException(status_code=400, detail="Invalid category. Must be 'reactions', 'comments', or 'shares'.")

    category_data = task["results"][cat_key]
    valid_accs = category_data["valid_accounts"]
    invalid_accs = category_data["invalid_accounts"]

    target_acc = None

    if req.target_status is True:
        # Move from INVALID -> VALID
        found_idx = None
        for i, acc in enumerate(invalid_accs):
            if acc["clean_profile_url"] == req.clean_profile_url:
                found_idx = i
                target_acc = acc
                break
        
        if found_idx is not None and target_acc:
            invalid_accs.pop(found_idx)
            target_acc["is_valid"] = True
            target_acc["reason"] = req.reason or "Admin Manual Override: Verified Valid"
            valid_accs.append(target_acc)
            
            # Recount: 1 valid account added
            category_data["valid_count"] += 1
            if category_data["invalid_count"] > 0:
                category_data["invalid_count"] -= 1

    else:
        # Move from VALID -> INVALID
        found_idx = None
        for i, acc in enumerate(valid_accs):
            if acc["clean_profile_url"] == req.clean_profile_url:
                found_idx = i
                target_acc = acc
                break

        if found_idx is not None and target_acc:
            valid_accs.pop(found_idx)
            target_acc["is_valid"] = False
            target_acc["reason"] = req.reason or "Admin Manual Override: Marked as Invalid/Bot"
            invalid_accs.append(target_acc)

            # Recount: 1 valid account removed
            if category_data["valid_count"] > 0:
                category_data["valid_count"] -= 1
            category_data["invalid_count"] += 1

    # Recalculate Final Contest Score
    new_score = calculate_contest_score(
        valid_reactions=task["results"]["reactions"]["valid_count"],
        valid_comments=task["results"]["comments"]["valid_count"],
        valid_shares=task["results"]["shares"]["valid_count"]
    )
    task["results"]["score"] = new_score

    return {
        "status": "success",
        "message": f"Account '{target_acc.get('account_name', '')}' updated to {'Valid' if req.target_status else 'Invalid'}.",
        "updated_category": {
            "valid_count": category_data["valid_count"],
            "invalid_count": category_data["invalid_count"]
        },
        "score": new_score
    }


@app.get("/api/export-excel/{task_id}")
async def export_excel_report(task_id: str):
    """
    Exports a comprehensive audit report to Excel (.xlsx) with styled sheets:
    1. Summary & Score Breakdown
    2. Valid Reactions (Like+Love)
    3. Invalid Reactions
    4. Valid Comments
    5. Invalid Comments
    6. Valid Shares
    7. Invalid Shares
    """
    if task_id not in SCANS_DATABASE:
        raise HTTPException(status_code=404, detail="Task ID not found.")

    task = SCANS_DATABASE[task_id]
    if task.get("status") != "completed" or not task.get("results"):
        raise HTTPException(status_code=400, detail="Scan results not ready for export.")

    res = task["results"]
    score = res["score"]

    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Styles
    title_font = Font(name="Arial", size=14, bold=True, color="1E293B")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Arial", size=10)
    
    header_fill_blue = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid") # Dark Blue
    header_fill_green = PatternFill(start_color="15803D", end_color="15803D", fill_type="solid") # Emerald Green
    header_fill_red = PatternFill(start_color="B91C1C", end_color="B91C1C", fill_type="solid") # Red

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # -------------------------------------------------------------
    # Sheet 1: Summary Statistics (Thống kê tương tác)
    # -------------------------------------------------------------
    ws_sum = wb.create_sheet(title="TongQuan_ThongKe")
    ws_sum.views.sheetView[0].showGridLines = True

    ws_sum.append(["BÁO CÁO THỐNG KÊ TƯƠNG TÁC BÀI VIẾT FACEBOOK"])
    ws_sum["A1"].font = title_font
    ws_sum.append([])

    ws_sum.append(["Thời gian xuất báo cáo:", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    ws_sum.append(["Link bài viết Facebook:", res.get("post_url", "")])
    ws_sum.append(["Tiêu đề bài viết:", res.get("post_title", "") or "Không có"])
    ws_sum.append([])

    # Table Header
    sum_headers = ["Hạng mục tương tác", "Tổng quét được", "Hợp lệ", "Vi phạm / Loại trừ", "Tỷ lệ hợp lệ"]
    ws_sum.append(sum_headers)
    for col_idx in range(1, len(sum_headers) + 1):
        cell = ws_sum.cell(row=6, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill_blue
        cell.alignment = Alignment(horizontal="center", vertical="center")

    rx_total = res["reactions"]["total_extracted"]
    rx_valid = res["reactions"]["valid_count"]
    rx_invalid = res["reactions"]["invalid_count"]
    rx_rate = f"{(rx_valid / rx_total * 100):.1f}%" if rx_total > 0 else "0.0%"

    cm_total = res["comments"]["total_extracted"]
    cm_valid = res["comments"]["valid_count"]
    cm_invalid = res["comments"]["invalid_count"]
    cm_rate = f"{(cm_valid / cm_total * 100):.1f}%" if cm_total > 0 else "0.0%"

    sum_rows = [
        ["Cảm xúc (Like 👍 + Love ❤️)", rx_total, rx_valid, rx_invalid, rx_rate],
        ["Bình luận (Comments 💬)", cm_total, cm_valid, cm_invalid, cm_rate],
    ]

    for r in sum_rows:
        ws_sum.append(r)

    # Total Row
    total_valid = rx_valid + cm_valid
    total_all = rx_total + cm_total
    total_invalid = rx_invalid + cm_invalid
    total_rate = f"{(total_valid / total_all * 100):.1f}%" if total_all > 0 else "0.0%"

    ws_sum.append(["TỔNG TƯƠNG TÁC HỢP LỆ", total_all, total_valid, total_invalid, total_rate])
    total_row_idx = 9
    for c in range(1, 6):
        cell = ws_sum.cell(row=total_row_idx, column=c)
        cell.font = Font(name="Arial", size=12, bold=True, color="047857")
        cell.fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
        cell.alignment = Alignment(horizontal="center" if c == 1 or c == 5 else "right")
        cell.border = thin_border

    # Format data cells
    for r in range(7, 9):
        for c in range(1, 6):
            cell = ws_sum.cell(row=r, column=c)
            cell.font = data_font
            cell.border = thin_border
            if c >= 2 and c <= 4:
                cell.alignment = Alignment(horizontal="right")
            elif c == 5:
                cell.alignment = Alignment(horizontal="center")

    # -------------------------------------------------------------
    # Helper to add Account List sheets
    # -------------------------------------------------------------
    def add_account_sheet(sheet_title: str, headers: list, accounts: list, is_valid: bool, has_comments: bool = False):
        ws = wb.create_sheet(title=sheet_title)
        ws.views.sheetView[0].showGridLines = True
        ws.append(headers)

        header_fill = header_fill_green if is_valid else header_fill_red
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for idx, acc in enumerate(accounts, start=1):
            row_data = [idx, acc.get("account_name", ""), acc.get("profile_url", "")]
            if has_comments:
                row_data.append(acc.get("interaction_count", 1))
            if not is_valid:
                row_data.append(acc.get("reason", "Vi phạm quy tắc lọc"))

            ws.append(row_data)

            # Apply borders and styling
            curr_row = idx + 1
            for c in range(1, len(row_data) + 1):
                cell = ws.cell(row=curr_row, column=c)
                cell.font = data_font
                cell.border = thin_border
                if c == 1 or (has_comments and c == 4):
                    cell.alignment = Alignment(horizontal="center")

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or "")
                max_len = max(max_len, len(val_str))
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 60)

    # Add sheets for each category (Reactions & Comments)
    add_account_sheet("HopLe_Reactions", ["STT", "Tên tài khoản", "Link Facebook cá nhân"], res["reactions"]["valid_accounts"], is_valid=True)
    add_account_sheet("ViPham_Reactions", ["STT", "Tên tài khoản", "Link Facebook cá nhân", "Lý do loại trừ"], res["reactions"]["invalid_accounts"], is_valid=False)
    add_account_sheet("HopLe_BinhLuan", ["STT", "Tên tài khoản", "Link Facebook cá nhân", "Số bình luận đăng"], res["comments"]["valid_accounts"], is_valid=True, has_comments=True)
    add_account_sheet("ViPham_BinhLuan", ["STT", "Tên tài khoản", "Link Facebook cá nhân", "Số bình luận đăng", "Lý do loại trừ"], res["comments"]["invalid_accounts"], is_valid=False, has_comments=True)

    # Auto-adjust column widths for summary sheet
    for col in ws_sum.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            max_len = max(max_len, len(val_str))
        ws_sum.column_dimensions[col_letter].width = min(max(max_len + 3, 14), 60)

    # Save to memory stream
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"Facebook_Interaction_Report_{task_id[:8]}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == "__main__":
    import uvicorn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    port = int(os.environ.get("PORT", 8000))
    # Trên Windows ưu tiên 127.0.0.1 để click link terminal mở trình duyệt không bị lỗi ERR_ADDRESS_INVALID
    host = "127.0.0.1" if sys.platform == "win32" and "PORT" not in os.environ else "0.0.0.0"
    uvicorn.run("app:app", host=host, port=port, reload=False)