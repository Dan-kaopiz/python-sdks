/**
 * LiveKit Microphone Publisher
 * Thu âm từ microphone và publish lên LiveKit server
 */

class MicrophonePublisher {
  constructor() {
    this.room = null;
    this.audioTrack = null;
    this.isConnected = false;
    this.isPublishing = false;
    this.audioContext = null;
    this.analyser = null;
    this.micStream = null;

    this.initializeElements();
    this.setupEventListeners();
    this.loadAudioDevices();
    this.log("🎉 Ứng dụng đã được khởi tạo");
  }

  initializeElements() {
    // Get DOM elements
    this.serverUrlInput = document.getElementById("serverUrl");
    this.roomNameInput = document.getElementById("roomName");
    this.participantNameInput = document.getElementById("participantName");
    this.accessTokenInput = document.getElementById("accessToken");
    this.audioDeviceSelect = document.getElementById("audioDevice");
    this.audioLevelFill = document.getElementById("audioLevelFill");
    this.statusContainer = document.getElementById("statusContainer");
    this.participantsList = document.getElementById("participantsList");
    this.logContainer = document.getElementById("logContainer");

    // Audio controls
    this.audioPlaybackEnabled = document.getElementById("audioPlaybackEnabled");
    this.masterVolume = document.getElementById("masterVolume");
    this.volumePercent = document.getElementById("volumePercent");
    this.audioDevicesInfo = document.getElementById("audioDevicesInfo");

    // Buttons
    this.testMicBtn = document.getElementById("testMicBtn");
    this.connectBtn = document.getElementById("connectBtn");
    this.publishBtn = document.getElementById("publishBtn");
  }

  setupEventListeners() {
    this.testMicBtn.addEventListener("click", () => this.testMicrophone());
    this.connectBtn.addEventListener("click", () => this.toggleConnection());
    this.publishBtn.addEventListener("click", () => this.togglePublishing());

    // Audio controls event listeners
    this.audioPlaybackEnabled.addEventListener("change", (e) => {
      this.updateAudioPlaybackSettings();
      this.log(
        `🔊 Audio playback: ${e.target.checked ? "enabled" : "disabled"}`
      );
    });

    this.masterVolume.addEventListener("input", (e) => {
      const volume = parseFloat(e.target.value);
      const percentage = Math.round(volume * 100);
      this.volumePercent.textContent = `${percentage}%`;
      this.updateAudioPlaybackSettings();
      this.log(`🔊 Volume set to: ${percentage}%`);
    });

    // Auto-refresh audio devices when dropdown is clicked
    this.audioDeviceSelect.addEventListener("click", () =>
      this.loadAudioDevices()
    );
  }

  updateAudioPlaybackSettings() {
    const enabled = this.audioPlaybackEnabled.checked;
    const volume = parseFloat(this.masterVolume.value);

    // Update all existing audio elements
    const audioElements = document.querySelectorAll('audio[id^="audio-"]');
    audioElements.forEach((audioElement) => {
      audioElement.volume = enabled ? volume : 0;
      audioElement.muted = !enabled;
    });

    // Update visual indicator
    const indicator = this.audioDevicesInfo.querySelector(".audio-indicator");
    if (indicator) {
      indicator.classList.toggle("muted", !enabled);
    }
  }

