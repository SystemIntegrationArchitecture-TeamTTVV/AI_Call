# ============================================================
#  TEST CLIENT v2 - Giả lập PSR/Twilio gửi text vào WebSocket
#  KHÔNG cần ffmpeg! Dùng "text inject" để test pipeline AI
#
#  Cách dùng:
#    python test_client.py
#    python test_client.py --text "Tôi muốn hỏi về gói dịch vụ"
#    python test_client.py --chat  (chế độ chat nhiều lượt)
# ============================================================

import asyncio
import base64
import json
import time
import argparse

import websockets

WS_URL = "ws://localhost:8765/ws"
CALL_ID = f"test-call-{int(time.time())}"


async def run_test(text: str = None, chat_mode: bool = False):
    url = f"{WS_URL}?call_id={CALL_ID}&tenant=test"
    print(f"\n{'='*55}")
    print(f"  🧪 TEST CLIENT v2")
    print(f"  📡 {url}")
    print(f"  Mode: {'💬 Chat nhiều lượt' if chat_mode else '🎤 Single turn'}")
    print(f"{'='*55}\n")

    try:
        async with websockets.connect(url) as ws:
            print("✅ Đã kết nối!\n")

            # ── Bước 1: Gửi connected → nhận lời chào ──────
            await ws.send(json.dumps({"event": "connected"}))
            print("📤 Gửi: event=connected")

            greeting = await asyncio.wait_for(ws.recv(), timeout=15.0)
            g = json.loads(greeting)
            print(f"📥 Lời chào từ AI: event={g.get('event')}")
            if g.get("event") == "chunk":
                mp3_b64 = g.get("media", {}).get("payload", "")
                _save_mp3(mp3_b64, "greeting")
            print()

            # ── Bước 2: Test hội thoại ───────────────────────
            if chat_mode:
                await _chat_loop(ws)
            else:
                question = text or "Tôi muốn hỏi về gói CRM của công ty"
                await _single_turn(ws, question, turn=1)

            # ── Kết thúc ─────────────────────────────────────
            await ws.send(json.dumps({"event": "closed"}))
            print("\n🔚 Đã gửi closed")

    except ConnectionRefusedError:
        print("❌ Không kết nối được! Chắc chắn python main.py đang chạy không?")
    except asyncio.TimeoutError:
        print("❌ Timeout! Server không phản hồi trong 15 giây")
    except Exception as e:
        print(f"❌ Lỗi: {e}")

    print(f"\n{'='*55}")
    print("  🏁 Test hoàn tất")
    print(f"  📂 Xem file MP3 tạo ra: test_output_*.mp3")
    print(f"{'='*55}\n")


async def _single_turn(ws, question: str, turn: int = 1):
    """Gửi 1 câu hỏi → nhận câu trả lời MP3."""
    print(f"🎤 Câu hỏi: '{question}'")

    # Dùng text_inject — bypass STT hoàn toàn, không cần ffmpeg!
    await ws.send(json.dumps({
        "event": "test_text",
        "text": question
    }))
    print("📤 Gửi: event=test_text (bypass STT)")
    print("⏳ Chờ AI phản hồi (Groq + gTTS)...")

    try:
        reply = await asyncio.wait_for(ws.recv(), timeout=30.0)
        msg = json.loads(reply)
        event = msg.get("event")

        if event == "chunk":
            mp3_b64 = msg.get("media", {}).get("payload", "")
            if mp3_b64:
                fname = _save_mp3(mp3_b64, f"reply_{turn}")
                print(f"✅ AI đã trả lời! Mở {fname} để nghe.")
            else:
                print("⚠️  AI trả lời nhưng TTS lỗi (payload rỗng)")

        elif event == "text_reply":
            # TTS lỗi → nhận text thuần
            text = msg.get("text", "")
            print(f"✅ AI trả lời (text): '{text}'")

        elif event == "transfer":
            print(f"🔀 AI chuyển máy → Extension {msg.get('data', {}).get('extension', '?')}")

        elif event == "error":
            print(f"❌ Server báo lỗi: {msg.get('message')}")

        else:
            print(f"⚠️  Event lạ: {event} | {msg}")

    except asyncio.TimeoutError:
        print("❌ Timeout 30s — kiểm tra GROQ_API_KEY trong .env")



async def _chat_loop(ws):
    """Chế độ chat nhiều lượt — gõ câu hỏi liên tục."""
    print("💬 Chế độ CHAT — Gõ câu hỏi, Enter để gửi, 'quit' để thoát\n")
    turn = 1
    while True:
        try:
            question = input(f"  Bạn [{turn}]: ").strip()
        except EOFError:
            break

        if question.lower() in ("quit", "exit", "thoát", "q"):
            break
        if not question:
            continue

        await _single_turn(ws, question, turn)
        print()
        turn += 1


def _save_mp3(mp3_b64: str, label: str) -> str:
    """Decode base64 MP3 và lưu file. Trả về tên file."""
    if not mp3_b64:
        return "(empty)"
    try:
        mp3_bytes = base64.b64decode(mp3_b64)
        fname = f"test_output_{label}.mp3"
        with open(fname, "wb") as f:
            f.write(mp3_bytes)
        print(f"   💾 Đã lưu: {fname} ({len(mp3_bytes):,} bytes)")
        return fname
    except Exception as e:
        print(f"   ⚠️  Không lưu được MP3: {e}")
        return "(error)"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test AI VoiceBot")
    parser.add_argument("--text", type=str, help="Câu hỏi test (single turn)")
    parser.add_argument("--chat", action="store_true", help="Chế độ chat nhiều lượt")
    args = parser.parse_args()

    asyncio.run(run_test(text=args.text, chat_mode=args.chat))
