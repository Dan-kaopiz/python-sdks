import asyncio
import os
from typing import List

import numpy as np
import sounddevice as sd
import logging
import websockets
import json
import base64
import scipy.signal

from livekit import rtc, api
from livekit.api import LiveKitAPI
from livekit.plugins import noise_cancellation
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

SAMPLERATE = 48000
BLOCKSIZE = 480  # 10ms chunks at 48kHz
CHANNELS = 1

# Voice agent settings
VOICE_AGENT_URL = "ws://localhost:8001/api/v2/ws/Minh"
VOICE_AGENT_INPUT_RATE = 16000  # 16kHz for sending to voice agent
VOICE_AGENT_OUTPUT_RATE = 24000  # 24kHz for receiving from voice agent


class AudioBuffer:
    def __init__(self, blocksize=BLOCKSIZE):
        self.blocksize = blocksize
        self.buffer = np.array([], dtype=np.int16)

    def add_frame(self, frame_data):
        self.buffer = np.concatenate([self.buffer, frame_data])

    def get_chunk(self):
        if len(self.buffer) >= self.blocksize:
            chunk = self.buffer[: self.blocksize]
            self.buffer = self.buffer[self.blocksize :]
            return chunk
        return None

    def get_padded_chunk(self):
        if len(self.buffer) > 0:
            chunk = np.zeros(self.blocksize, dtype=np.int16)
            available = min(len(self.buffer), self.blocksize)
            chunk[:available] = self.buffer[:available]
            self.buffer = self.buffer[available:]
            return chunk
        return np.zeros(self.blocksize, dtype=np.int16)


