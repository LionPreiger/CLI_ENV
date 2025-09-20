#!/usr/bin/env python3
"""
VM Client v3 - Connects to external server and streams output to host web UI
"""
import asyncio
import websockets
import json
import time

# --- v2 streaming logic ---
import asyncio
import websockets
import json
import time
import uuid
import logging
import platform
import os
import sys
from typing import Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from threading import Thread

class StreamingCommandExecutor:
    def __init__(self):
        self.allowed_commands = [
            'python', 'python3', 'pip', 'pip3', 'dir', 'ls', 'echo', 'whoami', 'date', 
            'ipconfig', 'ifconfig', 'ping', 'curl', 'wget', 'git', 'cat', 'head', 'tail',
            'find', 'grep', 'sort', 'uniq', 'wc', 'ps', 'top', 'df', 'du', 'free',
            'sudo', 'su', 'ssh', 'read', 'passwd', 'apt', 'yum', 'npm', 'node'
        ]
        self.running_processes = {}
        self.process_outputs = {}

    def is_safe_command(self, command):
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False
        base_cmd = cmd_parts[0].lower()
        dangerous = ['rm', 'del', 'format', 'shutdown', 'reboot', 'kill', 'killall', 'pkill']
        if any(danger in base_cmd for danger in dangerous):
            return False
        return True

    def execute_command_streaming(self, command, process_id, output_callback=None, input_callback=None):
        import queue, threading, subprocess, platform, os, time
        if not self.is_safe_command(command):
            return False, "Command not allowed for security reasons"
        try:
            output_queue = queue.Queue()
            self.process_outputs[process_id] = {
                'queue': output_queue,
                'complete': False,
                'exit_code': None,
                'full_output': '',
                'waiting_for_input': False,
                'last_output_time': time.time(),
                'process': None
            }
            system = platform.system().lower()
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=0,
                universal_newlines=True
            )
            self.running_processes[process_id] = process
            self.process_outputs[process_id]['process'] = process
            def read_output():
                full_output = ''
                try:
                    while True:
                        data = process.stdout.read(1)
                        if not data:
                            poll_result = process.poll()
                            if poll_result is not None:
                                break
                            time.sleep(0.05)
                            continue
                        full_output += data
                        output_queue.put(('output', data))
                        if output_callback:
                            output_callback('output', data)
                        self.process_outputs[process_id]['last_output_time'] = time.time()
                        self.process_outputs[process_id]['full_output'] = full_output
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

    def send_input(self, process_id, input_text):
        # Write input to process stdin
        logger.info(f"Attempting to send input '{input_text}' to process {process_id}")
        logger.info(f"Available processes: {list(self.process_outputs.keys())}")
        
        if process_id in self.process_outputs:
            process = self.process_outputs[process_id].get('process')
            if process and process.stdin:
                try:
                    # Check if process is still running (None means still running)
                    poll_result = process.poll()
                    logger.info(f"Process poll result: {poll_result}")
                    if poll_result is not None:
                        return False, f"Process already exited with code {poll_result}"
                    # Write and flush input with explicit encoding
                    input_line = str(input_text) + '\n'
                    logger.info(f"Writing input line: {repr(input_line)}")
                    process.stdin.write(input_line)
                    process.stdin.flush()
                    # Give a small delay to ensure input is processed
                    import time
                    time.sleep(0.1)
                    self.process_outputs[process_id]['waiting_for_input'] = False
                    logger.info("Input sent successfully")
                    return True, "Input sent"
                except Exception as e:
                    logger.error(f"Error sending input: {str(e)}")
                    return False, f"Error sending input: {str(e)}"
        logger.error(f"Process {process_id} not found or stdin not available")
        return False, "Process not found or stdin not available"

