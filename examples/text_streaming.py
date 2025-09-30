import os
import logging
import asyncio
from signal import SIGINT, SIGTERM
from livekit import rtc
import json
from typing import Dict, List

# Set the following environment variables with your own values
TOKEN = os.environ.get("LIVEKIT_TOKEN")
URL = os.environ.get("LIVEKIT_URL")


class TextStreamingApp:
    def __init__(self):
        self.room = rtc.Room()
        self.logger = logging.getLogger(__name__)
        self.active_tasks: List[asyncio.Task] = []
        self.connected_participants: Dict[str, rtc.RemoteParticipant] = {}

    async def setup_room_handlers(self):
        """Set up all room event handlers"""

        @self.room.on("participant_connected")
        def on_participant_connected(participant: rtc.RemoteParticipant):
            self.logger.info(f"Participant connected: {participant.identity} ({participant.sid})")
            self.connected_participants[participant.identity] = participant
            # Send welcome message to new participant
            asyncio.create_task(self.send_welcome_message(participant.identity))

        @self.room.on("participant_disconnected")
        def on_participant_disconnected(participant: rtc.RemoteParticipant):
            self.logger.info(f"Participant disconnected: {participant.identity}")
            if participant.identity in self.connected_participants:
                del self.connected_participants[participant.identity]

        # Register text stream handlers for different topics
        self.room.register_text_stream_handler("chat", self._handle_chat_stream)
        self.room.register_text_stream_handler("announcements", self._handle_announcement_stream)
        self.room.register_text_stream_handler("typing", self._handle_typing_stream)
        self.room.register_text_stream_handler("json-data", self._handle_json_stream)

    def _handle_chat_stream(self, reader: rtc.TextStreamReader, participant_identity: str):
        """Handle incoming chat messages"""
        task = asyncio.create_task(self._process_chat_message(reader, participant_identity))
        self.active_tasks.append(task)
        task.add_done_callback(lambda _: self.active_tasks.remove(task))

    def _handle_announcement_stream(self, reader: rtc.TextStreamReader, participant_identity: str):
        """Handle incoming announcements"""
        task = asyncio.create_task(self._process_announcement(reader, participant_identity))
        self.active_tasks.append(task)
        task.add_done_callback(lambda _: self.active_tasks.remove(task))

    def _handle_typing_stream(self, reader: rtc.TextStreamReader, participant_identity: str):
        """Handle typing indicators"""
        task = asyncio.create_task(self._process_typing_indicator(reader, participant_identity))
        self.active_tasks.append(task)
        task.add_done_callback(lambda _: self.active_tasks.remove(task))

    def _handle_json_stream(self, reader: rtc.TextStreamReader, participant_identity: str):
        """Handle structured JSON data streams"""
        task = asyncio.create_task(self._process_json_data(reader, participant_identity))
        self.active_tasks.append(task)
        task.add_done_callback(lambda _: self.active_tasks.remove(task))

    async def _process_chat_message(self, reader: rtc.TextStreamReader, participant_identity: str):
        """Process incoming chat messages"""
        try:
            full_message = await reader.read_all()
            self.logger.info(f"[CHAT] {participant_identity}: {full_message}")

            # Echo the message back to demonstrate bidirectional communication
            await self.send_echo_message(participant_identity, full_message)
        except Exception as e:
            self.logger.error(f"Error processing chat message: {e}")

    async def _process_announcement(self, reader: rtc.TextStreamReader, participant_identity: str):
        """Process incoming announcements"""
        try:
            announcement = await reader.read_all()
            self.logger.info(f"[ANNOUNCEMENT] {participant_identity}: {announcement}")
        except Exception as e:
            self.logger.error(f"Error processing announcement: {e}")

    async def _process_typing_indicator(self, reader: rtc.TextStreamReader, participant_identity: str):
        """Process typing indicators"""
        try:
            typing_status = await reader.read_all()
            self.logger.info(f"[TYPING] {participant_identity} is {typing_status}")
        except Exception as e:
            self.logger.error(f"Error processing typing indicator: {e}")

    async def _process_json_data(self, reader: rtc.TextStreamReader, participant_identity: str):
        """Process structured JSON data"""
        try:
            json_text = await reader.read_all()
            data = json.loads(json_text)
            self.logger.info(f"[JSON DATA] {participant_identity}: {data}")
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON from {participant_identity}: {e}")
        except Exception as e:
            self.logger.error(f"Error processing JSON data: {e}")

    async def send_welcome_message(self, participant_identity: str):
        """Send a welcome message to a new participant"""
        try:
            # Send character-by-character streaming message
            text_writer = await self.room.local_participant.stream_text(
                destination_identities=[participant_identity],
                topic="chat"
            )

            welcome_msg = f"Welcome to the text streaming demo, {participant_identity}!"
            for char in welcome_msg:
                await text_writer.write(char)
                await asyncio.sleep(0.05)  # Small delay for effect

            await text_writer.aclose()

        except Exception as e:
            self.logger.error(f"Error sending welcome message: {e}")

    async def send_echo_message(self, original_sender: str, message: str):
        """Echo a message back to the sender"""
        try:
            text_writer = await self.room.local_participant.stream_text(
                destination_identities=[original_sender],
                topic="chat"
            )

            echo_msg = f"Echo: {message}"
            await text_writer.write(echo_msg)
            await text_writer.aclose()

        except Exception as e:
            self.logger.error(f"Error sending echo message: {e}")

    async def broadcast_announcement(self, announcement: str):
        """Broadcast an announcement to all participants"""
        try:
            if not self.connected_participants:
                self.logger.info("No participants to broadcast to")
                return

            text_writer = await self.room.local_participant.stream_text(
                destination_identities=list(self.connected_participants.keys()),
                topic="announcements"
            )

            await text_writer.write(announcement)
            await text_writer.aclose()

            self.logger.info(f"Broadcasted announcement: {announcement}")

        except Exception as e:
            self.logger.error(f"Error broadcasting announcement: {e}")

    async def send_typing_indicator(self, target_identity: str, is_typing: bool):
        """Send typing indicator to a specific participant"""
        try:
            text_writer = await self.room.local_participant.stream_text(
                destination_identities=[target_identity],
                topic="typing"
            )

            status = "typing..." if is_typing else "stopped typing"
            await text_writer.write(status)
            await text_writer.aclose()

        except Exception as e:
            self.logger.error(f"Error sending typing indicator: {e}")

    async def send_json_data(self, target_identities: List[str], data: dict):
        """Send structured JSON data to participants"""
        try:
            text_writer = await self.room.local_participant.stream_text(
                destination_identities=target_identities,
                topic="json-data"
            )

            json_text = json.dumps(data)
            await text_writer.write(json_text)
            await text_writer.aclose()

            self.logger.info(f"Sent JSON data to {target_identities}: {data}")

        except Exception as e:
            self.logger.error(f"Error sending JSON data: {e}")

    async def connect(self):
        """Connect to the LiveKit room"""
        await self.setup_room_handlers()
        await self.room.connect(URL, TOKEN)
        self.logger.info(f"Connected to room: {self.room.name}")

        # Greet existing participants
        for identity, participant in self.room.remote_participants.items():
            self.connected_participants[identity] = participant
            await self.send_welcome_message(identity)

    async def disconnect(self):
        """Disconnect from the room and cleanup"""
        # Cancel all active tasks
        for task in self.active_tasks:
            task.cancel()

        await self.room.disconnect()
        self.logger.info("Disconnected from room")

    async def run_demo_sequence(self):
        """Run a demonstration sequence of text streaming features"""
        await asyncio.sleep(2)  # Wait a bit after connection

        # Demo 1: Broadcast announcement
        await self.broadcast_announcement("🎉 Text streaming demo starting!")
        await asyncio.sleep(3)

        # Demo 2: Send JSON data to all participants
        demo_data = {
            "type": "demo",
            "message": "This is structured data",
            "timestamp": asyncio.get_event_loop().time(),
            "features": ["real-time", "bidirectional", "multi-topic"]
        }

        if self.connected_participants:
            await self.send_json_data(list(self.connected_participants.keys()), demo_data)

        await asyncio.sleep(3)

        # Demo 3: Simulate typing indicators
        for participant_identity in self.connected_participants.keys():
            await self.send_typing_indicator(participant_identity, True)
            await asyncio.sleep(1)
            await self.send_typing_indicator(participant_identity, False)

        await asyncio.sleep(2)
        await self.broadcast_announcement("Demo sequence completed! Try sending messages!")


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    app = TextStreamingApp()

    async def cleanup():
        await app.disconnect()

    try:
        await app.connect()

        # Run the demo sequence
        demo_task = asyncio.create_task(app.run_demo_sequence())

        # Keep the application running
        await asyncio.Future()  # Run forever

    except KeyboardInterrupt:
        logging.info("Shutting down...")
    finally:
        await cleanup()


if __name__ == "__main__":
    # Check if required environment variables are set
    if not TOKEN or not URL:
        print("ERROR: LIVEKIT_TOKEN and LIVEKIT_URL environment variables are required")
        print("Set them with your LiveKit server credentials:")
        print("  export LIVEKIT_TOKEN='your-token-here'")
        print("  export LIVEKIT_URL='wss://your-livekit-server.com'")
        exit(1)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nApplication terminated by user")