class VoiceAgentClient:
    def __init__(self, url, output_queue):
        self.url = url
        self.websocket = None
        self.output_queue = output_queue
        self.connected = False
        
    async def connect(self):
        """Connect to voice agent WebSocket"""
        try:
            logger.info(f"🤖 Connecting to voice agent: {self.url}")
            self.websocket = await websockets.connect(self.url)
            
            # Wait for ready message
            logger.info("🤖 Waiting for ready message...")
            message = await self.websocket.recv()
            data = json.loads(message)
            
            if data.get("type") == "ready":
                logger.info("🤖 ✅ Voice agent connected and ready!")
                self.connected = True
                return True
            else:
                logger.error(f"🤖 ❌ Expected ready message, got: {data}")
                return False
                
        except Exception as e:
            logger.error(f"🤖 ❌ Failed to connect to voice agent: {e}")
            return False
    
    async def send_audio(self, audio_data):
        """Send audio data to voice agent (convert to 16kHz PCM base64)"""
        if not self.connected or not self.websocket:
            return
            
        try:
            # Convert from 48kHz to 16kHz
            resampled = scipy.signal.resample(
                audio_data.astype(np.float32), 
                int(len(audio_data) * VOICE_AGENT_INPUT_RATE / SAMPLERATE)
            ).astype(np.int16)
            
            # Convert to base64
            audio_bytes = resampled.tobytes()
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            
            # Send to voice agent
            message = {
                "type": "audio",
                "data": audio_b64
            }

            await self.websocket.send(json.dumps(message))
            logger.debug(f"🤖 📤 Sent {len(resampled)} samples to voice agent")
            
        except Exception as e:
            logger.error(f"🤖 ❌ Error sending audio: {e}")

    async def _process_chat_message(self, reader: rtc.TextStreamReader, participant_identity: str):
        """Process incoming chat messages"""
        try:
            full_message = await reader.read_all()
            logger.info(f"[CHAT] {participant_identity}: {full_message}")

            # Echo the message back to demonstrate bidirectional communication
            message = {
                "type": "text",
                "data": full_message
            }

            return json.dumps(message)
        except Exception as e:
            logger.error(f"Error processing chat message: {e}")

    def text_listener(self):
        def _handle_chat_stream(reader: rtc.TextStreamReader, participant_identity: str):
            async def process_and_send():
                result = await self._process_chat_message(reader, participant_identity)
                await self.websocket.send(result)

            asyncio.create_task(process_and_send())

        return _handle_chat_stream

    
    async def listen_for_responses(self):
        """Listen for audio responses from voice agent"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                
                if data.get("type") == "audio":
                    # Decode base64 audio (24kHz)
                    audio_b64 = data.get("data", "")
                    audio_bytes = base64.b64decode(audio_b64)
                    audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
                    
                    # Convert from 24kHz to 48kHz for LiveKit
                    resampled = scipy.signal.resample(
                        audio_data.astype(np.float32),
                        int(len(audio_data) * SAMPLERATE / VOICE_AGENT_OUTPUT_RATE)
                    ).astype(np.int16)
                    
                    # Put in output queue
                    try:
                        await self.output_queue.put(resampled)
                        logger.debug(f"🤖 📥 Received {len(resampled)} samples from voice agent")
                    except asyncio.QueueFull:
                        logger.warning("🤖 ⚠️ Output queue full, dropping audio")
                if data.get("type") == "text":
                    print(data.get("data", ""))
                        
        except websockets.exceptions.ConnectionClosed:
            logger.info("🤖 Voice agent connection closed")
            self.connected = False
        except Exception as e:
            logger.error(f"🤖 ❌ Error listening for responses: {e}")
            self.connected = False
    
    async def disconnect(self):
        """Disconnect from voice agent"""
        self.connected = False
        if self.websocket:
            await self.websocket.close()


async def audio_publisher(room: rtc.Room, voice_agent_queue: asyncio.Queue):
    """Publish audio from voice agent back to LiveKit room"""
    logger.info("🎤 Starting audio publisher for voice agent responses...")
    
    # Create audio source
    source = rtc.AudioSource(SAMPLERATE, CHANNELS)
    track = rtc.LocalAudioTrack.create_audio_track("voice-agent-response", source)
    
    # Publish the track
    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_MICROPHONE
    
    await room.local_participant.publish_track(track, options)
    logger.info("🎤 ✅ Voice agent response track published")
    
    try:
        while True:
            # Get audio from voice agent
            audio_data = await voice_agent_queue.get()
            
            # Create AudioFrame and capture it
            frame = rtc.AudioFrame(
                data=audio_data.tobytes(),
                sample_rate=SAMPLERATE,
                num_channels=CHANNELS,
                samples_per_channel=len(audio_data)
            )
            
            await source.capture_frame(frame)
            logger.debug(f"🎤 📡 Published {len(audio_data)} samples to LiveKit")
            
    except Exception as e:
        logger.error(f"🎤 ❌ Error in audio publisher: {e}")


async def audio_player(queue: asyncio.Queue):
    """Pull from the queue and stream audio using sounddevice."""
    buffer = AudioBuffer(BLOCKSIZE)
    frames_played = 0

    def callback(outdata, frames, time, status):
        nonlocal frames_played
        if status:
            logger.warning(f"Audio callback status: {status}")

        # Try to fill buffer from queue
        frames_added = 0
        while not queue.empty():
            try:
                data = queue.get_nowait()
                buffer.add_frame(data)
                frames_added += len(data)
            except asyncio.QueueEmpty:
                break

        if frames_added > 0:
            logger.debug(f"Added {frames_added} frames to buffer")

        # Get exactly the right amount of data
        chunk = buffer.get_chunk()
        if chunk is not None:
            outdata[:] = chunk.reshape(-1, 1)
            frames_played += len(chunk)
            
            # Log every 5 seconds of audio
            if frames_played % (SAMPLERATE * 5) == 0:
                seconds_played = frames_played // SAMPLERATE
                logger.info(f"🔊 Playing audio: {seconds_played} seconds so far")
        else:
            # Not enough data, use what we have padded with zeros
            outdata[:] = buffer.get_padded_chunk().reshape(-1, 1)

    try:
        logger.info(f"🔊 Initializing audio output: {SAMPLERATE}Hz, {CHANNELS} channel(s)")
        
        stream = sd.OutputStream(
            samplerate=SAMPLERATE,
            channels=CHANNELS,
            blocksize=BLOCKSIZE,
            dtype="int16",
            callback=callback,
            latency="low",
        )
        
        with stream:
            logger.info("🎵 Audio player ready, waiting for audio data...")
            while True:
                await asyncio.sleep(0.1)  # keep the loop alive
                
    except Exception as e:
        logger.error(f"❌ Audio player error: {e}")


async def rtc_session(room, queue: asyncio.Queue, voice_agent: VoiceAgentClient):
    logger.info("Starting RTC session with voice agent integration...")
    
    # Wait for participants to join
    logger.info("Waiting for participants...")
    participant_wait_time = 0
    while len(room.remote_participants) == 0:
        if participant_wait_time % 5 == 0:
            logger.info(f"No remote participants yet. Waited {participant_wait_time} seconds...")
            logger.info(f"Room participants: {len(room.remote_participants)}")
            
        await asyncio.sleep(1)
        participant_wait_time += 1
        
        if participant_wait_time > 30:  # Wait max 30 seconds for participants
            logger.warning("No participants joined after 30 seconds")
            return

    logger.info(f"Found {len(room.remote_participants)} remote participant(s)")

    # Look for audio track
    track: rtc.RemoteAudioTrack | None = None
    track_wait_time = 0
    
    while not track:
        for participant_sid, participant in room.remote_participants.items():
            logger.info(f"Checking participant: {participant.identity} (SID: {participant_sid})")
            logger.info(f"  Track publications: {len(participant.track_publications)}")
            
            for track_sid, track_pub in participant.track_publications.items():
                logger.info(f"  Track {track_sid}: kind={track_pub.kind}, subscribed={track_pub.subscribed}, muted={track_pub.muted}")
                
                if track_pub.kind == rtc.TrackKind.KIND_AUDIO and track_pub.subscribed:
                    track = track_pub.track
                    logger.info(f"✅ Found subscribed audio track: {track_sid} from {participant.identity}")
                    break
            
            if track:
                break
        
        if not track:
            track_wait_time += 2
            if track_wait_time % 10 == 0:
                logger.info(f"Still waiting for audio track... ({track_wait_time}s)")
            await asyncio.sleep(2)
            
            # if track_wait_time > 60:  # Wait max 60 seconds for audio track
            #     logger.error("No audio track found after 60 seconds")
            #     return

    logger.info("🎵 Creating audio stream...")
    try:
        stream = rtc.AudioStream.from_track(
            track=track,
            sample_rate=SAMPLERATE,
            num_channels=1,
            noise_cancellation=noise_cancellation.BVC(),
        )
    except Exception as e:
        logger.error(f"Failed to create audio stream: {e}")
        return

    logger.info("🔊 Starting audio processing with voice agent...")
    frames_processed = 0
    try:
        async for audio_frame_event in stream:
            frame = audio_frame_event.frame
            audio_data = np.frombuffer(frame.data, dtype=np.int16)
            
            frames_processed += 1
            if frames_processed % 100 == 0:
                logger.debug(f"Processed {frames_processed} audio frames")

            # Send audio to voice agent
            await voice_agent.send_audio(audio_data)
            
            # Also send to local audio player (optional, for monitoring)
            try:
                await queue.put(audio_data)
            except asyncio.QueueFull:
                logger.warning("Audio queue full, dropping frame")
                continue

    except Exception as e:
        logger.error(f"Error processing audio stream: {e}")
    finally:
        logger.info("Cleaning up audio stream...")
        await stream.aclose()


async def main():
    logger.info("🎧 Starting LiveKit Voice Agent Integration...")
    active_tasks: List[asyncio.Task] = []
    
    # Check audio devices
    logger.info("Available audio devices:")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device['max_output_channels'] > 0:
            logger.info(f"  Output {i}: {device['name']}")
    
    # Create queues
    local_audio_queue = asyncio.Queue(maxsize=50)  # For local monitoring
    voice_agent_queue = asyncio.Queue(maxsize=50)  # For voice agent responses
    
    # Start local audio player
    player_task = asyncio.create_task(audio_player(local_audio_queue))

    # Get environment variables
    url = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
    api_key = os.getenv("LIVEKIT_API_KEY", "devkey")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "secret")
    
    logger.info(f"Connecting to LiveKit: {url}")
    logger.info(f"Using API key: {api_key}")

    token = (
        api.AccessToken(api_key, api_secret)
        .with_identity("python-voice-agent")
        .with_name("Python Voice Agent")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room="truongnn-room",
                agent=True,
            )
        )
        .to_jwt()
    )

    room = rtc.Room()
    
    # Add event handlers for debugging
    @room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        logger.info(f"👤 Participant connected: {participant.identity}")

    @room.on("participant_disconnected")  
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logger.info(f"👋 Participant disconnected: {participant.identity}")

    @room.on("track_published")
    def on_track_published(publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        logger.info(f"📡 Track published: {publication.sid} ({publication.kind}) by {participant.identity}")

    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        logger.info(f"🎧 Track subscribed: {publication.sid} ({track.kind}) from {participant.identity}")

    @room.on("track_unsubscribed")
    def on_track_unsubscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        logger.info(f"❌ Track unsubscribed: {publication.sid} from {participant.identity}")

    # async def send_echo_message(original_sender: str, message: str):
    #     """Echo a message back to the sender"""
    #     try:
    #         text_writer = await room.local_participant.stream_text(
    #             destination_identities=[original_sender],
    #             topic="chat"
    #         )
    #
    #         echo_msg = f"Echo: {message}"
    #         await text_writer.write(echo_msg)
    #         await text_writer.aclose()
    #
    #     except Exception as e:
    #         logger.error(f"Error sending echo message: {e}")

    async def _process_chat_message(reader: rtc.TextStreamReader, participant_identity: str):
        """Process incoming chat messages"""
        try:
            full_message = await reader.read_all()
            logger.info(f"[CHAT] {participant_identity}: {full_message}")

            # Echo the message back to demonstrate bidirectional communication
            message = {
                "type": "text",
                "data": full_message
            }

            return message
        except Exception as e:
            logger.error(f"Error processing chat message: {e}")

    # def _handle_chat_stream(reader: rtc.TextStreamReader, participant_identity: str):
    #     """Handle incoming chat messages"""
    #     task = asyncio.create_task(_process_chat_message(reader, participant_identity))
    #     active_tasks.append(task)
    #     task.add_done_callback(lambda _: active_tasks.remove(task))
    # Initialize voice agent
    voice_agent = VoiceAgentClient(VOICE_AGENT_URL, voice_agent_queue)
    
    try:
        # Connect to LiveKit room
        await room.connect(
            url,
            token,
            options=rtc.RoomOptions(
                auto_subscribe=True,
            ),
        )
        logger.info(f"✅ Connected to LiveKit room: {room.name}")
        logger.info(f"Local participant: {room.local_participant.identity}")
        
        # Connect to voice agent
        if await voice_agent.connect():
            logger.info("🤖 ✅ Voice agent connected successfully")
            
            # Start voice agent response listener
            voice_agent_listener = asyncio.create_task(voice_agent.listen_for_responses())
            
            # Start audio publisher for voice agent responses
            voice_agent_publisher = asyncio.create_task(audio_publisher(room, voice_agent_queue))

            room.register_text_stream_handler("chat", voice_agent.text_listener())
            
            # Start RTC session with voice agent integration
            await rtc_session(room, local_audio_queue, voice_agent)
            
            # Clean up voice agent tasks
            voice_agent_listener.cancel()
            voice_agent_publisher.cancel()
            
            try:
                await voice_agent_listener
            except asyncio.CancelledError:
                pass
                
            try:
                await voice_agent_publisher
            except asyncio.CancelledError:
                pass
        else:
            logger.error("🤖 ❌ Failed to connect to voice agent")
            
    except Exception as e:
        logger.error(f"❌ Error in main: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("🧹 Cleaning up...")
        await voice_agent.disconnect()
        await room.disconnect()
        player_task.cancel()
        try:
            await player_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