class VMClientV3:
    def __init__(self, server_url: str, host_ws_url: str, vm_id: str):
        self.server_url = server_url
        self.host_ws_url = host_ws_url
        self.vm_id = vm_id
        self.server_ws = None
        self.host_ws = None
        self.executor = StreamingCommandExecutor()
        self.running = False
        self.active_commands = {}

    async def connect_server(self):
        ws_url = f"ws://{self.server_url}/api/vm/{self.vm_id}/ws"
        self.server_ws = await websockets.connect(ws_url)
        logger.info(f"Connected to server: {ws_url}")

    async def connect_host(self):
        self.host_ws = await websockets.connect(self.host_ws_url)
        logger.info(f"Connected to host UI: {self.host_ws_url}")

    async def send_to_host(self, message: Dict[str, Any]):
        if self.host_ws:
            await self.host_ws.send(json.dumps(message))

    async def send_to_server(self, message: Dict[str, Any]):
        if self.server_ws:
            await self.server_ws.send(json.dumps(message))

    async def handle_server_message(self, message: str):
        # Forward all server messages to host UI for streaming
        logger.info(f"Received message from server: {message}")
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            command = None
            command_id = None
            request_id = data.get("request_id")
            logger.info(f"Parsed message type: {msg_type}")
            # Handle input from server
            if msg_type == "send_input" or msg_type == "text":
                command_id = data.get("metadata", {}).get("command_id") or data.get("command_id")
                input_text = data.get("message") or data.get("input")
                logger.info(f"Received input message: command_id={command_id}, input_text={input_text}")
                
                # Send input_sent to host UI FIRST
                await self.send_to_host({
                    "type": "input_sent",
                    "vm_id": self.vm_id,
                    "message": input_text,
                    "timestamp": time.time(),
                    "command_id": command_id
                })
                
                # Then send input to the process
                success, msg = self.executor.send_input(command_id, input_text)
                logger.info(f"Send input result: success={success}, msg={msg}")
                if success:
                    # Send confirmation to server
                    await self.send_to_server({
                        "type": "input_sent",
                        "vm_id": self.vm_id,
                        "message": input_text,
                        "metadata": {
                            "command_id": command_id,
                            "timestamp": time.time()
                        },
                        "request_id": request_id
                    })
                else:
                    await self.send_to_server({
                        "type": "error",
                        "vm_id": self.vm_id,
                        "message": msg,
                        "metadata": {
                            "command_id": command_id,
                            "timestamp": time.time()
                        },
                        "request_id": request_id
                    })
                return
            if msg_type == "command" or ("command" in data):
                command = data.get("message") or data.get("command")
                command_id = data.get("metadata", {}).get("command_id") or str(uuid.uuid4())
            if command:
                await self.send_to_host({
                    "type": "command",
                    "vm_id": self.vm_id,
                    "message": command,
                    "timestamp": time.time(),
                    "command_id": command_id
                })
                logger.info(f"Forwarded command to host UI: {command}")
                loop = asyncio.get_event_loop()
                # Buffer for output processing
                output_buffer = ""
                sent_prompts = set()  # Track sent prompts to avoid duplicates
                
                def output_callback(msg_type, content):
                    nonlocal output_buffer
                    output_buffer += content
                    
                    # Check for complete lines (ending with \n)
                    if '\n' in output_buffer:
                        lines = output_buffer.split('\n')
                        # Process all complete lines except the last (incomplete) one
                        for line in lines[:-1]:
                            if line.strip():  # Only send non-empty lines
                                loop.call_soon_threadsafe(asyncio.create_task, self.send_to_host({
                                    "type": "output",
                                    "vm_id": self.vm_id,
                                    "message": line.strip(),
                                    "timestamp": time.time(),
                                    "command_id": command_id
                                }))
                                # Send to server for response tracking
                                loop.call_soon_threadsafe(asyncio.create_task, self.send_to_server({
                                    "type": "command_response",
                                    "vm_id": self.vm_id,
                                    "message": line + '\n',
                                    "metadata": {
                                        "command_id": command_id,
                                        "response_type": msg_type,
                                        "timestamp": time.time()
                                    },
                                    "request_id": request_id
                                }))
                        # Keep the last incomplete line in buffer
                        output_buffer = lines[-1]
                    
                    # Check for prompts (ends with ':' or '? ') but only if not already sent
                    current_buffer = output_buffer.strip()
                    if (current_buffer.endswith(':') or current_buffer.endswith('? ')) and current_buffer not in sent_prompts and len(current_buffer) > 2:
                        sent_prompts.add(current_buffer)
                        # Send input_request ONLY to host (not as output)
                        loop.call_soon_threadsafe(asyncio.create_task, self.send_to_host({
                            "type": "input_request",
                            "vm_id": self.vm_id,
                            "message": current_buffer,
                            "timestamp": time.time(),
                            "command_id": command_id
                        }))
                        loop.call_soon_threadsafe(asyncio.create_task, self.send_to_server({
                            "type": "input_request",
                            "vm_id": self.vm_id,
                            "message": current_buffer,
                            "metadata": {
                                "command_id": command_id,
                                "timestamp": time.time()
                            },
                            "request_id": request_id
                        }))
                        # Clear the buffer after sending prompt
                        output_buffer = ""
                # When command completes, flush any remaining buffer to host UI and server
                def complete_callback():
                    nonlocal output_buffer
                    if output_buffer.strip():
                        loop.call_soon_threadsafe(asyncio.create_task, self.send_to_host({
                            "type": "output",
                            "vm_id": self.vm_id,
                            "message": output_buffer.strip(),
                            "timestamp": time.time(),
                            "command_id": command_id
                        }))
                        loop.call_soon_threadsafe(asyncio.create_task, self.send_to_server({
                            "type": "command_response",
                            "vm_id": self.vm_id,
                            "message": output_buffer,
                            "metadata": {
                                "command_id": command_id,
                                "response_type": "output",
                                "timestamp": time.time()
                            },
                            "request_id": request_id
                        }))
                        output_buffer = ""
                def input_callback(msg_type, content):
                    # This callback is not needed since we handle prompts in output_callback
                    pass
                
                self.executor.execute_command_streaming(command, command_id, output_callback, input_callback)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON message: {e}")
            logger.error(f"Raw message: {message}")
        except Exception as e:
            logger.error(f"Error handling server message: {e}")
            logger.error(f"Raw message: {message}")

    async def listen(self):
        self.running = True
        logger.info("Starting to listen for messages from server...")
        while self.running:
            try:
                msg = await self.server_ws.recv()
                logger.info(f"Raw message received: {msg}")
                await self.handle_server_message(msg)
            except Exception as e:
                logger.error(f"Error in listen loop: {e}")
                break

    async def run(self):
        await self.connect_server()
        await self.connect_host()
        await self.listen()

if __name__ == "__main__":
    SERVER_URL = "217.154.254.231:9000"
    HOST_WS_URL = "ws://localhost:8765/vm_stream"
    if len(sys.argv) > 1:
        vm_id = sys.argv[1]
    else:
        vm_id_file = "vm_id.txt"
        vm_id = None
        if os.path.exists(vm_id_file):
            with open(vm_id_file, "r") as f:
                vm_id = f.read().strip()
        if not vm_id:
            vm_id = "vm-demo-id"
    client = VMClientV3(SERVER_URL, HOST_WS_URL, vm_id)
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("Shutdown requested by user")
