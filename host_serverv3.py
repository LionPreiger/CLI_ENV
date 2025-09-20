#!/usr/bin/env python3
"""
Host Server v3 - WebSocket server for VM streaming and web UI
"""
import asyncio
import websockets
import json
import logging
from flask import Flask, render_template, jsonify
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

web_app = Flask(__name__)
stream_data = []
seen_messages = set()  # Track message IDs to prevent duplicates

@web_app.route('/')
def index():
    return render_template('index.html')

@web_app.route('/api/stream')
def api_stream():
    return jsonify({"stream": stream_data})

async def vm_stream_handler(websocket, path):
    async for message in websocket:
        try:
            data = json.loads(message)
            
            msg_type = data.get('type', '')
            msg_content = data.get('message', '')
            command_id = data.get('command_id', '')
            
            # Simple but effective duplicate detection
            # For input_request and commands, only allow one per content
            if msg_type in ['input_request', 'command']:
                msg_id = f"{msg_type}-{msg_content}"
            else:
                # For output, be more permissive but still avoid exact duplicates
                msg_id = f"{msg_type}-{command_id}-{msg_content}-{len(stream_data)}"
            
            # Only add if we haven't seen this exact message recently
            if msg_id not in seen_messages:
                seen_messages.add(msg_id)
                
                # Ensure timestamp exists
                if 'timestamp' not in data:
                    import time
                    data['timestamp'] = time.time()
                
                stream_data.append(data)
                logger.info(f"Added: {msg_type} - {msg_content[:20]}...")
                
                # Keep only last 50 messages for better performance
                if len(stream_data) > 50:
                    stream_data.pop(0)
                    
                # Reset seen_messages when it gets too large
                if len(seen_messages) > 100:
                    seen_messages.clear()
            else:
                logger.debug(f"Skipped duplicate: {msg_type}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")

async def start_ws_server():
    server = await websockets.serve(vm_stream_handler, 'localhost', 8765, ping_interval=None)
    logger.info("WebSocket server started on ws://localhost:8765/vm_stream")
    await server.wait_closed()

def start_web():
    import webbrowser
    threading.Timer(2, lambda: webbrowser.open('http://localhost:8080')).start()
    web_app.run(host='127.0.0.1', port=8080, debug=False)

if __name__ == "__main__":
    threading.Thread(target=start_web, daemon=True).start()
    asyncio.run(start_ws_server())
