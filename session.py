# ============================================================
#  Session Manager
#  Lưu context hội thoại theo call_id (in-memory)
# ============================================================

import json
import urllib.request
import urllib.error
import time

sessions: dict = {}


def get_session(call_id: str) -> dict:
    """Lấy hoặc tạo mới session cho một cuộc gọi."""
    if call_id not in sessions:
        sessions[call_id] = {
            "call_id": call_id,
            "history": [],           # GPT message history
            "transcript": [],        # Log toàn bộ hội thoại
            "ai_retry_count": 0,     # Đếm số lần GPT lỗi
            "state": "active",       # active | transferred | ended
            "turn_count": 0,         # Số lượt hội thoại
            "start_time": time.time(), # Thời gian bắt đầu gọi
        }
    return sessions[call_id]


def add_message(call_id: str, role: str, content: str):
    """Thêm tin nhắn vào history và transcript."""
    s = get_session(call_id)
    s["history"].append({"role": role, "content": content})
    s["transcript"].append({"role": role, "text": content})

    # Giữ tối đa 16 messages gần nhất để tránh token quá nhiều
    if len(s["history"]) > 16:
        s["history"] = s["history"][-16:]

    if role == "user":
        s["turn_count"] += 1


def get_history(call_id: str) -> list:
    return get_session(call_id)["history"]


def clear_session(call_id: str):
    """Xoá session sau khi cuộc gọi kết thúc."""
    if call_id in sessions:
        s = sessions[call_id]
        
        transcript_text = ""
        if s["transcript"]:
            print(f"\n📝 TRANSCRIPT [{call_id}]:")
            for t in s["transcript"]:
                prefix = "👤" if t["role"] == "user" else "🤖"
                line = f"{prefix} {t['text']}"
                print(f"  {line}")
                transcript_text += line + "\n"
            print()
            
        log_id = s.get("log_id")
        if log_id:
            try:
                import os
                backend_base_url = os.getenv("BACKEND_URL", "https://starfish-app-5lg32.ondigitalocean.app").rstrip("/")
                url = f"{backend_base_url}/api/ai-consultation/logs/{log_id}"
                # Tính thời lượng cuộc gọi
                duration = int(time.time() - s.get("start_time", time.time()))
                
                # Phân tích kết quả từ transcript
                final_result = s.get("state", "completed")
                if final_result == "active":
                    lower_transcript = transcript_text.lower()
                    # Cải thiện bắt keyword chốt đơn
                    if any(kw in lower_transcript for kw in [
                        "đăng ký gói", "gửi email báo giá", "hướng dẫn cách đăng ký", 
                        "thông tin đăng ký", "đặt hàng", "mua gói", "thanh toán", "chọn gói"
                    ]):
                        final_result = "registered"
                    elif "xin lỗi đã làm phiền" in lower_transcript or "không rảnh" in lower_transcript:
                        final_result = "not_interested"
                    else:
                        final_result = "completed"
                
                recommended_package = "Gói Cơ Bản"
                if "doanh nghiệp" in lower_transcript:
                    recommended_package = "Gói Doanh Nghiệp"
                elif "nâng cao" in lower_transcript:
                    recommended_package = "Gói Nâng Cao"

                data = {
                    "result": final_result,
                    "notes": transcript_text.strip(),
                    "duration": duration,
                    "recommendedPackage": recommended_package
                }
                
                req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), method='PUT')
                req.add_header('Content-Type', 'application/json')
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        print(f"[{call_id}] 💾 Đã lưu lịch sử vào Backend (log_id={log_id})")
            except Exception as e:
                print(f"[{call_id}] ⚠️ Lỗi lưu lịch sử: {e}")

        del sessions[call_id]
