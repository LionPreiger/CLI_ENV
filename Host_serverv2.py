#!/usr/bin/env python3
"""
Host Server v2 - WebSocket Client that connects to external server as a Host/Controller
Connects to: 217.154.254.231:9000/api/host/{host_id}/ws
Requirements: pip install websockets asyncio flask
"""

import asyncio
import websockets
import json
import threading
import time
import uuid
import logging
from typing import Optional, Dict, Any
from flask import Flask, render_template, request, jsonify
import webbrowser
import platform
import socket

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HostWebSocketClient:
    """WebSocket client that connects to external server as a host/controller"""
    
    def __init__(self, server_url: str, host_id: str):
        self.server_url = server_url
        self.host_id = host_id
        self.websocket = None
        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5  # seconds
        self.start_time = time.time()
        self.connected_vms = {}  # Track connected VMs
        self.command_responses = {}  # Store command responses
        
    async def connect(self):
        """Connect to the WebSocket server"""
        try:
            # Construct the full WebSocket URL for host
            ws_url = f"ws://{self.server_url}/api/host/{self.host_id}/ws"
            logger.info(f"Connecting to: {ws_url}")
            
            self.websocket = await websockets.connect(ws_url)
            logger.info(f"Successfully connected to server as Host {self.host_id}")
            self.running = True
            self.reconnect_attempts = 0
            
            # Send initial connection message
            await self.send_message({
                "type": "host_connection",
                "host_id": self.host_id,
                "message": "Host controller connected",
                "metadata": {
                    "status": "connected",
                    "system_info": self.get_system_info(),
                    "timestamp": time.time()
                }
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the WebSocket server"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            logger.info("Disconnected from server")
    
    async def send_message(self, message: Dict[str, Any]):
        """Send a message to the server"""
        if self.websocket:
            try:
                await self.websocket.send(json.dumps(message))
                logger.debug(f"Sent message: {message.get('type', 'unknown')}")
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
    
    async def send_command_to_vm(self, vm_id: str, command: str, command_id: str = None):
        """Send a command to a specific VM"""
        if not command_id:
            command_id = str(uuid.uuid4())
        
        message = {
            "type": "send_to_vm",
            "host_id": self.host_id,
            "message": command,
            "metadata": {
                "target_vm_id": vm_id,
                "message_type": "command",
                "command_id": command_id,
                "timestamp": time.time()
            }
        }
        
        await self.send_message(message)
        return command_id
    
    async def stop_vm_command(self, vm_id: str, command_id: str):
        """Stop a command on a specific VM"""
        message = {
            "type": "send_to_vm",
            "host_id": self.host_id,
            "message": command_id,
            "metadata": {
                "target_vm_id": vm_id,
                "message_type": "stop_command",
                "command_id": command_id,
                "timestamp": time.time()
            }
        }
        
        await self.send_message(message)
    
    async def send_input_to_vm(self, vm_id: str, command_id: str, input_text: str):
        """Send input to a running command on a specific VM"""
        message = {
            "type": "send_to_vm",
            "host_id": self.host_id,
            "message": input_text,
            "metadata": {
                "target_vm_id": vm_id,
                "message_type": "send_input",
                "command_id": command_id,
                "timestamp": time.time()
            }
        }
        
        await self.send_message(message)
    
    async def request_vm_list(self):
        """Request list of connected VMs"""
        message = {
            "type": "get_vm_list",
            "host_id": self.host_id,
            "message": "Request VM list",
            "metadata": {
                "timestamp": time.time()
            }
        }
        
        await self.send_message(message)
    
    async def handle_message(self, message: str):
        """Handle incoming messages from the server"""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            
            if msg_type == "vm_list":
                await self.handle_vm_list(data)
            elif msg_type == "vm_response":
                await self.handle_vm_response(data)
            elif msg_type == "vm_connected":
                await self.handle_vm_connected(data)
            elif msg_type == "vm_disconnected":
                await self.handle_vm_disconnected(data)
            elif msg_type == "server_response":
                await self.handle_server_response(data)
            else:
                logger.info(f"Received {msg_type}: {data.get('message', '')}")
                
        except json.JSONDecodeError:
            logger.info(f"Received plain text: {message}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def handle_vm_list(self, data: dict):
        """Handle VM list response"""
        vm_list = data.get("metadata", {}).get("vms", [])
        self.connected_vms = {vm["vm_id"]: vm for vm in vm_list}
        logger.info(f"Connected VMs: {list(self.connected_vms.keys())}")
    
    async def handle_vm_response(self, data: dict):
        """Handle response from a VM"""
        vm_id = data.get("metadata", {}).get("vm_id", "unknown")
        response_type = data.get("metadata", {}).get("response_type", "unknown")
        command_id = data.get("metadata", {}).get("command_id")
        
        # Store response for web interface
        if command_id:
            if command_id not in self.command_responses:
                self.command_responses[command_id] = []
            
            self.command_responses[command_id].append({
                "vm_id": vm_id,
                "type": response_type,
                "message": data.get("message", ""),
                "metadata": data.get("metadata", {}),
                "timestamp": time.time()
            })
        
        logger.info(f"VM {vm_id} response ({response_type}): {data.get('message', '')}")
    
    async def handle_vm_connected(self, data: dict):
        """Handle VM connection notification"""
        vm_id = data.get("metadata", {}).get("vm_id", "unknown")
        vm_info = data.get("metadata", {}).get("vm_info", {})
        self.connected_vms[vm_id] = vm_info
        logger.info(f"VM connected: {vm_id}")
    
    async def handle_vm_disconnected(self, data: dict):
        """Handle VM disconnection notification"""
        vm_id = data.get("metadata", {}).get("vm_id", "unknown")
        if vm_id in self.connected_vms:
            del self.connected_vms[vm_id]
        logger.info(f"VM disconnected: {vm_id}")
    
    async def handle_server_response(self, data: dict):
        """Handle server response messages"""
        logger.info(f"Server: {data.get('message', '')}")
    
    def get_system_info(self):
        """Get basic system information"""
        try:
            return {
                'hostname': platform.node(),
                'system': platform.system(),
                'platform': platform.platform(),
                'python_version': platform.python_version(),
                'role': 'host_controller'
            }
        except Exception as e:
            return {'error': f'Error getting system info: {str(e)}'}
    
    async def listen(self):
        """Listen for messages from the server"""
        try:
            # Start heartbeat task
            heartbeat_task = asyncio.create_task(self.send_heartbeat())
            
            while self.running:
                try:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                    await self.handle_message(message)
                except asyncio.TimeoutError:
                    continue
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Connection closed by server")
        except Exception as e:
            logger.error(f"Error in listen loop: {e}")
        finally:
            self.running = False
            if 'heartbeat_task' in locals():
                heartbeat_task.cancel()
    
    async def send_heartbeat(self):
        """Send periodic heartbeat to server"""
        while self.running:
            try:
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
                if self.running:
                    await self.send_message({
                        "type": "heartbeat",
                        "host_id": self.host_id,
                        "message": "Host alive",
                        "metadata": {
                            "timestamp": time.time(),
                            "status": "alive",
                            "connected_vms": len(self.connected_vms)
                        }
                    })
                    logger.debug("Heartbeat sent")
            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")
                break
    
    async def run_with_reconnect(self):
        """Run the client with automatic reconnection"""
        while True:
            try:
                if await self.connect():
                    # Request VM list after connection
                    await asyncio.sleep(1)
                    await self.request_vm_list()
                    await self.listen()
                else:
                    logger.error("Failed to connect to server")
                
                if not self.running:
                    break
                    
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
            
            # Handle reconnection
            if self.reconnect_attempts < self.max_reconnect_attempts:
                self.reconnect_attempts += 1
                logger.info(f"Attempting to reconnect... (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})")
                await asyncio.sleep(self.reconnect_delay)
            else:
                logger.error("Max reconnection attempts reached. Exiting.")
                break

# Global client instance
host_client = None

# Web interface
web_app = Flask(__name__)

@web_app.route('/')
def index():
    """Main web interface"""
    return render_template('index.html')

@web_app.route('/api/health')
def api_health():
    """Check connection to server"""
    if host_client and host_client.running:
        return jsonify({
            'connected': True,
            'host_id': host_client.host_id,
            'connected_vms': len(host_client.connected_vms)
        })
    else:
        return jsonify({'connected': False, 'error': 'Not connected to server'})

@web_app.route('/api/vms')
def api_vms():
    """Get list of connected VMs"""
    if host_client:
        return jsonify({
            'success': True,
            'vms': list(host_client.connected_vms.values()),
            'count': len(host_client.connected_vms)
        })
    else:
        return jsonify({'success': False, 'error': 'Host client not initialized'})

@web_app.route('/api/execute', methods=['POST'])
def api_execute():
    """Execute command on a specific VM"""
    try:
        data = request.get_json()
        vm_id = data.get('vm_id', '')
        command = data.get('command', '')
        
        if not vm_id or not command:
            return jsonify({'error': 'VM ID and command are required'})
        
        if not host_client or not host_client.running:
            return jsonify({'error': 'Not connected to server'})
        
        # Send command asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        command_id = loop.run_until_complete(
            host_client.send_command_to_vm(vm_id, command)
        )
        loop.close()
        
        return jsonify({
            'success': True,
            'command_id': command_id,
            'vm_id': vm_id,
            'command': command
        })
        
    except Exception as e:
        return jsonify({'error': f'Error executing command: {str(e)}'})

@web_app.route('/api/stop/<command_id>', methods=['POST'])
def api_stop(command_id):
    """Stop a command on a VM"""
    try:
        data = request.get_json()
        vm_id = data.get('vm_id', '')
        
        if not vm_id:
            return jsonify({'error': 'VM ID is required'})
        
        if not host_client or not host_client.running:
            return jsonify({'error': 'Not connected to server'})
        
        # Send stop command asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            host_client.stop_vm_command(vm_id, command_id)
        )
        loop.close()
        
        return jsonify({'success': True, 'message': 'Stop command sent'})
        
    except Exception as e:
        return jsonify({'error': f'Error stopping command: {str(e)}'})

@web_app.route('/api/input/<command_id>', methods=['POST'])
def api_input(command_id):
    """Send input to a running command on a VM"""
    try:
        data = request.get_json()
        vm_id = data.get('vm_id', '')
        input_text = data.get('input', '')
        
        if not vm_id or not input_text:
            return jsonify({'error': 'VM ID and input are required'})
        
        if not host_client or not host_client.running:
            return jsonify({'error': 'Not connected to server'})
        
        # Send input asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            host_client.send_input_to_vm(vm_id, command_id, input_text)
        )
        loop.close()
        
        return jsonify({'success': True, 'message': 'Input sent'})
        
    except Exception as e:
        return jsonify({'error': f'Error sending input: {str(e)}'})

