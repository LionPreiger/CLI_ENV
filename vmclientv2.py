#!/usr/bin/env python3
"""
VM Client v2 - WebSocket Client that connects to external server
Connects to: 217.154.254.231:9000/api/vm/vmid/ws
Requirements: pip install websockets asyncio
"""

import asyncio
import websockets
import json
import subprocess
import platform
import sys
import os
import threading
import time
import signal
import uuid
import queue
import tempfile
from typing import Optional, Dict, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StreamingCommandExecutor:
    """Enhanced command executor with streaming support"""
    
    def __init__(self):
        """Initializes the StreamingCommandExecutor.

        This sets up the list of allowed commands for security and initializes
        dictionaries to track running processes and their outputs.
        """
        self.allowed_commands = [
            'python', 'python3', 'pip', 'pip3', 'dir', 'ls', 'echo', 'whoami', 'date', 
            'ipconfig', 'ifconfig', 'ping', 'curl', 'wget', 'git', 'cat', 'head', 'tail',
            'find', 'grep', 'sort', 'uniq', 'wc', 'ps', 'top', 'df', 'du', 'free',
            'sudo', 'su', 'ssh', 'read', 'passwd', 'apt', 'yum', 'npm', 'node'
        ]
        self.running_processes: Dict[str, Any] = {}
        self.process_outputs: Dict[str, Dict] = {}
    
    def is_safe_command(self, command: str) -> bool:
        """Checks if a command is safe to execute.

        Performs a basic security check to prevent execution of dangerous commands.

        Args:
            command (str): The command string to check.

        Returns:
            bool: True if the command is considered safe, False otherwise.
        """
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False
        
        base_cmd = cmd_parts[0].lower()
        
        # Block dangerous commands
        dangerous = ['rm', 'del', 'format', 'shutdown', 'reboot', 'kill', 'killall', 'pkill']
        if any(danger in base_cmd for danger in dangerous):
            return False
            
        return True
    
    def execute_command_streaming(self, command: str, process_id: str, output_callback=None):
        """Executes a command and streams its output in a separate thread.

        It handles both PTY-based execution for interactive commands on Linux/macOS
        and standard subprocess for other cases.

        Args:
            command (str): The command to execute.
            process_id (str): A unique ID for tracking the process.
            output_callback (callable, optional): A callback function to handle
                real-time output. It receives message type and content.
                Defaults to None.

        Returns:
            tuple[bool, str]: A tuple containing a boolean indicating success
            and either the process_id or an error message.
        """
        if not self.is_safe_command(command):
            return False, "Command not allowed for security reasons"

        try:
            # Initialize process output tracking
            output_queue = queue.Queue()
            self.process_outputs[process_id] = {
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

            system = platform.system().lower()
            
            # Try PTY approach for Linux/WSL (much better for interactive commands)
            if system in ('linux', 'darwin') or 'microsoft' in platform.release().lower():
                try:
                    import pty
                    import select
                    import shlex
                    import fcntl
                    import termios
                    
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
                    self.running_processes[process_id] = {'process': process, 'master_fd': master_fd, 'slave_fd': slave_fd}
                    
                    # Use PTY-based output reading (much better for interactive commands)
                    def read_output_pty():
                        full_output = ''
                        logger.info(f"Started PTY output reading thread for process {process_id}")
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
                                        
                                        # Call the output callback if provided
                                        if output_callback:
                                            output_callback('output', decoded)
                                        
                                        self.process_outputs[process_id]['last_output_time'] = time.time()
                                        self.process_outputs[process_id]['full_output'] = full_output
                                        
                                        # Enhanced detection for password prompts and input requests
                                        decoded_lower = decoded.lower()
                                        if any(prompt in decoded_lower for prompt in [
                                            '[sudo] password for', 'password:', 'password for',
                                            'enter password', 'sudo password', ': ', 'login:',
                                            'username:', 'passphrase:', 'pin:'
                                        ]) or decoded.endswith(': ') or decoded.endswith('$ '):
                                            if not self.process_outputs[process_id].get('waiting_for_input', False):
                                                self.process_outputs[process_id]['waiting_for_input'] = True
                                                logger.info(f"PTY detected input request for process {process_id}: '{decoded.strip()}'")
                                                if output_callback:
                                                    output_callback('input_request', decoded.strip())
                                                    
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
                                            if output_callback:
                                                output_callback('output', decoded)
                                    except OSError:
                                        pass
                                    break
                                
                                # Small sleep to prevent excessive CPU usage
                                time.sleep(0.001)
                                
                            exit_code = process.wait()
                            logger.info(f"PTY Process {process_id} finished with exit code: {exit_code}")
                            logger.info(f"PTY Full output for process {process_id}: '{full_output}'")
                            
                            self.process_outputs[process_id]['exit_code'] = exit_code
                            self.process_outputs[process_id]['complete'] = True
                            self.process_outputs[process_id]['full_output'] = full_output
                            
                            if output_callback:
                                logger.info(f"PTY Calling output_callback with completion for process {process_id}")
                                output_callback('complete', exit_code)
                                
                        except Exception as e:
                            logger.error(f"PTY Error in output reading: {e}")
                            self.process_outputs[process_id]['complete'] = True
                            if output_callback:
                                output_callback('error', str(e))
                        finally:
                            if process_id in self.running_processes:
                                del self.running_processes[process_id]
                            try:
                                os.close(master_fd)
                                os.close(slave_fd)
                            except:
                                pass

                    thread = threading.Thread(target=read_output_pty, daemon=True)
                    thread.start()
                    return True, process_id
                    
                except ImportError as e:
                    logger.warning(f"PTY not available ({e}), falling back to subprocess")
                except Exception as e:
                    logger.warning(f"PTY setup failed ({e}), falling back to subprocess")

            # Fallback: regular subprocess
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
            self.running_processes[process_id] = process

            def read_output():
                full_output = ''
                logger.info(f"Started output reading thread for process {process_id}")
                try:
                    while True:
                        # Read small chunks for immediate streaming
                        data = process.stdout.read(256)
                        if not data:
                            poll_result = process.poll()
                            if poll_result is not None:
                                logger.info(f"Process {process_id} completed with exit code: {poll_result}")
                                break
                            # Check if process might be waiting for input (no output for a while)
                            current_time = time.time()
                            last_output_time = self.process_outputs[process_id].get('last_output_time', current_time)
                            time_since_output = current_time - last_output_time
                            
                            # If no output for 2+ seconds and process is still running, check for input prompts
                            if (time_since_output > 2.0 and 
                                not self.process_outputs[process_id].get('waiting_for_input', False) and
                                full_output.strip()):
                                
                                logger.info(f"Process {process_id} no output for {time_since_output:.1f}s, checking for hidden input prompt...")
                                
                                # Check if the current output looks like it might be waiting for input
                                output_lower = full_output.lower()
                                looks_like_prompt = (
                                    'password' in output_lower or
                                    'sudo' in output_lower or
                                    full_output.strip().endswith(':') or
                                    'enter' in output_lower
                                )
                                
                                if looks_like_prompt:
                                    logger.info(f"Detected potential input prompt via timeout: '{full_output.strip()}'")
                                    self.process_outputs[process_id]['waiting_for_input'] = True
                                    output_queue.put(('input_request', full_output.strip()))
                                    if output_callback:
                                        output_callback('input_request', full_output.strip())
                            
                            # Give the process a bit more time to complete after input
                            time.sleep(0.05)  # Slightly longer sleep when no data
                            continue
                            
                        decoded = data.decode('utf-8', errors='replace')
                        full_output += decoded
                        output_queue.put(('output', decoded))
                        
                        # Call the output callback if provided
                        if output_callback:
                            output_callback('output', decoded)
                        
                        self.process_outputs[process_id]['last_output_time'] = time.time()
                        self.process_outputs[process_id]['full_output'] = full_output
                        
                        # Log all output for debugging
                        logger.info(f"Process {process_id} output chunk: '{decoded}' (repr: {repr(decoded)})")
                        logger.info(f"Process {process_id} full output so far: '{full_output}' (repr: {repr(full_output)})")
                        
                        # Enhanced detection for interactive prompts and input requests
                        decoded_lower = decoded.lower()
                        decoded_stripped = decoded.strip()
                        
                        # More comprehensive input detection patterns
                        input_patterns = [
                            '[sudo] password for', 'password:', 'password for',
                            'enter password', 'sudo password', 'login:', 'username:',
                            'passphrase:', 'pin:', 'enter your name:', 'enter your',
                            'please enter', 'input required', 'type your', 'what is your',
                            'password for lion7:', 'password for user:', 'sudo:', '[sudo]'
                        ]
                        
                        # Also check the accumulated output for sudo prompts that might be split across reads
                        full_output_lower = full_output.lower()
                        
                        # Check various conditions for input requests
                        is_input_request = (
                            any(pattern in decoded_lower for pattern in input_patterns) or
                            any(pattern in full_output_lower for pattern in ['[sudo] password for', 'password for']) or
                            decoded_stripped.endswith(': ') or
                            decoded_stripped.endswith('$ ') or
                            full_output.strip().endswith(': ') or  # Check full output too
                            (': ' in decoded_stripped and len(decoded_stripped) < 100) or  # Short prompts with ": "
                            ('input(' in decoded_lower and 'python' in command.lower())  # Python input() calls
                        )
                        
                        if is_input_request and not self.process_outputs[process_id].get('waiting_for_input', False):
                            self.process_outputs[process_id]['waiting_for_input'] = True
                            
                            # For sudo prompts, use the full accumulated output as the prompt
                            prompt_text = decoded_stripped
                            if '[sudo] password for' in full_output_lower or 'password for' in full_output_lower:
                                # Extract the sudo prompt from full output
                                lines = full_output.strip().split('\n')
                                for line in lines:
                                    if 'password for' in line.lower() or '[sudo]' in line.lower():
                                        prompt_text = line.strip()
                                        break
                            elif full_output.strip().endswith(':') and not prompt_text:
                                prompt_text = full_output.strip()
                            
                            output_queue.put(('input_request', prompt_text))
                            logger.info(f"Detected input request for process {process_id}: '{prompt_text}'")
                            if output_callback:
                                output_callback('input_request', prompt_text)
                        
                    exit_code = process.wait()
                    logger.info(f"Process {process_id} finished with exit code: {exit_code}")
                    logger.info(f"Full output for process {process_id}: '{full_output}'")
                    
                    self.process_outputs[process_id]['exit_code'] = exit_code
                    self.process_outputs[process_id]['complete'] = True
                    self.process_outputs[process_id]['full_output'] = full_output
                    output_queue.put(('complete', exit_code))
                    
                    if output_callback:
                        logger.info(f"Calling output_callback with completion for process {process_id}")
                        output_callback('complete', exit_code)
                        
                except Exception as e:
                    output_queue.put(('error', str(e)))
                    self.process_outputs[process_id]['complete'] = True
                    if output_callback:
                        output_callback('error', str(e))
                finally:
                    if process_id in self.running_processes:
                        del self.running_processes[process_id]

            thread = threading.Thread(target=read_output, daemon=True)
            thread.start()
            return True, process_id

        except Exception as e:
            return False, f"Error starting command: {str(e)}"
    
    def stop_command(self, process_id: str):
        """Stops a running command.

        Terminates the process with the given process_id. It first tries to
        terminate gracefully, then kills it if necessary.

        Args:
            process_id (str): The ID of the process to stop.

        Returns:
            tuple[bool, str]: A tuple containing a boolean indicating success
            and a confirmation or error message.
        """
        if process_id in self.running_processes:
            try:
                process = self.running_processes[process_id]
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
    
    def send_input(self, process_id: str, input_text: str):
        """Sends input to a running process.

        This is used to provide input to commands that are waiting for it,
        such as password prompts or interactive scripts.

        Args:
            process_id (str): The ID of the process to send input to.
            input_text (str): The text to send to the process's stdin.

        Returns:
            tuple[bool, str]: A tuple containing a boolean indicating success
            and a confirmation or error message.
        """
        logger.info(f"Attempting to send input '{input_text}' to process {process_id}")
        
        if process_id in self.running_processes:
            try:
                proc_info = self.running_processes[process_id]
                logger.info(f"Found process {process_id}, checking if still running...")
                
                # Handle PTY processes (dict format)
                if isinstance(proc_info, dict):
                    process = proc_info['process']
                    master_fd = proc_info.get('master_fd')
                    
                    if process.poll() is None:  # Process is still running
                        logger.info(f"PTY Process {process_id} is still running, sending input...")
                        
                        # For PTY, write to master_fd
                        if master_fd:
                            input_bytes = (input_text + '\n').encode('utf-8')
                            os.write(master_fd, input_bytes)
                            logger.info(f"Successfully wrote input to PTY process {process_id}: '{input_text}'")
                        else:
                            # Fallback to stdin
                            if hasattr(process, 'stdin') and process.stdin:
                                process.stdin.write((input_text + '\n').encode('utf-8'))
                                process.stdin.flush()
                                logger.info(f"Successfully wrote input to PTY stdin process {process_id}: '{input_text}'")
                            else:
                                logger.error(f"PTY Process {process_id} has no master_fd or stdin")
                                return False, "Process master_fd/stdin not available"
                        
                        # Reset the waiting_for_input flag
                        if process_id in self.process_outputs:
                            self.process_outputs[process_id]['waiting_for_input'] = False
                            logger.info(f"Reset waiting_for_input flag for PTY process {process_id}")
                        
                        return True, "Input sent successfully"
                    else:
                        poll_result = process.poll()
                        logger.error(f"PTY Process {process_id} has already completed with exit code: {poll_result}")
                        return False, f"Process has already completed (exit code: {poll_result})"
                else:
                    # Handle regular subprocess
                    process = proc_info
                    if hasattr(process, 'poll') and process.poll() is None:  # Process is still running
                        logger.info(f"Regular Process {process_id} is still running, sending input...")
                        
                        if hasattr(process, 'stdin') and process.stdin:
                            input_with_newline = (input_text + '\n').encode('utf-8')
                            process.stdin.write(input_with_newline)
                            process.stdin.flush()
                            logger.info(f"Successfully wrote input to regular process {process_id}: '{input_text}'")
                        else:
                            logger.error(f"Regular Process {process_id} has no stdin or stdin is None")
                            return False, "Process stdin not available"
                        
                        # Reset the waiting_for_input flag
                        if process_id in self.process_outputs:
                            self.process_outputs[process_id]['waiting_for_input'] = False
                            logger.info(f"Reset waiting_for_input flag for regular process {process_id}")
                        
                        return True, "Input sent successfully"
                    else:
                        poll_result = process.poll() if hasattr(process, 'poll') else "unknown"
                        logger.error(f"Regular Process {process_id} has already completed with exit code: {poll_result}")
                        return False, f"Process has already completed (exit code: {poll_result})"
                        
            except Exception as e:
                logger.error(f"Error sending input to process {process_id}: {str(e)}")
                return False, f"Error sending input: {str(e)}"
        else:
            logger.error(f"Process {process_id} not found in running processes: {list(self.running_processes.keys())}")
            return False, "Process not found"


class VMWebSocketClient:
    """WebSocket client that connects to external server"""
    
    def __init__(self, server_url: str, vm_id: str):
        """Initializes the VMWebSocketClient.

        Args:
            server_url (str): The base URL of the WebSocket server.
            vm_id (str): The unique identifier for this VM client.
        """
        self.server_url = server_url
        self.vm_id = vm_id
        self.websocket = None
        self.executor = StreamingCommandExecutor()
        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5  # seconds
        self.start_time = time.time()  # Track when client started
        self.message_queue = None  # Will be initialized when event loop is available
        self.active_requests = {}  # Track active request_ids for command completion
        self.last_input_request_command = None  # Track the last command that requested input
        
    async def connect(self):
        """Connects to the WebSocket server and sends an initial status message.

        It constructs the full WebSocket URL, establishes the connection,
        and sends a connection message with system information.

        Returns:
            bool: True if the connection was successful, False otherwise.
        """
        try:
            # Initialize the message queue when event loop is available
            if self.message_queue is None:
                self.message_queue = asyncio.Queue()
            
            # Construct the full WebSocket URL
            ws_url = f"ws://{self.server_url}/api/vm/{self.vm_id}/ws"
            logger.info(f"Connecting to: {ws_url}")
            
            self.websocket = await websockets.connect(ws_url)
            logger.info(f"Successfully connected to server as VM {self.vm_id}")
            self.running = True
            self.reconnect_attempts = 0
            
            # Send initial connection message
            await self.send_message({
                "type": "connection",
                "vm_id": self.vm_id,
                "message": "VM client connected",
                "metadata": {
                    "status": "connected",
                    "system_info": self.get_system_info(),
                    "timestamp": time.time()
                }
            })
            
            # Send a test message to verify communication
            await asyncio.sleep(1)  # Wait a moment
            await self.send_message({
                "type": "status",
                "vm_id": self.vm_id,
                "message": "VM client ready for commands",
                "metadata": {
                    "capabilities": ["command_execution", "file_operations", "system_info"],
                    "timestamp": time.time()
                }
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
    
    async def disconnect(self):
        """Disconnects from the WebSocket server.

        Sets the running flag to False and closes the WebSocket connection if it's open.
        """
        self.running = False
        if self.websocket:
            await self.websocket.close()
            logger.info("Disconnected from server")
    
    async def send_message(self, message: Dict[str, Any]):
        """Sends a JSON-formatted message to the server.

        Args:
            message (Dict[str, Any]): The message dictionary to send.
        """
        if self.websocket:
            try:
                await self.websocket.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
    
    async def send_response(self, response_data: Dict[str, Any], request_id: str = None):
        """Sends a response message to the server, including the original request_id.

        Args:
            response_data (Dict[str, Any]): The response data to send.
            request_id (str, optional): The ID of the request this is a response to.
                Defaults to None.
        """
        if request_id:
            response_data["request_id"] = request_id
        
        await self.send_message(response_data)
    
    async def handle_message(self, message: str):
        """Handles an incoming message from the server.

        It parses the message, determines its format (new vs. old, JSON vs. plain text),
        and routes it to the appropriate handler.

        Args:
            message (str): The raw message string received from the server.
        """
        try:
            # Try to parse as JSON first
            data = json.loads(message)
            
            # Check if this message has a request_id (requires response)
            request_id = data.get("request_id")
            
            # Handle new message format with message, type/message_type, and metadata
            if "message" in data and ("type" in data or "message_type" in data):
                # Normalize message_type to type for consistent handling
                if "message_type" in data and "type" not in data:
                    data["type"] = data["message_type"]
                await self.handle_new_format_message(data, request_id)
            # Handle old format for backward compatibility
            elif "type" in data or "message_type" in data:
                msg_type = data.get("type", "") or data.get("message_type", "")
                
                if msg_type == "command":
                    await self.handle_command(data, request_id)
                elif msg_type == "stop_command":
                    await self.handle_stop_command(data, request_id)
                elif msg_type == "send_input":
                    await self.handle_send_input(data, request_id)
                elif msg_type == "ping":
                    await self.send_response({"type": "pong", "vm_id": self.vm_id}, request_id)
                else:
                    logger.info(f"Received JSON message: {data}")
                    if request_id:
                        await self.send_response({"type": "ack", "message": "Message received"}, request_id)
            else:
                logger.info(f"Received unknown format: {data}")
                if request_id:
                    await self.send_response({"type": "ack", "message": "Message received"}, request_id)
                
        except json.JSONDecodeError:
            # Handle plain text messages (like server echoes)
            if message.startswith("Server received:"):
                logger.info(f"Server echo: {message}")
            else:
                # Try to parse commands from plain text
                await self.handle_plain_text_message(message)
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def handle_new_format_message(self, data: dict, request_id: str = None):
        """Handles messages conforming to the new {message, type, metadata} format.

        It routes messages to specific handlers based on their `type` field.

        Args:
            data (dict): The parsed JSON data of the message.
            request_id (str, optional): The request_id from the message, if any.
                Defaults to None.
        """
        message_content = data.get("message", "")
        message_type = data.get("type", "")
        metadata = data.get("metadata", {})
        
        logger.info(f"Received {message_type} message: {message_content}")
        
        if message_type == "command":
            # Extract command from message or metadata
            command = message_content
            command_id = metadata.get("command_id", str(uuid.uuid4()))
            
            # Smart detection: if this looks like input for a waiting command, handle as input instead
            if (self.last_input_request_command and 
                self.last_input_request_command in self.executor.running_processes and
                len(command.strip()) < 100 and  # Short input
                not any(cmd in command.lower() for cmd in ['python', 'ls', 'dir', 'echo', 'cd'])):  # Not a typical command
                
                logger.info(f"Auto-detecting '{command}' as input for waiting command {self.last_input_request_command}")
                await self.handle_send_input({
                    "command_id": self.last_input_request_command,
                    "input": command
                }, request_id)
            else:
                await self.handle_command({
                    "command": command,
                    "command_id": command_id
                }, request_id)
            
        elif message_type == "stop_command":
            command_id = metadata.get("command_id", message_content)
            await self.handle_stop_command({
                "command_id": command_id
            }, request_id)
            
        elif message_type == "send_input":
            command_id = metadata.get("command_id", "")
            input_text = message_content
            
            # If no command_id specified, try to use the last command that requested input
            if not command_id and self.last_input_request_command:
                command_id = self.last_input_request_command
                logger.info(f"No command_id specified for input, using last input request command: {command_id}")
            await self.handle_send_input({
                "command_id": command_id,
                "input": input_text
            }, request_id)
            
        elif message_type == "ping":
            await self.send_response({
                "type": "pong",
                "vm_id": self.vm_id,
                "message": "pong",
                "metadata": {"timestamp": time.time()}
            }, request_id)
            
        elif message_type == "status_request":
            # Send status information
            await self.send_status_update(request_id)
            
        elif message_type == "system_info_request":
            # Send system information
            await self.send_response({
                "type": "system_info_response",
                "vm_id": self.vm_id,
                "message": "System information",
                "metadata": {
                    "system_info": self.get_system_info(),
                    "running_processes": list(self.executor.running_processes.keys())
                }
            }, request_id)
            
        else:
            # Handle other message types
            logger.info(f"Received {message_type}: {message_content}")
            if metadata:
                logger.info(f"Metadata: {metadata}")
            
            # Send acknowledgment if request_id is provided
            if request_id:
                await self.send_response({
                    "type": "ack",
                    "message": f"Received {message_type} message",
                    "metadata": {"original_type": message_type}
                }, request_id)
    
    async def send_status_update(self, request_id: str = None):
        """Sends a detailed status update to the server.

        This includes VM status, number of active processes, system info, and uptime.

        Args:
            request_id (str, optional): The request_id if this is a response to a
                status request. Defaults to None.
        """
        response_data = {
            "type": "status_response", 
            "vm_id": self.vm_id,
            "message": "VM status update",
            "metadata": {
                "status": "running",
                "active_processes": len(self.executor.running_processes),
                "system_info": self.get_system_info(),
                "uptime": time.time() - getattr(self, 'start_time', time.time())
            }
        }
        
        if request_id:
            await self.send_response(response_data, request_id)
        else:
            await self.send_message(response_data)
    
    async def handle_plain_text_message(self, message: str):
        """Handles plain text messages that might be simple commands.

        This provides backward compatibility for simple command execution formats
        like "EXECUTE: command".

        Args:
            message (str): The plain text message from the server.
        """
        logger.info(f"Received plain text: {message}")
        
        # Check if it's a command in plain text format
        if message.startswith("EXECUTE:"):
            command = message[8:].strip()
            command_id = str(uuid.uuid4())
            await self.handle_command({
                "command": command,
                "command_id": command_id
            })
        elif message.startswith("STOP:"):
            command_id = message[5:].strip()
            await self.handle_stop_command({
                "command_id": command_id
            })
        else:
            # Just log other plain text messages
            logger.info(f"Plain text message from server: {message}")
    
    async def handle_command(self, data: Dict[str, Any], request_id: str = None):
        """Handles a command execution request.

        It initiates the command execution via the StreamingCommandExecutor and
        sets up a callback to handle the output.

        Args:
            data (Dict[str, Any]): The command request data, containing the command
                and a command_id.
            request_id (str, optional): The request_id for the entire interaction.
                Defaults to None.
        """
        command = data.get("command", "")
        command_id = data.get("command_id", str(uuid.uuid4()))
        
        if not command:
            await self.send_response({
                "type": "error",
                "vm_id": self.vm_id,
                "message": "No command provided",
                "metadata": {
                    "command_id": command_id,
                    "error": "missing_command",
                    "timestamp": time.time()
                }
            }, request_id)
            return
        
        logger.info(f"Executing command: {command}")
        logger.info(f"Command ID: {command_id}, Request ID: {request_id}")
        
        # Store the request_id for this command if provided
        if request_id:
            self.active_requests[command_id] = {
                'request_id': request_id,
                'full_output': '',
                'start_time': time.time(),
                'previous_output_length': 0  # Track incremental output
            }
        
        def output_callback(msg_type, content):
            """Callback to collect command output"""
            try:
                # If this command has a request_id, collect the output
                if command_id in self.active_requests:
                    if msg_type == "output":
                        # Accumulate output
                        self.active_requests[command_id]['full_output'] += str(content)
                    elif msg_type == "input_request":
                        # Track this as the last command that requested input
                        self.last_input_request_command = command_id
                        
                        # Store the prompt but don't send immediate response
                        # Instead, send the input prompt as the command response
                        request_info = self.active_requests[command_id]
                        
                        # Store the output up to this point (before first input only)
                        current_output = request_info['full_output']
                        if not request_info.get('output_before_input'):
                            # Only store on first input request, not subsequent ones
                            request_info['output_before_input'] = current_output
                            # Initialize previous_output_length to track incremental output from now on
                            request_info['previous_output_length'] = len(current_output)
                            logger.info(f"Stored output before FIRST input for {command_id}: '{current_output}'")
                        
                        input_prompt_response = {
                            "type": "command_awaiting_input",
                            "vm_id": self.vm_id,
                            "message": str(content).strip(),  # Send the prompt as the message
                            "metadata": {
                                "command_id": command_id,
                                "command": command,
                                "prompt": str(content).strip(),
                                "waiting_for_input": True,
                                "timestamp": time.time()
                            },
                            "request_id": request_info['request_id']
                        }
                        
                        # Send the input prompt as the response to the original command
                        if self.message_queue is not None:
                            try:
                                self.message_queue.put_nowait(input_prompt_response)
                                logger.info(f"Sent input prompt response for command {command_id}: {str(content)}")
                            except asyncio.QueueFull:
                                logger.warning("Message queue full, dropping input prompt response")
                        
                        # Mark as waiting for input
                        self.active_requests[command_id]['waiting_for_input'] = True
                    elif msg_type == "complete":
                        # Handle command completion - always send completion response
                        request_info = self.active_requests[command_id]
                        
                        # Extract clean output for multi-input commands
                        full_output = request_info['full_output']
                        clean_output = full_output
                        
                        # For multi-input commands, extract only the final output
                        if request_info.get('output_before_input'):
                            output_before_input = request_info['output_before_input']
                            if full_output.startswith(output_before_input):
                                # Remove the part that was before input
                                clean_output = full_output[len(output_before_input):].strip()
                                logger.info(f"Multi-input extraction for {command_id}: '{clean_output}'")
                        
                        completion_response = {
                            "type": "command_completed",
                            "vm_id": self.vm_id,
                            "message": clean_output,  # Send clean output as message
                            "metadata": {
                                "command_id": command_id,
                                "command": command,
                                "exit_code": content,
                                "execution_time": time.time() - request_info['start_time'],
                                "full_output": full_output,  # Keep full output for reference
                                "multi_input": bool(request_info.get('output_before_input')),
                                "timestamp": time.time()
                            },
                            "request_id": request_info['request_id']
                        }
                        
                        # Send final response
                        if self.message_queue is not None:
                            try:
                                self.message_queue.put_nowait(completion_response)
                                logger.info(f"Queued completion response for command {command_id}")
                            except asyncio.QueueFull:
                                logger.warning("Message queue full, dropping completion response")
                        else:
                            logger.error("Message queue is None, cannot send completion response")
                        
                        # Clean up the active request
                        del self.active_requests[command_id]
                        
                        # Clear input request tracking if this was the waiting command
                        if self.last_input_request_command == command_id:
                            self.last_input_request_command = None
                    elif msg_type == "error":
                        # Command failed - send error response
                        if command_id in self.active_requests:
                            request_info = self.active_requests[command_id]
                            error_response = {
                                "type": "command_error",
                                "vm_id": self.vm_id,
                                "message": f"Command failed: {str(content)}",
                                "metadata": {
                                    "command_id": command_id,
                                    "command": command,
                                    "error": str(content),
                                    "output": request_info['full_output'],
                                    "timestamp": time.time()
                                },
                                "request_id": request_info['request_id']
                            }
                            
                            if self.message_queue is not None:
                                try:
                                    self.message_queue.put_nowait(error_response)
                                except asyncio.QueueFull:
                                    logger.warning("Message queue full, dropping error response")
                            
                            # Clean up the active request
                            del self.active_requests[command_id]
                            
                            # Clear input request tracking if this was the waiting command
                            if self.last_input_request_command == command_id:
                                self.last_input_request_command = None
                else:
                    # No request_id - just log the output (legacy behavior)
                    logger.debug(f"Output ({msg_type}): {str(content)[:100]}...")
                    
            except Exception as e:
                logger.error(f"Error in output callback: {e}")
        
        success, result = self.executor.execute_command_streaming(
            command, command_id, output_callback
        )
        
        if success:
            # Only send started confirmation if no request_id (immediate response)
            # If request_id exists, we'll send the final response when command completes
            if not request_id:
                await self.send_message({
                    "type": "command_started",
                    "vm_id": self.vm_id,
                    "message": f"Command started: {command}",
                    "metadata": {
                        "command_id": result,
                        "command": command,
                        "timestamp": time.time()
                    }
                })
            else:
                # Just log that we started the command
                logger.info(f"Command started with request_id {request_id}: {command}")
        else:
            await self.send_response({
                "type": "error",
                "vm_id": self.vm_id,
                "message": f"Failed to start command: {result}",
                "metadata": {
                    "command_id": command_id,
                    "error": result,
                    "timestamp": time.time()
                }
            }, request_id)
    
    async def handle_stop_command(self, data: Dict[str, Any], request_id: str = None):
        """Handles a request to stop a running command.

        Args:
            data (Dict[str, Any]): The request data, containing the command_id to stop.
            request_id (str, optional): The request_id for the response. Defaults to None.
        """
        command_id = data.get("command_id", "")
        
        if not command_id:
            await self.send_response({
                "type": "error",
                "vm_id": self.vm_id,
                "message": "No command ID provided for stop request",
                "metadata": {
                    "error": "missing_command_id",
                    "timestamp": time.time()
                }
            }, request_id)
            return
        
        success, message = self.executor.stop_command(command_id)
        
        await self.send_response({
            "type": "command_stopped",
            "vm_id": self.vm_id,
            "message": message,
            "metadata": {
                "command_id": command_id,
                "success": success,
                "timestamp": time.time()
            }
        }, request_id)
    
    async def handle_send_input(self, data: Dict[str, Any], request_id: str = None):
        """Handles a request to send input to a running process.

        After sending the input, it waits for the process to either request more
        input or complete, then sends an appropriate response.

        Args:
            data (Dict[str, Any]): The request data, containing the command_id and
                the input text.
            request_id (str, optional): The request_id for the response. Defaults to None.
        """
        command_id = data.get("command_id", "")
        input_text = data.get("input", "")
        
        logger.info(f"Received input request - command_id: '{command_id}', input: '{input_text}'")
        logger.info(f"Active processes: {list(self.executor.running_processes.keys())}")
        
        if not command_id or not input_text:
            await self.send_response({
                "type": "error",
                "vm_id": self.vm_id,
                "message": "Command ID and input text are required",
                "metadata": {
                    "error": "missing_parameters",
                    "provided_command_id": command_id,
                    "provided_input": input_text,
                    "timestamp": time.time()
                }
            }, request_id)
            return
        
        # Store the current output length BEFORE sending input to track incremental output
        output_length_before_input = 0
        if command_id in self.executor.process_outputs:
            current_full_output = self.executor.process_outputs[command_id].get('full_output', '')
            output_length_before_input = len(current_full_output)
            logger.info(f"Storing output length before sending input '{input_text}': {output_length_before_input}")
        
        success, message = self.executor.send_input(command_id, input_text)
        logger.info(f"Input send result - success: {success}, message: {message}")
        
        if success:
            # Wait for the process to either request more input or complete
            logger.info(f"Input sent to process {command_id}, waiting for next prompt or completion...")
            
            # Wait for next input request or completion
            timeout = 10  # 10 seconds timeout
            start_time = time.time()
            next_response = None
            
            # Reset flags to allow detection
            if self.last_input_request_command == command_id:
                self.last_input_request_command = None
            if command_id in self.active_requests:
                self.active_requests[command_id]['waiting_for_input'] = False
            
            # Wait for either next input request or completion
            while (time.time() - start_time) < timeout:
                await asyncio.sleep(0.1)  # Check every 100ms
                
                # Check if process completed
                if command_id in self.executor.process_outputs:
                    process_output = self.executor.process_outputs[command_id]
                    if process_output.get('complete', False):
                        # Process completed - return only the final incremental output
                        full_output = process_output.get('full_output', '')
                        exit_code = process_output.get('exit_code', 0)
                        
                        # Get only the new output since we sent the input
                        logger.info(f"Output length before input: {output_length_before_input}, Full output length: {len(full_output)}")
                        
                        # Extract only the new output (final result)
                        final_output = full_output[output_length_before_input:].strip()
                        
                        # Clean up any extra whitespace and control characters
                        final_output = final_output.replace('\r\n', '\n').replace('\r', '\n')
                        
                        # For final output, join multiple lines with spaces for cleaner result
                        if '\n' in final_output:
                            final_output = ' '.join(line.strip() for line in final_output.split('\n') if line.strip())
                        
                        # If final_output is empty or just whitespace, it means no new output after last input
                        if not final_output:
                            final_output = "Command completed"
                        
                        logger.info(f"Final incremental output for {command_id}: '{final_output}'")
                        
                        next_response = {
                            "type": "command_completed",
                            "vm_id": self.vm_id,
                            "message": final_output,
                            "metadata": {
                                "command_id": command_id,
                                "exit_code": exit_code,
                                "input_provided": input_text,
                                "final_output": final_output,
                                "full_output": full_output,
                                "output_length_before_input": output_length_before_input,
                                "timestamp": time.time()
                            }
                        }
                        break
                
                # Check if new input request was detected
                if (self.last_input_request_command == command_id or 
                    (command_id in self.executor.process_outputs and 
                     self.executor.process_outputs[command_id].get('waiting_for_input', False))):
                    
                    # New input prompt detected - extract only the NEW prompt (incremental output)
                    if command_id in self.executor.process_outputs:
                        full_output = self.executor.process_outputs[command_id].get('full_output', '')
                        
                        # Extract only the new output since we sent the input
                        new_output = full_output[output_length_before_input:].strip()
                        
                        # Clean up any extra whitespace and control characters
                        new_output = new_output.replace('\r\n', '\n').replace('\r', '\n')
                        
                        logger.info(f"New output since sending input for {command_id}: '{new_output}'")
                        
                        # Extract the prompt from the new output
                        lines = new_output.split('\n')
                        prompt = ""
                        for line in reversed(lines):
                            line = line.strip()
                            if line and (line.endswith(':') or 'enter' in line.lower() or 'input' in line.lower()):
                                prompt = line
                                break
                        
                        if not prompt and lines:
                            prompt = lines[-1].strip()
                        
                        next_response = {
                            "type": "command_awaiting_input",
                            "vm_id": self.vm_id,
                            "message": prompt,
                            "metadata": {
                                "command_id": command_id,
                                "prompt": prompt,
                                "waiting_for_input": True,
                                "previous_input": input_text,
                                "new_output": new_output,
                                "output_length_before_input": output_length_before_input,
                                "timestamp": time.time()
                            }
                        }
                        break
            
            # Send the response (either next prompt or completion)
            if next_response:
                await self.send_response(next_response, request_id)
            else:
                # Timeout - send error
                await self.send_response({
                    "type": "error",
                    "vm_id": self.vm_id,
                    "message": "Timeout waiting for process response after input",
                    "metadata": {
                        "command_id": command_id,
                        "error": "input_response_timeout",
                        "input_provided": input_text,
                        "timestamp": time.time()
                    }
                }, request_id)
            
            # Clean up if process completed
            if next_response and next_response["type"] == "command_completed":
                if command_id in self.executor.process_outputs:
                    del self.executor.process_outputs[command_id]
                if command_id in self.active_requests:
                    del self.active_requests[command_id]
                if self.last_input_request_command == command_id:
                    self.last_input_request_command = None
        else:
            # Input sending failed
            await self.send_response({
                "type": "error",
                "vm_id": self.vm_id,
                "message": f"Failed to send input: {message}",
                "metadata": {
                    "command_id": command_id,
                    "error": "input_send_failed",
                    "input_text": input_text,
                    "timestamp": time.time()
                }
            }, request_id)
    
    def get_system_info(self):
        """Gets basic system information.

        Returns:
            dict: A dictionary containing hostname, system, platform, Python version,
            and current working directory.
        """
        try:
            return {
                'hostname': platform.node(),
                'system': platform.system(),
                'platform': platform.platform(),
                'python_version': platform.python_version(),
                'working_directory': os.getcwd()
            }
        except Exception as e:
            return {'error': f'Error getting system info: {str(e)}'}
    
    async def listen(self):
        """Listens for incoming messages from the server in a loop.

        It also manages background tasks for sending heartbeats and processing
        the message queue.
        """
        try:
            # Start heartbeat task
            heartbeat_task = asyncio.create_task(self.send_heartbeat())
            # Start message processor task
            message_processor_task = asyncio.create_task(self.process_message_queue())
            
            while self.running:
                try:
                    # Use timeout to allow heartbeat to work
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                    await self.handle_message(message)
                except asyncio.TimeoutError:
                    # Timeout is normal, allows heartbeat to continue
                    continue
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Connection closed by server")
        except Exception as e:
            logger.error(f"Error in listen loop: {e}")
        finally:
            self.running = False
            # Cancel background tasks
            if 'heartbeat_task' in locals():
                heartbeat_task.cancel()
            if 'message_processor_task' in locals():
                message_processor_task.cancel()
    
    async def process_message_queue(self):
        """Processes and sends messages from the internal thread-safe queue.

        This allows other threads (like the command output callback) to safely
        queue messages to be sent on the main asyncio event loop.
        """
        while self.running:
            try:
                # Check if queue is available
                if self.message_queue is None:
                    await asyncio.sleep(1.0)
                    continue
                
                # Get message from queue with timeout
                message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                logger.info(f"Processing queued message: {message.get('type', 'unknown')} - {message.get('message', '')[:100]}")
                await self.send_message(message)
                self.message_queue.task_done()
            except asyncio.TimeoutError:
                # Timeout is normal, just continue
                continue
            except Exception as e:
                logger.error(f"Error processing message queue: {e}")
    
    async def send_heartbeat(self):
        """Sends a periodic heartbeat message to the server to keep the connection alive.
        """
        while self.running:
            try:
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
                if self.running:
                    await self.send_message({
                        "type": "heartbeat",
                        "vm_id": self.vm_id,
                        "message": "VM alive",
                        "metadata": {
                            "timestamp": time.time(),
                            "status": "alive",
                            "active_processes": len(self.executor.running_processes)
                        }
                    })
                    logger.debug("Heartbeat sent")
            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")
                break
    
    async def run_with_reconnect(self):
        """Runs the client and automatically handles reconnection.

        If the connection is lost, it will attempt to reconnect a configured
        number of times with a delay.
        """
        while True:
            try:
                if await self.connect():
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


async def main():
    """Main entry point for the VM client.

    It parses command-line arguments for the VM ID, initializes the client,
    and runs it with reconnection logic.
    """
    print("=" * 50)
    print("VM WebSocket Client v2 Starting...")
    print("=" * 50)
    
    # Configuration
    SERVER_URL = "217.154.254.231:9000"
    
    # Get VM ID from command line or generate one
    if len(sys.argv) > 1:
        vm_id = sys.argv[1]
    else:
        # Generate a unique VM ID based on hostname and MAC address
        import socket
        hostname = socket.gethostname()
        try:
            # Try to get MAC address
            import uuid as uuid_lib
            mac = ':'.join(['{:02x}'.format((uuid_lib.getnode() >> elements) & 0xff) 
                           for elements in range(0,2*6,2)][::-1])
            vm_id = f"{hostname}-{mac}"
        except:
            vm_id = f"{hostname}-{str(uuid.uuid4())[:8]}"
    
    print(f"VM ID: {vm_id}")
    print(f"Connecting to: {SERVER_URL}")
    print("=" * 50)
    
    # Create and run the client
    client = VMWebSocketClient(SERVER_URL, vm_id)
    
    try:
        print("🔗 Connecting to server...")
        await client.run_with_reconnect()
    except KeyboardInterrupt:
        print("\n⏹️  Shutdown requested by user")
        await client.disconnect()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await client.disconnect()
    
    print("✅ VM Client stopped.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
