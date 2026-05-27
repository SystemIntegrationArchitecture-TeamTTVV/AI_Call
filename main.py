# ============================================================
#  MAIN - WebSocket Server (Twilio Media Streams + Test Mode)
# ============================================================

import asyncio
import json
import time
import traceback
import websockets

import config
from session import get_session, add_message, clear_session
from stt import add_mulaw_chunk, add_pcm_chunk, transcribe, clear_buffer
from gpt import get_ai_response
from tts import text_to_mulaw_base64, text_to_mp3_base64
from rules import should_transfer
from livestream_rules import build_livestream_prompt

_last_audio_time: dict[str, float] = {}
_processing: dict[str, bool] = {}


def _twilio_media(stream_sid: str, mulaw_b64: str) -> str:
    return json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": mulaw_b64}})


def _twilio_clear(stream_sid: str) -> str:
    return json.dumps({"event": "clear", "streamSid": stream_sid})


# ── Xử lý 1 lượt hội thoại ──────────────────────────────────
async def process_turn(ws, call_id: str, stream_sid: str, is_test: bool):
    if _processing.get(call_id):
        return
    _processing[call_id] = True
    session = get_session(call_id)

    try:
        user_text = transcribe(call_id)
        if not user_text:
            return

        add_message(call_id, "user", user_text)
        need_transfer, reason = should_transfer(user_text, call_id)

        if need_transfer:
            print(f"[{call_id}] 🔀 Transfer ({reason})")
            session["state"] = "transferred"
            notice = await text_to_mp3_base64("Tôi sẽ kết nối bạn với nhân viên tư vấn ngay.")
            if notice:
                await ws.send(json.dumps({"event": "chunk", "media": {"payload": notice, "format": "mp3"}}))
            return

        ai_reply = await get_ai_response(call_id, user_text)
        if not ai_reply:
            return

        is_end = False
        lower_reply = ai_reply.lower()
        if "[kết_thúc]" in lower_reply or "tạm biệt" in lower_reply or "xin lỗi đã làm phiền" in lower_reply:
            is_end = True
            ai_reply = ai_reply.replace("[KẾT_THÚC]", "").replace("[kết_thúc]", "").strip()

        add_message(call_id, "assistant", ai_reply)

        if is_test:
            mp3 = await text_to_mp3_base64(ai_reply)
            if mp3:
                await ws.send(json.dumps({"event": "chunk", "media": {"payload": mp3, "format": "mp3"}}))
                print(f"[{call_id}] 🔊 Đã phát audio (test)")
        else:
            mulaw = await text_to_mulaw_base64(ai_reply)
            if mulaw and stream_sid:
                await ws.send(_twilio_clear(stream_sid))
                await ws.send(_twilio_media(stream_sid, mulaw))
                print(f"[{call_id}] 🔊 Đã phát audio (Twilio)")
                if is_end:
                    await ws.send(json.dumps({
                        "event": "mark",
                        "streamSid": stream_sid,
                        "mark": {"name": "end_call"}
                    }))
                    print(f"[{call_id}] 🔖 Đã gửi mark end_call")

    except Exception as e:
        print(f"[{call_id}] ❌ Lỗi process_turn:")
        traceback.print_exc()
    finally:
        _processing[call_id] = False


# ── Silence detector ─────────────────────────────────────────
async def silence_watcher(ws, call_id: str, stream_sid_ref: list, is_test: bool):
    session = get_session(call_id)
    while session["state"] == "active":
        await asyncio.sleep(0.3)
        last_t = _last_audio_time.get(call_id)
        if last_t is None:
            continue
        elapsed = time.time() - last_t
        if elapsed >= config.SILENCE_SECONDS and not _processing.get(call_id):
            _last_audio_time[call_id] = time.time() + 9999
            await process_turn(ws, call_id, stream_sid_ref[0], is_test)