  async loadAudioDevices() {
    try {
      // Request microphone permission first to get device labels
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        // Stop the stream immediately, we just needed permission
        stream.getTracks().forEach((track) => track.stop());
      } catch (permissionError) {
        this.log("⚠️ Cần cấp quyền microphone để xem tên thiết bị");
      }

      const devices = await navigator.mediaDevices.enumerateDevices();
      const audioInputs = devices.filter(
        (device) => device.kind === "audioinput"
      );

      // Clear existing options
      this.audioDeviceSelect.innerHTML =
        '<option value="">Chọn thiết bị...</option>';

      // Add audio input devices
      audioInputs.forEach((device, index) => {
        const option = document.createElement("option");
        option.value = device.deviceId;
        option.textContent = device.label || `Microphone ${index + 1}`;
        this.audioDeviceSelect.appendChild(option);
      });

      // Auto-select first device if available
      if (audioInputs.length > 0 && !this.audioDeviceSelect.value) {
        this.audioDeviceSelect.selectedIndex = 1; // Select first actual device (skip "Chọn thiết bị...")
      }

      this.log(`📱 Tìm thấy ${audioInputs.length} thiết bị microphone`);
    } catch (error) {
      this.logError("❌ Không thể tải danh sách thiết bị âm thanh", error);
    }
  }

  async testMicrophone() {
    try {
      const deviceId = this.audioDeviceSelect.value;
      if (!deviceId) {
        alert("Vui lòng chọn thiết bị microphone trước");
        return;
      }

      this.testMicBtn.textContent = "🎤 Đang test...";
      this.testMicBtn.disabled = true;

      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { deviceId: deviceId ? { exact: deviceId } : undefined },
      });

      this.log("🎤 Bắt đầu test microphone trong 5 giây...");

      // Setup audio analysis
      this.setupAudioAnalysis(stream);

      // Test for 5 seconds
      setTimeout(() => {
        stream.getTracks().forEach((track) => track.stop());
        this.stopAudioAnalysis();
        this.testMicBtn.textContent = "🎤 Test Microphone";
        this.testMicBtn.disabled = false;
        this.log("✅ Test microphone hoàn thành");
      }, 5000);
    } catch (error) {
      this.logError("❌ Test microphone thất bại", error);
      this.testMicBtn.textContent = "🎤 Test Microphone";
      this.testMicBtn.disabled = false;
    }
  }

  setupAudioAnalysis(stream) {
    try {
      this.audioContext = new (window.AudioContext ||
        window.webkitAudioContext)();
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 256;

      const source = this.audioContext.createMediaStreamSource(stream);
      source.connect(this.analyser);

      this.updateAudioLevel();
    } catch (error) {
      this.logError("❌ Không thể thiết lập audio analysis", error);
    }
  }

  updateAudioLevel() {
    if (!this.analyser) return;

    const bufferLength = this.analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const updateLevel = () => {
      if (!this.analyser) return;

      this.analyser.getByteFrequencyData(dataArray);

      // Calculate average volume
      let sum = 0;
      for (let i = 0; i < bufferLength; i++) {
        sum += dataArray[i];
      }
      const average = sum / bufferLength;
      const percentage = (average / 255) * 100;

      this.audioLevelFill.style.width = `${percentage}%`;

      // Continue updating
      requestAnimationFrame(updateLevel);
    };

    updateLevel();
  }

  stopAudioAnalysis() {
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
      this.analyser = null;
    }
    this.audioLevelFill.style.width = "0%";
  }

  async toggleConnection() {
    if (!this.isConnected) {
      await this.connect();
    } else {
      await this.disconnect();
    }
  }

  async connect() {
    try {
      const serverUrl = this.serverUrlInput.value.trim();
      const roomName = this.roomNameInput.value.trim();
      const participantName = this.participantNameInput.value.trim();
      const accessToken = this.accessTokenInput.value.trim();

      if (!serverUrl || !roomName || !participantName) {
        alert("Vui lòng điền đầy đủ thông tin kết nối");
        return;
      }

      this.updateStatus("connecting", "🔄 Đang kết nối...");
      this.connectBtn.textContent = "🔄 Đang kết nối...";
      this.connectBtn.disabled = true;

      // Check if LiveKit is available
      if (typeof LivekitClient === "undefined") {
        throw new Error(
          "LiveKit library chưa được load. Vui lòng refresh trang và thử lại."
        );
      }

      // Create room instance
      this.room = new LivekitClient.Room({
        adaptiveStream: true,
        dynacast: true,
      });

      // Setup room event listeners
      this.setupRoomEventListeners();

      // Connect to room
      let token = accessToken;
      if (!token) {
        // Get token from server API
        token = await this.getTokenFromServer(participantName, roomName);
      }

      await this.room.connect(serverUrl, token);

      this.isConnected = true;
      this.updateStatus("connected", "✅ Đã kết nối thành công!");
      this.connectBtn.textContent = "🔌 Ngắt kết nối";
      this.connectBtn.disabled = false;
      this.publishBtn.disabled = false;

      this.log(`✅ Đã kết nối đến phòng: ${roomName}`);
    } catch (error) {
      this.logError("❌ Kết nối thất bại", error);
      this.updateStatus("disconnected", "❌ Kết nối thất bại");
      this.connectBtn.textContent = "🔗 Kết nối";
      this.connectBtn.disabled = false;
    }
  }

  async getTokenFromServer(identity, roomName) {
    try {
      const response = await fetch("/api/token", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          identity: identity,
          room: roomName,
          name: identity,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();

      if (data.error) {
        throw new Error(data.error);
      }

      this.log(`🔑 Đã nhận token từ server cho phòng: ${roomName}`);
      return data.token;
    } catch (error) {
      this.logError("❌ Không thể lấy token từ server", error);

      // Fallback to client-side token generation for demo
      this.log("⚠️ Đang sử dụng token demo (không an toàn cho production)");
      return this.generateAccessToken(identity, roomName);
    }
  }

  async generateAccessToken(identity, roomName) {
    // This is a simple token generation for demo purposes
    // In production, tokens should be generated on your server
    const payload = {
      iss: "livekit",
      sub: identity,
      aud: "livekit",
      exp: Math.floor(Date.now() / 1000) + 86400, // 24 hours
      nbf: Math.floor(Date.now() / 1000),
      video: {
        room: roomName,
        roomJoin: true,
        roomRecord: false,
        roomAdmin: false,
        roomList: false,
        canPublish: true,
        canSubscribe: true,
      },
    };

    // For demo purposes, return a dummy token
    // In production, implement proper JWT token generation on server
    return btoa(JSON.stringify(payload));
  }

  setupRoomEventListeners() {
    this.room
      .on(LivekitClient.RoomEvent.Connected, () => {
        this.log("🎉 Room connected event triggered");
      })
      .on(LivekitClient.RoomEvent.Disconnected, () => {
        this.log("👋 Room disconnected");
        this.handleDisconnection();
      })
      .on(LivekitClient.RoomEvent.ParticipantConnected, (participant) => {
        this.log(`👤 Participant joined: ${participant.identity}`);
        this.updateParticipantsList();
      })
      .on(LivekitClient.RoomEvent.ParticipantDisconnected, (participant) => {
        this.log(`👋 Participant left: ${participant.identity}`);
        this.updateParticipantsList();
      })
      .on(
        LivekitClient.RoomEvent.TrackSubscribed,
        (track, publication, participant) => {
          this.log(
            `🎧 Subscribed to ${participant.identity}'s ${track.kind} track`
          );

          // Handle audio track subscription - this is where voice agent response comes
          if (track.kind === LivekitClient.Track.Kind.Audio) {
            this.handleRemoteAudioTrack(track, participant);
          }
        }
      )
      .on(
        LivekitClient.RoomEvent.TrackUnsubscribed,
        (track, publication, participant) => {
          this.log(
            `❌ Unsubscribed from ${participant.identity}'s ${track.kind} track`
          );

          // Clean up audio element when track is unsubscribed
          if (track.kind === LivekitClient.Track.Kind.Audio) {
            this.removeRemoteAudioTrack(track, participant);
          }
        }
      );
  }

  handleRemoteAudioTrack(track, participant) {
    try {
      this.log(`🔊 Setting up audio playback for ${participant.identity}`);

      // Create audio element for this remote participant
      const audioElement = document.createElement("audio");
      audioElement.id = `audio-${participant.sid}`;
      audioElement.autoplay = true;
      audioElement.controls = false; // Hide controls, but you can show them for debugging
      audioElement.style.display = "none"; // Hide from UI

      // Apply current volume settings
      const enabled = this.audioPlaybackEnabled.checked;
      const volume = parseFloat(this.masterVolume.value);
      audioElement.volume = enabled ? volume : 0;
      audioElement.muted = !enabled;

      // Set the MediaStream from the track
      audioElement.srcObject = new MediaStream([track.mediaStreamTrack]);

      // Add to page (even if hidden)
      document.body.appendChild(audioElement);

      // Log when audio starts playing
      audioElement.onplaying = () => {
        this.log(`🔊 ✅ Playing audio from ${participant.identity}`);

        // Update visual indicator
        const indicator =
          this.audioDevicesInfo.querySelector(".audio-indicator");
        if (indicator && enabled) {
          indicator.classList.remove("muted");
        }
      };

      audioElement.onerror = (error) => {
        this.logError(
          `🔊 ❌ Audio playback error for ${participant.identity}`,
          error
        );
      };

      // Add volume debug info
      this.log(
        `🔊 Audio element created for ${
          participant.identity
        } (Volume: ${Math.round(audioElement.volume * 100)}%)`
      );
    } catch (error) {
      this.logError(
        `🔊 ❌ Failed to setup audio playback for ${participant.identity}`,
        error
      );
    }
  }

  removeRemoteAudioTrack(track, participant) {
    try {
      const audioElement = document.getElementById(`audio-${participant.sid}`);
      if (audioElement) {
        audioElement.pause();
        audioElement.srcObject = null;
        audioElement.remove();
        this.log(`🔊 Removed audio element for ${participant.identity}`);
      }
    } catch (error) {
      this.logError(
        `🔊 ❌ Failed to remove audio element for ${participant.identity}`,
        error
      );
    }
  }

  async disconnect() {
    try {
      if (this.isPublishing) {
        await this.stopPublishing();
      }

      if (this.room) {
        await this.room.disconnect();
        this.room = null;
      }

      this.handleDisconnection();
      this.log("👋 Đã ngắt kết nối");
    } catch (error) {
      this.logError("❌ Lỗi khi ngắt kết nối", error);
    }
  }

  handleDisconnection() {
    this.isConnected = false;
    this.isPublishing = false;

    this.updateStatus("disconnected", "📱 Trạng thái: Chưa kết nối");
    this.connectBtn.textContent = "🔗 Kết nối";
    this.connectBtn.disabled = false;
    this.publishBtn.textContent = "📡 Bắt đầu publish";
    this.publishBtn.disabled = true;

    this.stopAudioAnalysis();
    this.updateParticipantsList();
  }

  async togglePublishing() {
    if (!this.isPublishing) {
      await this.startPublishing();
    } else {
      await this.stopPublishing();
    }
  }

  async startPublishing() {
    try {
      const deviceId = this.audioDeviceSelect.value;
      if (!deviceId) {
        alert("Vui lòng chọn thiết bị microphone");
        return;
      }

      this.publishBtn.textContent = "📡 Đang publish...";
      this.publishBtn.disabled = true;

      // Get microphone stream
      this.micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: deviceId ? { exact: deviceId } : undefined,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      // Create and publish audio track using the simpler API
      await this.room.localParticipant.setMicrophoneEnabled(true, {
        deviceId: deviceId,
      });

      this.isPublishing = true;
      this.publishBtn.textContent = "🛑 Dừng publish";
      this.publishBtn.disabled = false;
      this.publishBtn.classList.add("pulse");

      // Setup audio level monitoring
      this.setupAudioAnalysis(this.micStream);

      this.log("📡 Đã bắt đầu publish microphone");
    } catch (error) {
      this.logError("❌ Không thể publish microphone", error);
      this.publishBtn.textContent = "📡 Bắt đầu publish";
      this.publishBtn.disabled = false;
    }
  }

  async stopPublishing() {
    try {
      // Use the simpler API to disable microphone
      await this.room.localParticipant.setMicrophoneEnabled(false);

      if (this.micStream) {
        this.micStream.getTracks().forEach((track) => track.stop());
        this.micStream = null;
      }

      this.stopAudioAnalysis();

      this.isPublishing = false;
      this.publishBtn.textContent = "📡 Bắt đầu publish";
      this.publishBtn.classList.remove("pulse");

      this.log("🛑 Đã dừng publish microphone");
    } catch (error) {
      this.logError("❌ Lỗi khi dừng publish", error);
    }
  }

  updateStatus(status, message) {
    this.statusContainer.className = `status ${status}`;
    this.statusContainer.textContent = message;
  }

  updateParticipantsList() {
    if (!this.room) {
      this.participantsList.innerHTML = `
                <p style="text-align: center; color: #666; font-style: italic;">
                    Chưa có người tham gia nào...
                </p>
            `;
      return;
    }

    const participants = Array.from(this.room.participants.values());
    participants.push(this.room.localParticipant); // Add local participant

    if (participants.length === 0) {
      this.participantsList.innerHTML = `
                <p style="text-align: center; color: #666; font-style: italic;">
                    Chưa có người tham gia nào...
                </p>
            `;
      return;
    }

    this.participantsList.innerHTML = participants
      .map((participant) => {
        const isLocal = participant === this.room.localParticipant;
        const audioTracks = Array.from(
          participant.audioTrackPublications.values()
        );
        const hasAudio = audioTracks.some((track) => !track.isMuted);

        // Check if this is the voice agent
        const isVoiceAgent =
          participant.identity.includes("voice-agent") ||
          participant.identity.includes("python-voice-agent");

        // Show audio status with more detail
        let audioStatus = "🔇 Tắt âm";
        if (hasAudio) {
          if (isVoiceAgent) {
            audioStatus = "🤖 Voice Agent Response";
          } else if (isLocal) {
            audioStatus = "🎤 Đang phát";
          } else {
            audioStatus = "🎧 Có âm thanh";
          }
        }

        return `
                <div class="participant">
                    <div class="participant-info">
                        <div class="participant-avatar">
                            ${
                              isVoiceAgent
                                ? "🤖"
                                : participant.identity.charAt(0).toUpperCase()
                            }
                        </div>
                        <div>
                            <div class="participant-name">
                                ${participant.identity} ${
          isLocal ? "(Bạn)" : ""
        }
                                ${isVoiceAgent ? "(AI)" : ""}
                            </div>
                            <div class="participant-status">
                                ${audioStatus}
                            </div>
                        </div>
                    </div>
                    <div class="audio-controls">
                        ${
                          !isLocal && hasAudio
                            ? `<span class="audio-indicator ${
                                !this.audioPlaybackEnabled.checked
                                  ? "muted"
                                  : ""
                              }"></span>`
                            : ""
                        }
                        ${isLocal ? "🏠" : isVoiceAgent ? "🤖" : "👤"}
                    </div>
                </div>
            `;
      })
      .join("");
  }

  log(message) {
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = document.createElement("div");
    logEntry.innerHTML = `<span style="color: #666;">[${timestamp}]</span> ${message}`;
    this.logContainer.appendChild(logEntry);
    this.logContainer.scrollTop = this.logContainer.scrollHeight;
  }

  logError(message, error) {
    console.error(message, error);
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = document.createElement("div");
    logEntry.innerHTML = `<span style="color: #666;">[${timestamp}]</span> <span style="color: #ff6666;">${message}: ${error.message}</span>`;
    this.logContainer.appendChild(logEntry);
    this.logContainer.scrollTop = this.logContainer.scrollHeight;
  }
}

// Initialize the application when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
  window.micPublisher = new MicrophonePublisher();
});

// Handle page unload
window.addEventListener("beforeunload", () => {
  if (window.micPublisher && window.micPublisher.room) {
    window.micPublisher.disconnect();
  }
});
