# ============================================================
#  Rules - Logic xử lý: khi nào transfer, khi nào hangup
# ============================================================

import config
from session import get_session


def should_transfer(user_text: str, call_id: str) -> tuple[bool, str]:
    """
    Kiểm tra có nên chuyển sang nhân viên không.
    Trả về (should_transfer: bool, reason: str)
    """
    session = get_session(call_id)
    text_lower = user_text.lower()

    # Rule 1: Khách nói từ khoá chuyển máy
    for kw in config.TRANSFER_KEYWORDS:
        if kw in text_lower:
            return True, f"keyword: {kw}"

    # Rule 2: GPT lỗi quá nhiều lần
    if session.get("ai_retry_count", 0) >= config.MAX_AI_RETRIES:
        return True, "ai_retry_limit"

    return False, ""


def should_end_call(call_id: str) -> bool:
    """Kiểm tra có nên kết thúc cuộc gọi không (tương lai mở rộng)."""
    session = get_session(call_id)
    text_lower = " ".join(
        t["text"].lower() for t in session.get("transcript", [])[-2:]
    )
    end_keywords = ["thôi được rồi", "cảm ơn tạm biệt", "bye", "tắt máy"]
    return any(kw in text_lower for kw in end_keywords)


# ============================================================
#  Message builders - Tạo JSON message gửi về Tel4vn
# ============================================================

def build_chunk_action(base64_mp3: str) -> dict:
    """Phát audio MP3 cho khách (không chờ, stream ngay)."""
    return {
        "event": "chunk",
        "media": {
            "payload": base64_mp3,
            "format": "mp3"
        }
    }


def build_media_action(base64_wav: str) -> dict:
    """Phát audio WAV và chờ phát xong (is_sync)."""
    return {
        "event": "media",
        "media": {
            "payload": base64_wav,
            "is_sync": True
        }
    }


def build_transfer_action(extension: str = None) -> dict:
    """Chuyển cuộc gọi sang nhân viên."""
    return {
        "event": "transfer",
        "data": {
            "extension": extension or config.AGENT_EXTENSION
        }
    }


def build_hangup_action() -> dict:
    """Cúp máy."""
    return {"event": "hangup"}
