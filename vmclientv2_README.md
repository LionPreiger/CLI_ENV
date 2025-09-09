# VM Client v2 - WebSocket Client

## Overview

`vmclientv2.py` is a new WebSocket client that connects to an external server instead of running a local Flask server. It establishes a persistent connection to the backend endpoint and enables real-time command execution.

## Key Features

- **External Server Connection**: Connects to `217.154.254.231:9000/api/vm/vmid/ws`
- **Real-time Communication**: Uses WebSocket for instant bidirectional communication
- **Command Execution**: Executes system commands with streaming output
- **Auto-reconnection**: Automatically reconnects on connection loss
- **Unique VM ID**: Generates or accepts a unique VM identifier
- **Security**: Maintains safety checks for command execution

## Usage

### Basic Usage
```bash
python vmclientv2.py
```

### With Custom VM ID
```bash
python vmclientv2.py my-custom-vm-id
```

### VM ID Generation
If no VM ID is provided, the client automatically generates one using:
- Hostname
- MAC address (when available)
- UUID fallback

Example generated ID: `DESKTOP-ABC123-aa:bb:cc:dd:ee:ff`

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install websockets>=10.0 asyncio
```

2. Run the setup script:
```bash
python setup.py
```

## Protocol

The client communicates with the server using JSON messages:

### Connection Message
```json
{
    "type": "connection",
    "vm_id": "unique-vm-id",
    "status": "connected",
    "system_info": {
        "hostname": "computer-name",
        "system": "Windows",
        "platform": "Windows-10-...",
        "python_version": "3.x.x",
        "working_directory": "/path/to/current/dir"
    }
}
```

### Command Execution
Server sends:
```json
{
    "type": "command",
    "command": "ls -la",
    "command_id": "unique-command-id"
}
```

Client responds with streaming output:
```json
{
    "type": "command_output",
    "command_id": "unique-command-id",
    "output_type": "output",
    "content": "command output here..."
}
```

### Command Completion
```json
{
    "type": "command_output",
    "command_id": "unique-command-id",
    "output_type": "complete",
    "content": 0
}
```

## Security Features

- **Command Filtering**: Only allows safe commands, blocks dangerous operations
- **Process Isolation**: Each command runs in a separate process
- **Input Validation**: Validates all incoming messages
- **Safe Command List**: Maintains a whitelist of allowed commands

## Error Handling

- **Connection Errors**: Automatic reconnection with exponential backoff
- **Command Errors**: Proper error reporting to server
- **Process Management**: Clean process termination and resource cleanup

## Differences from Original VM_client.py

| Feature | VM_client.py | vmclientv2.py |
|---------|--------------|---------------|
| Architecture | Flask server | WebSocket client |
| Connection | Incoming connections | Outgoing connection |
| Protocol | HTTP/HTTPS + WebSocket | Pure WebSocket |
| SSL/TLS | Self-signed certificates | Handled by server |
| Usage | Server waiting for clients | Client connecting to server |

## Troubleshooting

### Connection Issues
1. Check network connectivity to `217.154.254.231:9000`
2. Verify the server is running and accepting connections
3. Check firewall settings

### Command Execution Issues
1. Ensure commands are in the allowed list
2. Check system permissions for the command
3. Verify working directory access

### Reconnection Problems
1. Check network stability
2. Verify server availability
3. Review client logs for specific errors

## Configuration

The client can be configured by modifying these variables in the script:

```python
SERVER_URL = "217.154.254.231:9000"
max_reconnect_attempts = 5
reconnect_delay = 5  # seconds
```

## Logging

The client uses Python's logging module with INFO level by default. To see more detailed logs, modify the logging level:

```python
logging.basicConfig(level=logging.DEBUG)
```