# ── Handler chính ────────────────────────────────────────────
async def handle_call(ws):
    import urllib.parse
    path = getattr(ws.request, "path", "") if hasattr(ws, "request") else getattr(ws, "path", "")
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
    is_test = "call_id" in qs
    call_id = qs.get("call_id", [""])[0] or f"twilio-{int(time.time())}"
    groq_key = qs.get("groq_key", [""])[0]

    print(f"\n{'='*55}")
    print(f"📞 Kết nối | call_id={call_id} | {'TEST' if is_test else 'TWILIO'}")
    print(f"{'='*55}")

    session = get_session(call_id)
    if groq_key:
        session["groq_key"] = groq_key

    # ── Livestream Consultation Mode ──────────────────────────
    consultation_mode = qs.get("mode", ["livestream"])[0]
    if consultation_mode == "livestream":
        import urllib.parse as _up
        packages_text = _up.unquote(qs.get("packages", [""])[0])
        extra_instructions = _up.unquote(qs.get("instructions", [""])[0])
        session["system_prompt"] = build_livestream_prompt(packages_text, extra_instructions)
        session["consultation_mode"] = "livestream"
        print(f"[{call_id}] 📦 Livestream consultation mode")

    stream_sid_ref = [""]
    _last_audio_time[call_id] = time.time() + 9999
    _processing[call_id] = False

    watcher = asyncio.create_task(silence_watcher(ws, call_id, stream_sid_ref, is_test))

    try:
        async for raw in ws:
            # Parse JSON
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event = msg.get("event")

            # Wrap mọi handler để server không crash
            try:

                # ── test_text: bypass STT (không cần ffmpeg) ─────────────────────
                if event == "test_text":
                    user_text = msg.get("text", "").strip()
                    if not user_text:
                        continue

                    print(f"[{call_id}] 📝 Text inject: '{user_text}'")
                    add_message(call_id, "user", user_text)

                    ai_reply = await get_ai_response(call_id, user_text)
                    if not ai_reply:
                        await ws.send(json.dumps({"event": "error", "message": "LLM không trả lời"}))
                        continue

                    add_message(call_id, "assistant", ai_reply)
                    mp3 = await text_to_mp3_base64(ai_reply)

                    if mp3:
                        await ws.send(json.dumps({"event": "chunk", "media": {"payload": mp3, "format": "mp3"}}))
                        print(f"[{call_id}] 🔊 Đã gửi MP3 reply")
                    else:
                        # TTS lỗi → gửi text thuần để test client không bị treo
                        await ws.send(json.dumps({"event": "text_reply", "text": ai_reply}))
                        print(f"[{call_id}] 💬 TTS lỗi → gửi text: {ai_reply}")

                # ── connected ────────────────────────────────────────────────────
                elif event == "connected":
                    print(f"[{call_id}] ✅ Connected")

                    # Tuỳ chế độ tư vấn → thay đổi lời chào
                    if session.get("consultation_mode") == "livestream":
                        greeting = "Xin chào! Tôi là AI tư vấn dịch vụ livestream của hệ thống TTVV. Bạn có thể dành một chút thời gian để nghe tư vấn được không ạ?"
                    else:
                        greeting = "Xin chào! Tôi là AI tư vấn của hệ thống TTVV. Bạn có thể dành một chút thời gian được không ạ?"

                    if is_test:
                        mp3 = await text_to_mp3_base64(greeting)
                        if mp3:
                            await ws.send(json.dumps({"event": "chunk", "media": {"payload": mp3, "format": "mp3"}}))
                            print(f"[{call_id}] 🎙️ Lời chào đã gửi (MP3)")
                        else:
                            # gTTS lỗi → gửi text để client không bị treo
                            await ws.send(json.dumps({"event": "chunk", "media": {"payload": "", "format": "mp3"}}))
                            print(f"[{call_id}] 💬 gTTS lỗi → gửi empty chunk")

                # ── start (Twilio) ────────────────────────────────────────────────
                elif event == "start":
                    sid = msg.get("streamSid", "")
                    stream_sid_ref[0] = sid
                    
                    start_data = msg.get("start", {})
                    custom_params = start_data.get("customParameters", {})
                    log_id = custom_params.get("logId")
                    if log_id:
                        session["log_id"] = log_id
                        print(f"[{call_id}] 📎 Gắn log_id: {log_id}")
                        
                    print(f"[{call_id}] 🚀 Twilio stream: sid={sid}")
                    mulaw = await text_to_mulaw_base64(
                        "Xin chào! Tôi là AI tư vấn dịch vụ livestream của hệ thống TTVV. Bạn có thể dành một chút thời gian để nghe tư vấn được không ạ?"
                    )
                    if mulaw and sid:
                        await ws.send(_twilio_media(sid, mulaw))
                        print(f"[{call_id}] 🎙️ Lời chào đã gửi (Twilio)")

                # ── media: nhận audio ─────────────────────────────────────────────
                elif event == "media":
                    payload = msg.get("media", {}).get("payload", "")
                    if payload:
                        import base64
                        import audioop
                        try:
                            raw_bytes = base64.b64decode(payload)
                            
                            # 1. Thêm vào buffer (WAV cho STT)
                            if is_test:
                                pcm_bytes = raw_bytes
                                add_pcm_chunk(call_id, payload)
                            else:
                                pcm_bytes = audioop.ulaw2lin(raw_bytes, 2)
                                add_mulaw_chunk(call_id, payload)
                                
                            # 2. Đo âm lượng (RMS) để phát hiện im lặng (VAD)
                            rms = audioop.rms(pcm_bytes, 2)
                            
                            # Ngưỡng 300~500 là phù hợp để lọc tiếng xì xèo của mic
                            if rms > 400:
                                _last_audio_time[call_id] = time.time()
                                
                        except Exception as decode_err:
                            pass

                # ── stop / closed ─────────────────────────────────────────────────
                elif event in ("stop", "closed"):
                    print(f"[{call_id}] 🔚 Kết thúc (event: {event})")
                    break
                    
                # ── mark ──────────────────────────────────────────────────────────
                elif event == "mark":
                    mark_name = msg.get("mark", {}).get("name")
                    if mark_name == "end_call":
                        print(f"[{call_id}] 🔚 Đã phát xong audio cuối, ngắt kết nối!")
                        await ws.close()
                        break

            except Exception:
                print(f"[{call_id}] ❌ Lỗi xử lý event='{event}':")
                traceback.print_exc()
                # Không crash → tiếp tục lặng nghe

    except websockets.exceptions.ConnectionClosed as e:
        print(f"[{call_id}] 🔌 Closed: code={e.code}")
    except Exception:
        print(f"[{call_id}] ❌ Lỗi không xử lý:")
        traceback.print_exc()
    finally:
        watcher.cancel()
        clear_buffer(call_id)
        clear_session(call_id)
        _last_audio_time.pop(call_id, None)
        _processing.pop(call_id, None)
        print(f"[{call_id}] 🧹 Cleaned up\n")


# ── Khởi động ────────────────────────────────────────────────
async def main():
    print("=" * 55)
    print("  🤖 AI VoiceBot - Twilio Edition")
    print(f"  📡 ws://{config.WS_HOST}:{config.WS_PORT}")
    print("  Stack: Google STT + Groq Llama3 (free) + gTTS")
    print("=" * 55)
    print()
    async with websockets.serve(handle_call, config.WS_HOST, config.WS_PORT):
        print(f"✅ Server: ws://localhost:{config.WS_PORT}")
        print("   ngrok: ngrok http 8765")
        print()
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
