import asyncio
import logging
from signal import SIGINT, SIGTERM
import os

from livekit import rtc, api


# ensure LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET are set


async def main(room: rtc.Room) -> None:
    @room.on("participant_disconnected")
    def on_participant_disconnect(participant: rtc.Participant, *_):
        logging.info("participant disconnected: %s", participant.identity)

    token = (
        api.AccessToken()
        .with_identity("text-publisher")
        .with_name("text publisher")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room="truongnn-room",
            )
        )
        .to_jwt()
    )
    url = os.getenv("LIVEKIT_URL")

    logging.info("connecting to %s", url)
    try:
        await room.connect(
            url,
            token,
            options=rtc.RoomOptions(
                auto_subscribe=True,
            ),
        )
        logging.info("connected to room %s", room.name)
    except rtc.ConnectError as e:
        logging.error("failed to connect to the room: %s", e)
        return

    while True:
        text = input("Input: ")
        publication = await room.local_participant.send_text(text,
                                                             topic='chat'
                                                             )
        print(publication.stream_id)
    # logging.info("published track %s", publication.sid)

    # asyncio.ensure_future(publish_frames(source, 440))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        handlers=[logging.FileHandler("publish_wave.log"), logging.StreamHandler()],
    )

    loop = asyncio.get_event_loop()
    room = rtc.Room(loop=loop)

    async def cleanup():
        await room.disconnect()
        loop.stop()

    asyncio.ensure_future(main(room))
    # for signal in [SIGINT, SIGTERM]:
    #     loop.add_signal_handler(signal, lambda: asyncio.ensure_future(cleanup()))

    try:
        loop.run_forever()
    finally:
        loop.close()
