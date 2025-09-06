#!/usr/bin/env python3
"""
Remote Command Server with WebSocket Support
Install on target PC and run as: python VM_client.py
Requirements: pip install flask flask-socketio
"""

import subprocess
import platform
import sys
import os
import threading
import time
import signal
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit, disconnect
import tempfile
import json
import queue
import uuid
import ssl
import ipaddress
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-this-in-production'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global storage for running processes
running_processes = {}
process_outputs = {}
server_busy = False  # Track if server is currently executing a command
websocket_clients = {}  # Track WebSocket clients by process_id

def generate_self_signed_cert():
    """Generate a self-signed certificate for HTTPS"""
    cert_file = "server.crt"
    key_file = "server.key"
    
    # Check if certificates already exist
    if os.path.exists(cert_file) and os.path.exists(key_file):
        print("SSL certificates found, using existing certificates.")
        return cert_file, key_file
    
    print("Generating self-signed SSL certificate...")
    
    try:
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        
        # Get hostname/IP for certificate
        import socket
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except:
            local_ip = "127.0.0.1"
        
        # Create certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"State"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, u"City"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Remote Command Server"),
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(hostname),
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                x509.IPAddress(ipaddress.IPv4Address(local_ip)),
            ]),
            critical=False,
        ).sign(private_key, hashes.SHA256())
        
        # Write certificate to file
        with open(cert_file, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        # Write private key to file
        with open(key_file, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        print(f"SSL certificate generated: {cert_file}")
        print(f"SSL private key generated: {key_file}")
        print(f"Certificate valid for: {hostname}, localhost, 127.0.0.1, {local_ip}")
        
        return cert_file, key_file
    
    except Exception as e:
        print(f"Failed to generate SSL certificate: {e}")
        raise e

class StreamingCommandExecutor:
    def __init__(self):
        self.allowed_commands = [
            'python', 'python3', 'pip', 'pip3', 'dir', 'ls', 'echo', 'whoami', 'date', 
            'ipconfig', 'ifconfig', 'ping', 'curl', 'wget', 'git', 'cat', 'head', 'tail',
            'find', 'grep', 'sort', 'uniq', 'wc', 'ps', 'top', 'df', 'du', 'free',
            'sudo', 'su', 'ssh', 'read', 'passwd', 'apt', 'yum', 'npm', 'node'
        ]
    
    def is_safe_command(self, command):
        """Basic safety check for commands"""
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False
        
        base_cmd = cmd_parts[0].lower()
        
        # Block dangerous commands
        dangerous = ['rm', 'del', 'format', 'shutdown', 'reboot', 'kill', 'killall', 'pkill']
        if any(danger in base_cmd for danger in dangerous):
            return False
            
        return True
    
    def execute_command_streaming(self, command, process_id):
        """Execute command with streaming output and interactive input support (PTY for Windows/Linux)"""
        if not self.is_safe_command(command):
            return False, "Command not allowed for security reasons"

        try:
            system = platform.system().lower()
            output_queue = queue.Queue()
            process_outputs[process_id] = {
                'queue': output_queue,
                'complete': False,
                'exit_code': None,
                'full_output': '',
                'waiting_for_input': False,
                'last_output_time': time.time()
            }

            # Special handling for sudo commands to ensure proper terminal behavior
            if command.strip().startswith('sudo '):
                # Add -S flag to read password from stdin if not already present
                if '-S' not in command and '--stdin' not in command:
                    command = command.replace('sudo ', 'sudo -S ', 1)

            if system.startswith('win'):
                try:
                    import pywinpty
                    spawn_cmd = command if isinstance(command, str) else ' '.join(command)
                    pty_handle = pywinpty.PTY(spawn_cmd)
                    running_processes[process_id] = pty_handle

                    def read_output():
                        full_output = ''
                        try:
                            while True:
                                data = pty_handle.read(1024)
                                if not data:
                                    break
                                decoded = data.decode(errors='ignore') if isinstance(data, bytes) else data
                                full_output += decoded
                                for line in decoded.splitlines():
                                    output_queue.put(('output', line))
                                    print(line)
                                process_outputs[process_id]['last_output_time'] = time.time()
                            exit_code = pty_handle.get_exit_code() if hasattr(pty_handle, 'get_exit_code') else 0
                            process_outputs[process_id]['exit_code'] = exit_code
                            process_outputs[process_id]['complete'] = True
                            process_outputs[process_id]['full_output'] = full_output
                            output_queue.put(('complete', exit_code))
                        except Exception as e:
                            output_queue.put(('error', str(e)))
                            process_outputs[process_id]['complete'] = True
                        finally:
                            global server_busy
                            server_busy = False
                            if process_id in running_processes:
                                del running_processes[process_id]

                    thread = threading.Thread(target=read_output, daemon=True)
                    thread.start()
                    return True, process_id
                except ImportError:
                    print("pywinpty not installed. Falling back to subprocess. To see all output, install pywinpty: pip install pywinpty")

            elif system in ('linux', 'darwin') or 'microsoft' in platform.release().lower():
                import pty
                import select
                import shlex
                import fcntl
                import termios
                import tty
                
                master_fd, slave_fd = pty.openpty()
                
                # Configure terminal attributes for proper interactive behavior
                try:
                    # Set terminal to raw mode for better interaction
                    attrs = termios.tcgetattr(slave_fd)
                    attrs[3] = attrs[3] & ~termios.ECHO  # Turn off echo initially
                    termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)
                except:
                    pass
                
                # Make master_fd non-blocking for immediate reads
                flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
                fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                
                # Set up proper environment for sudo and interactive commands
                env = os.environ.copy()
                env.update({
                    'TERM': 'xterm-256color',
                    'SHELL': '/bin/bash',
                    'PATH': env.get('PATH', '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'),
                    'HOME': env.get('HOME', '/home/' + env.get('USER', 'user')),
                    'USER': env.get('USER', 'user'),
                    'LOGNAME': env.get('LOGNAME', env.get('USER', 'user')),
                    'SUDO_ASKPASS': '',  # Clear any askpass helper
                })
                
                cmd_args = command if isinstance(command, list) else shlex.split(command)
                process = subprocess.Popen(
                    cmd_args,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    preexec_fn=os.setsid,  # Create new session to handle signals properly
                    universal_newlines=False,  # Use bytes to avoid encoding issues
                    env=env  # Use our enhanced environment
                )
                running_processes[process_id] = {'process': process, 'master_fd': master_fd, 'slave_fd': slave_fd}

                def read_output():
                    full_output = ''
                    try:
                        while True:
                            # Use very short timeout for immediate response
                            rlist, _, _ = select.select([master_fd], [], [], 0.01)
                            if master_fd in rlist:
                                try:
                                    # Read smaller chunks for more immediate streaming
                                    data = os.read(master_fd, 256)
                                    if not data:
                                        break
                                    
                                    decoded = data.decode('utf-8', errors='replace')
                                    full_output += decoded
                                    
                                    # Send immediately, character by character for prompts
                                    output_queue.put(('output', decoded))
                                    print(decoded, end='', flush=True)  # Force flush to console
                                    process_outputs[process_id]['last_output_time'] = time.time()
                                    process_outputs[process_id]['full_output'] = full_output
                                    
                                    # Enhanced detection for password prompts and input requests
                                    decoded_lower = decoded.lower()
                                    if any(prompt in decoded_lower for prompt in [
                                        '[sudo] password for', 'password:', 'password for',
                                        'enter password', 'sudo password', ': ', 'login:',
                                        'username:', 'passphrase:', 'pin:'
                                    ]) or decoded.endswith(': ') or decoded.endswith('$ '):
                                        process_outputs[process_id]['waiting_for_input'] = True
                                        output_queue.put(('input_request', decoded.strip()))
                                        
                                except OSError as e:
                                    if e.errno == 11:  # EAGAIN/EWOULDBLOCK - no data available
                                        pass
                                    else:
                                        break
                            
                            # Check if process is still running
                            if process.poll() is not None:
                                # Process finished, read any remaining data
                                try:
                                    while True:
                                        data = os.read(master_fd, 256)
                                        if not data:
                                            break
                                        decoded = data.decode('utf-8', errors='replace')
                                        full_output += decoded
                                        output_queue.put(('output', decoded))
                                        print(decoded, end='', flush=True)
                                except OSError:
                                    pass
                                break
                            
                            # Small sleep to prevent excessive CPU usage
                            time.sleep(0.001)
                            
                        exit_code = process.wait()
                        process_outputs[process_id]['exit_code'] = exit_code
                        process_outputs[process_id]['complete'] = True
                        process_outputs[process_id]['full_output'] = full_output
                        output_queue.put(('complete', exit_code))
                    except Exception as e:
                        output_queue.put(('error', str(e)))
                        process_outputs[process_id]['complete'] = True
                    finally:
                        global server_busy
                        server_busy = False
                        if process_id in running_processes:
                            del running_processes[process_id]
                        try:
                            os.close(master_fd)
                            os.close(slave_fd)
                        except:
                            pass

                thread = threading.Thread(target=read_output, daemon=True)
                thread.start()
                return True, process_id

            # Fallback: regular subprocess with improved streaming
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=False,  # Use bytes for better control
                bufsize=0,   # Unbuffered for immediate output
                universal_newlines=False
            )
            running_processes[process_id] = process

            def read_output():
                full_output = ''
                try:
                    while True:
                        # Read small chunks for immediate streaming
                        data = process.stdout.read(256)
                        if not data:
                            if process.poll() is not None:
                                break
                            time.sleep(0.01)  # Short sleep when no data
                            continue
                            
                        decoded = data.decode('utf-8', errors='replace')
                        full_output += decoded
                        output_queue.put(('output', decoded))
                        print(decoded, end='', flush=True)
                        process_outputs[process_id]['last_output_time'] = time.time()
                        process_outputs[process_id]['full_output'] = full_output
                        
                        # Check for interactive prompts
                        if '[sudo]' in decoded.lower() or 'password' in decoded.lower() or decoded.endswith(': '):
                            process_outputs[process_id]['waiting_for_input'] = True
                            output_queue.put(('input_request', decoded.strip()))
                        
                    exit_code = process.wait()
                    process_outputs[process_id]['exit_code'] = exit_code
                    process_outputs[process_id]['complete'] = True
                    process_outputs[process_id]['full_output'] = full_output
                    output_queue.put(('complete', exit_code))
                except Exception as e:
                    output_queue.put(('error', str(e)))
                    process_outputs[process_id]['complete'] = True
                finally:
                    global server_busy
                    server_busy = False
                    if process_id in running_processes:
                        del running_processes[process_id]

            thread = threading.Thread(target=read_output, daemon=True)
            thread.start()
            return True, process_id

        except Exception as e:
            return False, f"Error starting command: {str(e)}"
    
    def stop_command(self, process_id):
        """Stop a running command"""
        if process_id in running_processes:
            try:
                proc_info = running_processes[process_id]
                
                # Handle different process storage formats
                if isinstance(proc_info, dict):
                    # Linux/WSL with PTY
                    process = proc_info['process']
                    master_fd = proc_info.get('master_fd')
                    slave_fd = proc_info.get('slave_fd')
                    
                    # Try to terminate gracefully
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    except:
                        process.terminate()
                    
                    # Wait a bit for graceful termination
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        # Force kill if needed
                        try:
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                        except:
                            process.kill()
                        process.wait()
                    
                    # Clean up file descriptors
                    try:
                        if master_fd:
                            os.close(master_fd)
                        if slave_fd:
                            os.close(slave_fd)
                    except:
                        pass
                else:
                    # Regular subprocess or Windows PTY
                    process = proc_info
                    process.terminate()
                    
                    # Wait a bit for graceful termination
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        # Force kill if needed
                        process.kill()
                        process.wait()
                
                return True, "Command stopped"
            except Exception as e:
                return False, f"Error stopping command: {str(e)}"
        else:
            return False, "Process not found or already completed"
    
    def send_input(self, process_id, input_text):
        """Send input to a running process"""
        if process_id in running_processes:
            try:
                proc_info = running_processes[process_id]
                
                # Handle different process storage formats
                if isinstance(proc_info, dict):
                    # Linux/WSL with PTY
                    process = proc_info['process']
                    master_fd = proc_info.get('master_fd')
                    
                    if process.poll() is None:  # Process is still running
                        # For PTY, write to master_fd
                        if master_fd:
                            input_bytes = (input_text + '\n').encode('utf-8')
                            os.write(master_fd, input_bytes)
                        else:
                            # Fallback to stdin
                            process.stdin.write(input_text + '\n')
                            process.stdin.flush()
                        
                        # Reset the waiting_for_input flag
                        if process_id in process_outputs:
                            process_outputs[process_id]['waiting_for_input'] = False
                        
                        return True, "Input sent successfully"
                    else:
                        return False, "Process has already completed"
                else:
                    # Regular subprocess or Windows PTY
                    process = proc_info
                    if hasattr(process, 'poll') and process.poll() is None:  # Process is still running
                        if hasattr(process, 'stdin') and process.stdin:
                            process.stdin.write(input_text + '\n')
                            process.stdin.flush()
                        elif hasattr(process, 'write'):  # Windows PTY
                            process.write(input_text + '\n')
                        
                        # Reset the waiting_for_input flag
                        if process_id in process_outputs:
                            process_outputs[process_id]['waiting_for_input'] = False
                        
                        return True, "Input sent successfully"
                    else:
                        return False, "Process has already completed"
                        
            except Exception as e:
                return False, f"Error sending input: {str(e)}"
        else:
            return False, "Process not found"