@web_app.route('/api/responses/<command_id>')
def api_responses(command_id):
    """Get responses for a specific command"""
    if host_client and command_id in host_client.command_responses:
        return jsonify({
            'success': True,
            'responses': host_client.command_responses[command_id]
        })
    else:
        return jsonify({'success': False, 'responses': []})

def start_web_interface():
    """Start the web interface"""
    web_app.run(host='127.0.0.1', port=8080, debug=False)

async def main():
    """Main function"""
    global host_client
    
    print("=" * 50)
    print("Host WebSocket Client v2 Starting...")
    print("=" * 50)
    
    # Configuration
    SERVER_URL = "217.154.254.231:9000"
    
    # Generate host ID
    hostname = socket.gethostname()
    host_id = f"host-{hostname}-{str(uuid.uuid4())[:8]}"
    
    print(f"Host ID: {host_id}")
    print(f"Connecting to: {SERVER_URL}")
    print("=" * 50)
    
    # Create the client
    host_client = HostWebSocketClient(SERVER_URL, host_id)
    
    # Start web interface in background
    web_thread = threading.Thread(target=start_web_interface, daemon=True)
    web_thread.start()
    
    # Wait a moment then open browser
    await asyncio.sleep(2)
    try:
        webbrowser.open('http://localhost:8080')
        print("Web interface opened at: http://localhost:8080")
    except:
        print("Could not auto-open browser. Please go to: http://localhost:8080")
    
    try:
        print("🔗 Connecting to server...")
        await host_client.run_with_reconnect()
    except KeyboardInterrupt:
        print("\n⏹️  Shutdown requested by user")
        await host_client.disconnect()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await host_client.disconnect()
    
    print("✅ Host Client stopped.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")
    except Exception as e:
        print(f"Fatal error: {e}")
