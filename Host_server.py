#!/usr/bin/env python3
"""
Remote Command Client with WebSocket Support
Run on your PC to connect to target PC
Requirements: pip install flask requests python-socketio
"""

import requests
import json
import base64
import webbrowser
import threading
import time
from flask import Flask, render_template, request, jsonify, Response
import os
import urllib3
import ssl

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class RemoteClient:
    def __init__(self):
        self.target_host = None
        self.target_port = 5000
        self.base_url = None
        self.use_https = True  # Default to HTTPS
        self.verify_ssl = False  # Allow self-signed certificates
        
    def set_target(self, host, port=5000, use_https=True):
        """Set target server details"""
        self.target_host = host
        self.target_port = port
        self.use_https = use_https
        protocol = "https" if use_https else "http"
        self.base_url = f"{protocol}://{host}:{port}"
        
    def test_connection(self):
        """Test connection to target server"""
        try:
            # Try HTTPS first
            if self.use_https:
                response = requests.get(f"{self.base_url}/health", timeout=5, verify=self.verify_ssl)
                return response.status_code == 200
            else:
                response = requests.get(f"{self.base_url}/health", timeout=5)
                return response.status_code == 200
        except requests.exceptions.SSLError:
            # If HTTPS fails, try HTTP as fallback
            if self.use_https:
                print("HTTPS connection failed, trying HTTP fallback...")
                self.use_https = False
                self.base_url = f"http://{self.target_host}:{self.target_port}"
                return self.test_connection()
            return False
        except:
            return False
    
    def get_system_info(self):
        """Get system info from target"""
        try:
            if self.use_https:
                response = requests.get(f"{self.base_url}/system_info", timeout=10, verify=self.verify_ssl)
            else:
                response = requests.get(f"{self.base_url}/system_info", timeout=10)
            
            if response.status_code == 200:
                return response.json()
            return None
        except:
            return None
    
    def execute_command(self, command):
        """Start command execution on target server"""
        try:
            data = {'command': command}
            if self.use_https:
                response = requests.post(
                    f"{self.base_url}/execute",
                    json=data,
                    timeout=10,
                    verify=self.verify_ssl
                )
            else:
                response = requests.post(
                    f"{self.base_url}/execute",
                    json=data,
                    timeout=10
                )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'Server error: {response.status_code}'}
                
        except requests.exceptions.Timeout:
            return {'error': 'Command start timed out'}
        except Exception as e:
            return {'error': f'Connection error: {str(e)}'}
    
    def stop_command(self, process_id):
        """Stop a running command"""
        try:
            if self.use_https:
                response = requests.post(f"{self.base_url}/stop/{process_id}", timeout=5, verify=self.verify_ssl)
            else:
                response = requests.post(f"{self.base_url}/stop/{process_id}", timeout=5)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'Server error: {response.status_code}'}
        except Exception as e:
            return {'error': f'Error stopping command: {str(e)}'}
    
    def get_connection_info(self):
        """Get connection information for WebSocket"""
        protocol = "wss" if self.use_https else "ws"
        return {
            'protocol': protocol,
            'host': self.target_host,
            'port': self.target_port,
            'use_https': self.use_https
        }

# Global client instance
client = RemoteClient()

# Web interface
web_app = Flask(__name__)

@web_app.route('/')
def index():
    """Main web interface"""
    return render_template('index.html')

@web_app.route('/api/health')
def api_health():
    """Check connection to target server"""
    if not client.base_url:
        return jsonify({'connected': False, 'error': 'Target not configured'})
    
    if client.test_connection():
        return jsonify({
            'connected': True, 
            'target_info': f'{client.target_host}:{client.target_port}'
        })
    else:
        return jsonify({'connected': False, 'error': 'Cannot reach target server'})

@web_app.route('/api/target_info')
def api_target_info():
    """Get target server connection info for WebSocket"""
    if not client.base_url:
        return jsonify({'error': 'Target not configured'})
    
    conn_info = client.get_connection_info()
    return jsonify({
        'target_host': conn_info['host'],
        'target_port': conn_info['port'],
        'protocol': conn_info['protocol'],
        'use_https': conn_info['use_https']
    })

@web_app.route('/api/system_info')
def api_system_info():
    """Get system info from target"""
    try:
        info = client.get_system_info()
        if info:
            return jsonify({'success': True, 'info': info})
        else:
            return jsonify({'success': False, 'error': 'Could not get system info'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@web_app.route('/api/execute', methods=['POST'])
def api_execute():
    """Execute command on target server"""
    try:
        data = request.get_json()
        command = data.get('command', '')
        
        result = client.execute_command(command)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Client error: {str(e)}'})

@web_app.route('/api/server_status')
def api_server_status():
    """Get server busy status"""
    try:
        if client.use_https:
            response = requests.get(f"{client.base_url}/status", timeout=5, verify=client.verify_ssl)
        else:
            response = requests.get(f"{client.base_url}/status", timeout=5)
        
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'busy': False, 'error': f'Server error: {response.status_code}'})
    except Exception as e:
        return jsonify({'busy': False, 'error': f'Status check error: {str(e)}'})

