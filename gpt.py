# ============================================================
#  GPT - AI Conversation (Groq - MIỄN PHÍ)
#  Groq cung cấp Llama 3.1 8B miễn phí, tốc độ rất nhanh
#  Đăng ký: https://console.groq.com
#  Hỗ trợ: Dynamic system prompt cho livestream consultation
# ============================================================

from groq import Groq
import config
from session import get_session, add_message
from livestream_rules import build_livestream_prompt

client = Groq(api_key=config.GROQ_API_KEY)

SYSTEM_PROMPT = """Bạn là nhân viên tư vấn của hệ thống TTVV.

QUY TẮC QUAN TRỌNG:
- Trả lời NGẮN GỌN, tối đa 2-3 câu ngắn
- Nói tự nhiên như người thật qua điện thoại
- KHÔNG dùng markdown, bullet points, emoji
- Hỏi lại nếu chưa hiểu ý khách

THÔNG TIN DỊCH VỤ:
- Tư vấn các gói Livestream cho khách hàng.
- Hỗ trợ kỹ thuật: Thứ 2-6, 8h-18h
- Hotline: 1800-xxxx (miễn phí)

Nếu khách hỏi điều bạn không chắc, hãy đề nghị chuyển sang chuyên viên."""


async def get_ai_response(call_id: str, user_text: str) -> str | None:
    """Gọi Groq Llama 3 → text phản hồi (MIỄN PHÍ)."""
    session = get_session(call_id)
    
    # Ưu tiên lấy key từ Webhook truyền vào (từ CRM Settings), nếu không có thì dùng key mặc định
    dynamic_key = session.get("groq_key")
    if dynamic_key:
        active_client = Groq(api_key=dynamic_key)
    else:
        active_client = client

    try:
        # Ưu tiên system prompt động từ session (livestream consultation mode)
        active_prompt = session.get("system_prompt") or SYSTEM_PROMPT

        response = active_client.chat.completions.create(
            model=config.GPT_MODEL,
            messages=[
                {"role": "system", "content": active_prompt},
                *session["history"],
                {"role": "user", "content": user_text},
            ],
            max_tokens=config.GPT_MAX_TOKENS,
            temperature=0.7,
        )
        reply = response.choices[0].message.content.strip()
        print(f"[LLM] Trả lời: '{reply}'")
        return reply

    except Exception as e:
        print(f"[LLM] Lỗi Groq: {e}")
        session["ai_retry_count"] = session.get("ai_retry_count", 0) + 1
        return None