executor = StreamingCommandExecutor()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'server': 'Remote Command Server',
        'version': '2.0',
        'streaming': True
    })

@app.route('/execute', methods=['POST'])
def execute_command():
    """Start command execution with streaming"""
    global server_busy
    
    try:
        # Check if server is already busy
        if server_busy:
            return jsonify({
                'success': False,
                'error': 'Server is busy executing another command. Please wait or stop the current command first.',
                'busy': True
            }), 409  # Conflict status code
        
        data = request.get_json()
        if not data or 'command' not in data:
            return jsonify({'error': 'No command provided'}), 400
        
        command = data['command']
        process_id = str(uuid.uuid4())
        
        # Start command execution
        success, result = executor.execute_command_streaming(command, process_id)
        
        if success:
            server_busy = True  # Mark server as busy
            return jsonify({
                'success': True,
                'process_id': result,
                'command': command,
                'message': 'Command started, use /stream endpoint to get output'
            })
        else:
            return jsonify({
                'success': False,
                'error': result
            })
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

# WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print(f"Client disconnected: {request.sid}")
    # Clean up any process associations
    for process_id in list(websocket_clients.keys()):
        if websocket_clients[process_id] == request.sid:
            del websocket_clients[process_id]
            break

@socketio.on('start_streaming')
def handle_start_streaming(data):
    """Start streaming output for a process"""
    process_id = data.get('process_id')
    if not process_id:
        emit('error', {'message': 'Process ID is required'})
        return
    
    if process_id not in process_outputs:
        emit('error', {'message': 'Process not found'})
        return
    
    # Associate this client with the process
    websocket_clients[process_id] = request.sid
    
    # Send start event
    emit('stream_data', {'type': 'start', 'process_id': process_id})
    
    # Start background task to stream output
    socketio.start_background_task(stream_process_output, process_id, request.sid)

