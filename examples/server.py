#!/usr/bin/env python3
"""
Simple HTTP server để serve static files và cung cấp token generation cho LiveKit
"""

import asyncio
import json
import os
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import webbrowser
from dotenv import load_dotenv
load_dotenv()


# Import LiveKit API để tạo token
try:
    from livekit import api
    LIVEKIT_AVAILABLE = True
except ImportError:
    LIVEKIT_AVAILABLE = False
    print("⚠️ Warning: livekit-api not installed. Token generation will not work.")


class LiveKitHandler(SimpleHTTPRequestHandler):
    """Custom handler để xử lý requests và cung cấp API endpoints"""
    
    def __init__(self, *args, **kwargs):
        # Set directory to serve files from
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)
    
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)
        
        # API endpoint để tạo access token
        if parsed_path.path == '/api/token':
            self.handle_token_request(parsed_path)
        else:
            # Serve static files
            super().do_GET()
    
    def do_POST(self):
        """Handle POST requests"""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/api/token':
            self.handle_token_request(parsed_path, method='POST')
        else:
            self.send_error(404, "Not Found")
    
    def handle_token_request(self, parsed_path, method='GET'):
        """Xử lý request để tạo access token"""
        try:
            if not LIVEKIT_AVAILABLE:
                self.send_json_response({
                    'error': 'LiveKit API not available. Please install livekit-api package.'
                }, status=500)
                return
            
            # Lấy parameters
            if method == 'GET':
                params = parse_qs(parsed_path.query)
                identity = params.get('identity', [''])[0]
                room = params.get('room', [''])[0]
                name = params.get('name', [''])[0] or identity
            else:  # POST
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                identity = data.get('identity', '')
                room = data.get('room', '')
                name = data.get('name', '') or identity
            
            if not identity or not room:
                self.send_json_response({
                    'error': 'Missing required parameters: identity and room'
                }, status=400)
                return
            
            # Tạo access token
            token = self.generate_access_token(identity, room, name)
            
            if token:
                self.send_json_response({
                    'token': token,
                    'identity': identity,
                    'room': room,
                    'name': name
                })
            else:
                self.send_json_response({
                    'error': 'Failed to generate token. Please check LIVEKIT_API_KEY and LIVEKIT_API_SECRET'
                }, status=500)
                
        except Exception as e:
            print(f"Token generation error: {e}")
            self.send_json_response({
                'error': f'Token generation failed: {str(e)}'
            }, status=500)
    
    def generate_access_token(self, identity, room, name):
        """Tạo LiveKit access token"""
        try:
            api_key = os.getenv('LIVEKIT_API_KEY')
            api_secret = os.getenv('LIVEKIT_API_SECRET')
            
            if not api_key or not api_secret:
                print("⚠️ Warning: LIVEKIT_API_KEY hoặc LIVEKIT_API_SECRET chưa được set")
                return None
            
            token = (
                api.AccessToken(api_key, api_secret)
                .with_identity(identity)
                .with_name(name)
                .with_grants(
                    api.VideoGrants(
                        room_join=True,
                        room=room,
                        can_publish=True,
                        can_subscribe=True,
                    )
                )
                .to_jwt()
            )
            
            return token
            
        except Exception as e:
            print(f"Error generating token: {e}")
            return None
    
    def send_json_response(self, data, status=200):
        """Send JSON response"""
        json_data = json.dumps(data).encode('utf-8')
        
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(json_data)))
        self.end_headers()
        self.wfile.write(json_data)
    
    def log_message(self, format, *args):
        """Custom log format"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] {format % args}")


def start_server(port=8000):
    """Khởi động HTTP server"""
    server_address = ('', port)
    
    try:
        httpd = HTTPServer(server_address, LiveKitHandler)
        print(f"🚀 Server đang chạy tại http://localhost:{port}")
        print(f"📱 Mở trình duyệt và truy cập: http://localhost:{port}/mic_publisher.html")
        
        # Kiểm tra environment variables
        livekit_url = os.getenv('LIVEKIT_URL')
        livekit_api_key = os.getenv('LIVEKIT_API_KEY')
        livekit_api_secret = os.getenv('LIVEKIT_API_SECRET')
        
        print("\n🔧 Cấu hình môi trường:")
        print(f"   LIVEKIT_URL: {livekit_url or '❌ Chưa được set'}")
        print(f"   LIVEKIT_API_KEY: {'✅ Đã set' if livekit_api_key else '❌ Chưa được set'}")
        print(f"   LIVEKIT_API_SECRET: {'✅ Đã set' if livekit_api_secret else '❌ Chưa được set'}")
        
        if not all([livekit_url, livekit_api_key, livekit_api_secret]):
            print("\n⚠️  Cảnh báo: Vui lòng tạo file .env với nội dung:")
            print("   LIVEKIT_URL=wss://your-livekit-server.com")
            print("   LIVEKIT_API_KEY=your-api-key")
            print("   LIVEKIT_API_SECRET=your-api-secret")
        
        print(f"\n📚 API Endpoints:")
        print(f"   GET  /api/token?identity=user&room=room-name")
        print(f"   POST /api/token (JSON body)")
        
        print(f"\n🛑 Nhấn Ctrl+C để dừng server\n")
        
        # Tự động mở trình duyệt sau 2 giây
        def open_browser():
            time.sleep(2)
            try:
                webbrowser.open(f'http://localhost:{port}/mic_publisher.html')
            except:
                pass
        
        threading.Thread(target=open_browser, daemon=True).start()
        
        httpd.serve_forever()
        
    except KeyboardInterrupt:
        print("\n👋 Server đang dừng...")
        httpd.server_close()
    except Exception as e:
        print(f"❌ Lỗi server: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='LiveKit Microphone Publisher Server')
    parser.add_argument('--port', type=int, default=8000, help='Port để chạy server (mặc định: 8000)')
    
    args = parser.parse_args()
    
    start_server(args.port)
