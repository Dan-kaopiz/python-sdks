import asyncio
import logging
import os

from livekit import api, rtc
logger = logging.getLogger(__name__)

async def text_reader():
    url = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
    api_key = os.getenv("LIVEKIT_API_KEY", "devkey")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "secret")

    token = (
        api.AccessToken(api_key, api_secret)
        .with_identity("app_text_listener")
        .with_name("App Text Listener")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room="text_room",
            )
        )
        .to_jwt()
    )

    room = rtc.Room()

    def on_done(task: asyncio.Task):
        print("Task finished with result:", task.result())

    async def _process_chat_message(reader: rtc.TextStreamReader, participant_identity: str):
        """Process incoming chat messages"""
        try:
            full_message = await reader.read_all()
            logger.info(f"[CHAT] {participant_identity}: {full_message}")
            return full_message

            # Echo the message back to demonstrate bidirectional communication
            # await send_echo_message(participant_identity, full_message)
        except Exception as e:
            logger.error(f"Error processing chat message: {e}")

    def _handle_chat_stream(reader: rtc.TextStreamReader, participant_identity: str):
        """Handle incoming chat messages"""
        print(participant_identity)
        task = asyncio.create_task(_process_chat_message(reader, participant_identity))
        task.add_done_callback(on_done)

    room.register_text_stream_handler("chat", _handle_chat_stream)

    await room.connect(
        url,
        token,
        options=rtc.RoomOptions(
            auto_subscribe=True,
        ),
    )

    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(text_reader())