def stream_process_output(process_id, client_sid):
    """Background task to stream process output via WebSocket"""
    if process_id not in process_outputs:
        socketio.emit('stream_data', {'type': 'error', 'content': 'Process not found'}, room=client_sid)
        return
    
    output_info = process_outputs[process_id]
    output_queue = output_info['queue']
    last_heartbeat = time.time()
    
    while True:
        try:
            # Use very short timeout for immediate streaming
            msg_type, content = output_queue.get(timeout=0.1)
            
            if msg_type == 'output':
                socketio.emit('stream_data', {'type': 'output', 'content': content}, room=client_sid)
                last_heartbeat = time.time()
            elif msg_type == 'complete':
                socketio.emit('stream_data', {'type': 'complete', 'exit_code': content}, room=client_sid)
                break
            elif msg_type == 'error':
                socketio.emit('stream_data', {'type': 'error', 'content': content}, room=client_sid)
                break
            elif msg_type == 'input_request':
                socketio.emit('stream_data', {'type': 'input_request', 'content': content}, room=client_sid)
                last_heartbeat = time.time()
                
        except queue.Empty:
            # Send heartbeat only every 5 seconds to reduce noise
            current_time = time.time()
            if current_time - last_heartbeat > 5:
                socketio.emit('stream_data', {'type': 'heartbeat'}, room=client_sid)
                last_heartbeat = current_time
            
            # Check if process completed
            if output_info['complete']:
                socketio.emit('stream_data', {'type': 'complete', 'exit_code': output_info['exit_code']}, room=client_sid)
                break
        except Exception as e:
            socketio.emit('stream_data', {'type': 'error', 'content': str(e)}, room=client_sid)
            break
    
    # Cleanup
    if process_id in process_outputs:
        del process_outputs[process_id]
    if process_id in websocket_clients:
        del websocket_clients[process_id]

