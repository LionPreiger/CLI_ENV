# VM Client v2 - New Message Format

## Server Message Format

The server now sends messages in this format:
```json
{
    "message": "command content or message",
    "type": "message_type",
    "metadata": {
        "key": "value",
        "additional": "data"
    }
}
```

## Supported Message Types

### 1. Command Execution
**Server sends:**
```json
{
    "message": "ls -la",
    "type": "command", 
    "metadata": {
        "command_id": "unique-id-123"
    }
}
```

**Client responds with:**
```json
{
    "type": "command_started",
    "vm_id": "vm-identifier",
    "message": "Command started: ls -la",
    "metadata": {
        "command_id": "unique-id-123",
        "command": "ls -la",
        "timestamp": 1694123456.789
    }
}
```

**Command output (streaming):**
```json
{
    "type": "command_output",
    "vm_id": "vm-identifier", 
    "message": "total 8\ndrwxr-xr-x 2 user user 4096 Sep  7 22:00 .\n",
    "metadata": {
        "command_id": "unique-id-123",
        "output_type": "output",
        "timestamp": 1694123456.789
    }
}
```

**Command completion:**
```json
{
    "type": "command_output",
    "vm_id": "vm-identifier",
    "message": "0",
    "metadata": {
        "command_id": "unique-id-123",
        "output_type": "complete",
        "timestamp": 1694123456.789
    }
}
```

### 2. Stop Command
**Server sends:**
```json
{
    "message": "unique-id-123",
    "type": "stop_command",
    "metadata": {
        "command_id": "unique-id-123"
    }
}
```

### 3. Send Input to Command
**Server sends:**
```json
{
    "message": "password123",
    "type": "send_input",
    "metadata": {
        "command_id": "unique-id-123"
    }
}
```

### 4. Ping/Health Check
**Server sends:**
```json
{
    "message": "ping",
    "type": "ping",
    "metadata": {}
}
```

**Client responds:**
```json
{
    "type": "pong",
    "vm_id": "vm-identifier",
    "message": "pong",
    "metadata": {
        "timestamp": 1694123456.789
    }
}
```

### 5. Status Request
**Server sends:**
```json
{
    "message": "status",
    "type": "status_request",
    "metadata": {}
}
```

**Client responds:**
```json
{
    "type": "status_response",
    "vm_id": "vm-identifier",
    "message": "VM status update",
    "metadata": {
        "status": "running",
        "active_processes": 2,
        "system_info": {
            "hostname": "DESKTOP-D92R0CO",
            "system": "Linux",
            "platform": "Linux-6.6.87.2-microsoft-standard-WSL2",
            "python_version": "3.12.9",
            "working_directory": "/current/path"
        },
        "uptime": 3600.5
    }
}
```

### 6. System Info Request
**Server sends:**
```json
{
    "message": "get system info",
    "type": "system_info_request",
    "metadata": {}
}
```

## Example Usage from Server

To send a command to the VM, make a POST request to:
```
POST /api/vm/{vmid}/send
```

With payload:
```json
{
    "message": "whoami",
    "message_type": "command",
    "metadata": {
        "command_id": "test-whoami-001"
    }
}
```

## Automatic Messages from Client

### Connection Message
```json
{
    "type": "connection",
    "vm_id": "DESKTOP-D92R0CO-fd:f5:d6:59:66:99",
    "message": "VM client connected",
    "metadata": {
        "status": "connected",
        "system_info": {...},
        "timestamp": 1694123456.789
    }
}
```

### Heartbeat (every 30 seconds)
```json
{
    "type": "heartbeat",
    "vm_id": "DESKTOP-D92R0CO-fd:f5:d6:59:66:99",
    "message": "VM alive",
    "metadata": {
        "timestamp": 1694123456.789,
        "status": "alive",
        "active_processes": 1
    }
}
```

## Error Handling

All errors follow this format:
```json
{
    "type": "error",
    "vm_id": "vm-identifier",
    "message": "Human readable error message",
    "metadata": {
        "error": "error_code_or_details",
        "timestamp": 1694123456.789,
        "context": "additional_context"
    }
}
```
