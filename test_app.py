# -*- coding: utf-8 -*-
import time
import requests

BASE_URL = "http://127.0.0.1:8000"

def test_full_workflow():
    print("1. Testing GET / ...")
    res = requests.get(f"{BASE_URL}/")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert "Facebook Contest Scoring & Anti-Spam" in res.text
    print("   -> GET / OK!")

    print("2. Testing GET /api/session-status ...")
    res = requests.get(f"{BASE_URL}/api/session-status")
    assert res.status_code == 200
    data = res.json()
    assert "saved" in data
    print(f"   -> Session Status OK: saved={data['saved']}")

    print("3. Testing POST /api/scan (Demo mode)...")
    scan_res = requests.post(f"{BASE_URL}/api/scan", json={
        "post_url": "https://www.facebook.com/fanpage/posts/1029384756",
        "use_demo": True
    })
    assert scan_res.status_code == 200
    task_id = scan_res.json()["task_id"]
    print(f"   -> Scan Task Started: task_id={task_id}")

    # Wait for background task to complete (demo mode takes ~1.5s)
    max_wait = 10
    start_t = time.time()
    completed = False
    while time.time() - start_t < max_wait:
        st_res = requests.get(f"{BASE_URL}/api/scan-status/{task_id}")
        st_data = st_res.json()
        print(f"   -> Task Status: {st_data['status']} ({st_data['progress']}%) - {st_data['message']}")
        if st_data["status"] == "completed":
            completed = True
            break
        time.sleep(0.5)

    assert completed, "Task did not complete within timeout"

    print("4. Testing GET /api/results/{task_id} ...")
    res_data = requests.get(f"{BASE_URL}/api/results/{task_id}").json()
    score = res_data["score"]
    reactions = res_data["reactions"]
    comments = res_data["comments"]
    shares = res_data["shares"]

    print(f"   -> Contest Score Breakdown:")
    print(f"      - Valid Reactions: {score['valid_reactions']} x 1 = {score['reaction_points']} pts (Total Extracted: {reactions['total_extracted']}, Invalid: {reactions['invalid_count']})")
    print(f"      - Valid Comments: {score['valid_comments']} x 2 = {score['comment_points']} pts (Total Extracted: {comments['total_extracted']}, Invalid: {comments['invalid_count']})")
    print(f"      - FINAL TOTAL SCORE: {score['final_total_score']} points")

    expected_score = (score["valid_reactions"] * 1) + (score["valid_comments"] * 2)
    assert score["final_total_score"] == expected_score, f"Score mismatch: {score['final_total_score']} != {expected_score}"

    print("5. Testing POST /api/override (Manual Admin Override)...")
    # Pick first invalid comment
    assert len(comments["invalid_accounts"]) > 0, "No invalid comments found in test"
    target_invalid = comments["invalid_accounts"][0]
    target_url = target_invalid["clean_profile_url"]
    prev_valid_comments = score["valid_comments"]
    prev_total_score = score["final_total_score"]

    override_res = requests.post(f"{BASE_URL}/api/override", json={
        "task_id": task_id,
        "category": "comments",
        "clean_profile_url": target_url,
        "target_status": True,
        "reason": "Admin test override"
    })
    assert override_res.status_code == 200
    ov_data = override_res.json()
    assert ov_data["status"] == "success"
    new_score = ov_data["score"]
    print(f"   -> Overrode account '{target_invalid['account_name']}' to Valid.")
    print(f"   -> Valid Comments updated: {prev_valid_comments} -> {new_score['valid_comments']}")
    print(f"   -> Final Total Score updated: {prev_total_score} -> {new_score['final_total_score']} (Diff: +2 pts)")
    assert new_score["valid_comments"] == prev_valid_comments + 1
    assert new_score["final_total_score"] == prev_total_score + 2

    print("6. Testing GET /api/export-excel/{task_id} ...")
    excel_res = requests.get(f"{BASE_URL}/api/export-excel/{task_id}")
    assert excel_res.status_code == 200
    assert "spreadsheetml" in excel_res.headers.get("content-type", "")
    assert len(excel_res.content) > 1000
    print(f"   -> Excel Export OK! Received {len(excel_res.content)} bytes.")

    print("\nALL INTEGRATION & ENDPOINT TESTS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    test_full_workflow()