@app.route('/poll/<process_id>')
def poll_output(process_id):
    """Polling endpoint for output (fallback for WebSocket)"""
    try:
        if process_id not in process_outputs:
            return jsonify({'success': False, 'error': 'Process not found'})
        
        output_info = process_outputs[process_id]
        
        # Collect all output so far
        all_output = []
        temp_queue = queue.Queue()
        
        # Drain current queue
        while True:
            try:
                msg_type, content = output_info['queue'].get_nowait()
                all_output.append(content)
                temp_queue.put((msg_type, content))
            except queue.Empty:
                break
        
        # Put messages back
        while not temp_queue.empty():
            output_info['queue'].put(temp_queue.get())
        
        response_data = {
            'success': True,
            'output': output_info['full_output'],
            'complete': output_info['complete'],
            'exit_code': output_info.get('exit_code')
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Polling error: {str(e)}'})

@app.route('/stop/<process_id>', methods=['POST'])
def stop_command(process_id):
    """Stop a running command"""
    global server_busy
    
    try:
        success, message = executor.stop_command(process_id)
        
        # Mark as complete in outputs
        if process_id in process_outputs:
            process_outputs[process_id]['complete'] = True
            process_outputs[process_id]['queue'].put(('error', 'Command stopped by user'))
        
        # Mark server as no longer busy
        server_busy = False
        
        return jsonify({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        return jsonify({'error': f'Error stopping command: {str(e)}'}), 500

@app.route('/input/<process_id>', methods=['POST'])
def send_input_to_process(process_id):
    """Send input to a running process"""
    try:
        data = request.get_json()
        if not data or 'input' not in data:
            return jsonify({'error': 'Input text is required'}), 400
        
        input_text = data['input']
        success, message = executor.send_input(process_id, input_text)
        
        if success:
            return jsonify({
                'success': True,
                'message': message
            })
        else:
            return jsonify({'error': message}), 400
            
    except Exception as e:
        return jsonify({'error': f'Error sending input: {str(e)}'}), 500

@app.route('/status', methods=['GET'])
def server_status():
    """Get server status"""
    return jsonify({
        'busy': server_busy,
        'running_processes': list(running_processes.keys()),
        'process_count': len(running_processes)
    })

@app.route('/processes', methods=['GET'])
def list_processes():
    """List running processes"""
    return jsonify({
        'running_processes': list(running_processes.keys()),
        'count': len(running_processes)
    })

@app.route('/system_info', methods=['GET'])
def system_info():
    """Get basic system information"""
    try:
        import platform
        info = {
            'hostname': platform.node(),
            'system': platform.system(),
            'platform': platform.platform(),
            'python_version': platform.python_version(),
            'working_directory': os.getcwd()
        }
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': f'Error getting system info: {str(e)}'}), 500

if __name__ == '__main__':
    print("=" * 50)
    print("Remote Command Server Starting (HTTPS/WSS Edition)...")
    print("=" * 50)
    
    # Generate or use existing SSL certificates
    try:
        cert_file, key_file = generate_self_signed_cert()
        use_ssl = True
        protocol = "https"
        print(f"SSL enabled with certificate: {cert_file}")
    except Exception as e:
        print(f"SSL certificate generation failed: {e}")
        print("Falling back to HTTP (insecure)")
        use_ssl = False
        protocol = "http"
    
    print(f"Server will run on: {protocol}://0.0.0.0:5000")
    print("Endpoints:")
    print("  GET  /health      - Health check")
    print("  GET  /system_info - System information") 
    print("  POST /execute     - Execute command")
    if use_ssl:
        print("  WebSocket (WSS)  - Real-time command streaming")
    else:
        print("  WebSocket        - Real-time command streaming")
    print("  POST /stop/<id>   - Stop running command")
    print("  GET  /processes   - List running processes")
    print("=" * 50)
    if use_ssl:
        print("SECURITY INFO: This server uses HTTPS and WSS for secure communication.")
        print("If using self-signed certificates, clients will need to accept the certificate.")
    else:
        print("SECURITY WARNING: This server uses HTTP (unencrypted).")
    print("Only run this on trusted networks!")
    print("=" * 50)
    
    # Run server with SocketIO
    try:
        if use_ssl:
            # Try to use SSL
            print("Starting HTTPS server...")
            socketio.run(app, host='0.0.0.0', port=5000, debug=False, 
                        certfile=cert_file, keyfile=key_file)
        else:
            print("Starting HTTP server...")
            socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except Exception as e:
        print(f"Failed to start server with SSL: {e}")
        print("Falling back to HTTP...")
        try:
            socketio.run(app, host='0.0.0.0', port=5000, debug=False)
        except Exception as e2:
            print(f"Failed to start server: {e2}")
            sys.exit(1)