@web_app.route('/api/poll/<process_id>')
def api_poll(process_id):
    """Polling fallback for streaming output"""
    try:
        # Get current output from server
        if client.use_https:
            response = requests.get(f"{client.base_url}/poll/{process_id}", timeout=5, verify=client.verify_ssl)
        else:
            response = requests.get(f"{client.base_url}/poll/{process_id}", timeout=5)
        
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'success': False, 'error': f'Server error: {response.status_code}'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Polling error: {str(e)}'})

@web_app.route('/api/stop/<process_id>', methods=['POST'])
def api_stop(process_id):
    """Stop command on target server"""
    try:
        result = client.stop_command(process_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Error stopping command: {str(e)}'})

@web_app.route('/api/input/<process_id>', methods=['POST'])
def api_input(process_id):
    """Send input to a running command on target server"""
    try:
        data = request.get_json()
        if not data or 'input' not in data:
            return jsonify({'error': 'Input text is required'}), 400
        
        input_text = data['input']
        
        # Send input to target server
        if client.use_https:
            response = requests.post(
                f"{client.base_url}/input/{process_id}",
                json={'input': input_text},
                timeout=5,
                verify=client.verify_ssl
            )
        else:
            response = requests.post(
                f"{client.base_url}/input/{process_id}",
                json={'input': input_text},
                timeout=5
            )
        
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'error': f'Server error: {response.status_code}'}), response.status_code
            
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request timed out'}), 408
    except Exception as e:
        return jsonify({'error': f'Error sending input: {str(e)}'}), 500

def start_web_interface():
    """Start the web interface"""
    web_app.run(host='127.0.0.1', port=8080, debug=False)

def main():
    print("=" * 60)
    print("Remote Command Client - HTTPS/WSS Edition")
    print("=" * 60)
    
    # Get target server details
    while True:
        target_ip = input("Enter target PC IP address: ").strip()
        if target_ip:
            break
        print("Please enter a valid IP address!")
    
    target_port = input("Enter target PC port (default 5000): ").strip()
    if not target_port:
        target_port = 5000
    else:
        try:
            target_port = int(target_port)
        except:
            print("Invalid port, using default 5000")
            target_port = 5000
    
    # Ask about HTTPS preference
    use_https_input = input("Use HTTPS? (Y/n): ").strip().lower()
    use_https = use_https_input != 'n' and use_https_input != 'no'
    
    # Configure client
    client.set_target(target_ip, target_port, use_https)
    
    protocol = "HTTPS" if use_https else "HTTP"
    print(f"\nConnecting to {target_ip}:{target_port} using {protocol}...")
    
    # Test connection
    if client.test_connection():
        final_protocol = "HTTPS" if client.use_https else "HTTP"
        print(f"Connection successful using {final_protocol}!")
        
        if use_https and not client.use_https:
            print("Note: Fell back to HTTP due to HTTPS connection issues")
        
        # Get system info
        sys_info = client.get_system_info()
        if sys_info:
            print(f"Target system: {sys_info.get('platform', 'Unknown')}")
            print(f"Hostname: {sys_info.get('hostname', 'Unknown')}")
    else:
        print("Cannot connect to target server!")
        print("Make sure the server is running on the target PC.")
        print("Press Enter to continue anyway (you can retry from web interface)")
        input()
    
    print("\n" + "=" * 60)
    print("Starting web interface with HTTPS/WSS streaming support...")
    print("Web interface will open at: http://localhost:8080")
    print("=" * 60)
    print("Security Features:")
    if client.use_https:
        print("- HTTPS communication with target server")
        print("- WSS (WebSocket Secure) for real-time streaming")
        print("- Self-signed certificates accepted")
    else:
        print("- HTTP communication (fallback mode)")
        print("- Standard WebSocket streaming")
    print("- Real-time streaming output")
    print("- Stop commands in real-time")
    print("- Command history")
    print("- Live status indicators")
    print("=" * 60)
    
    # Start web interface in background
    web_thread = threading.Thread(target=start_web_interface, daemon=True)
    web_thread.start()
    
    # Wait a moment then open browser
    time.sleep(2)
    try:
        webbrowser.open('http://localhost:8080')
    except:
        print("Could not auto-open browser. Please go to: http://localhost:8080")
    
    print("\nPress Ctrl+C to exit...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nGoodbye!")

if __name__ == '__main__':
    main()