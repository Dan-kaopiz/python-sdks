# Voice Agent Integration với LiveKit

Ví dụ này tích hợp một voice agent qua WebSocket với LiveKit để xử lý audio realtime.

## Cách hoạt động

1. **LiveKit Connection**: Kết nối đến LiveKit room để nhận audio từ clients
2. **Voice Agent Integration**: 
   - Gửi audio từ clients đến voice agent (16kHz PCM base64)
   - Nhận response audio từ voice agent (24kHz PCM base64)
   - Chuyển đổi và publish audio response lại cho clients qua LiveKit

## Yêu cầu

```bash
pip install websockets scipy sounddevice python-dotenv
```

## Cấu hình

File `.env` cần chứa:
```
LIVEKIT_URL=wss://your-livekit-server
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret
```

## Chạy ứng dụng

```bash
python play_audio_stream.py
```

## Luồng xử lý Audio

1. **Client → Voice Agent**:
   - Client gửi audio qua LiveKit (48kHz)
   - Script nhận audio và downsample xuống 16kHz
   - Convert thành base64 PCM và gửi đến voice agent qua WebSocket

2. **Voice Agent → Client**:
   - Voice agent trả về audio (24kHz base64 PCM) qua WebSocket
   - Script upsample lên 48kHz
   - Publish audio qua LiveKit để client có thể nghe

## Voice Agent WebSocket Protocol

- **Connect**: `wss://xxxxxxxxxxxxxxx`
- **Ready message**: `{"type": "ready"}`
- **Send audio**: `{"type": "audio", "data": "base64_pcm_16khz"}`
- **Receive audio**: `{"type": "audio", "data": "base64_pcm_24khz"}`

## Testing

1. Mở `mic_publisher.html` trong trình duyệt
2. Kết nối đến cùng LiveKit room
3. Chạy script này
4. Nói vào microphone trên trình duyệt
5. Nghe response từ voice agent
