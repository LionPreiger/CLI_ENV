# VM Client v2 - Final Output Response Pattern

## Overview

The VM client now sends a single final response with complete output instead of streaming individual messages during command execution.

## Message Flow

### Command Execution:
```
1. Server → VM: {"message": "ls -la", "type": "command", "request_id": "uuid-123"}
2. VM executes command and collects ALL output
3. VM → Server: {"type": "command_completed", "request_id": "uuid-123", "message": "complete_output_here", "metadata": {"exit_code": 0}}
```

### Status/Info Requests:
```
1. Server → VM: {"message": "status", "type": "status_request", "request_id": "uuid-456"}
2. VM → Server: {"type": "status_response", "request_id": "uuid-456", ...}
```

## Response Format

### Successful Command:
```json
{
    "type": "command_completed",
    "vm_id": "vm-001",
    "message": "total 8\ndrwxr-xr-x 2 user user 4096 Sep  7 22:00 .\ndrwxr-xr-x 3 user user 4096 Sep  7 21:59 ..\n-rw-r--r-- 1 user user    0 Sep  7 22:00 file.txt\n",
    "metadata": {
        "command_id": "cmd-001",
        "command": "ls -la",
        "exit_code": 0,
        "execution_time": 0.123,
        "timestamp": 1694123456.789
    },
    "request_id": "uuid-123"
}
```

### Failed Command:
```json
{
    "type": "command_error",
    "vm_id": "vm-001", 
    "message": "Command failed: /bin/sh: 1: invalidcommand: not found",
    "metadata": {
        "command_id": "cmd-002",
        "command": "invalidcommand",
        "error": "Command not found",
        "output": "",
        "timestamp": 1694123456.789
    },
    "request_id": "uuid-124"
}
```

## Key Changes

1. **No Streaming**: Command output is collected and sent once when complete
2. **Single Response**: Server receives one final response per request
3. **Complete Output**: Full command output is in the `message` field
4. **Execution Metrics**: Includes execution time and exit code
5. **Error Handling**: Separate response type for command failures

## Benefits

- **Simpler Integration**: Server gets one response to process
- **Complete Context**: Full output available at once
- **Better Performance**: Reduces WebSocket message overhead
- **Reliable Completion**: Clear indication when command finishes
- **Error Distinction**: Separate handling for success vs failure

## Backward Compatibility

- Commands without `request_id` still work (legacy mode)
- Old message formats are still supported
- Non-command messages (ping, status) work as before

## Usage Example

### Server Request:
```python
# POST /api/vm/{vmid}/send
{
    "message": "whoami && pwd && date",
    "message_type": "command",
    "metadata": {"command_id": "multi-cmd-001"},
    "timeout": 30.0
}
```

### VM Response:
```json
{
    "type": "command_completed",
    "vm_id": "desktop-abc123",
    "message": "user\n/home/user\nSat Sep  7 22:30:45 UTC 2025\n",
    "metadata": {
        "command_id": "multi-cmd-001",
        "command": "whoami && pwd && date", 
        "exit_code": 0,
        "execution_time": 0.045,
        "timestamp": 1694123445.123
    },
    "request_id": "uuid-789"
}
```

## Error Scenarios

1. **Command Not Found**: Returns `command_error` with error details
2. **Permission Denied**: Returns `command_error` with security message  
3. **Execution Timeout**: VM internal timeout handling
4. **Invalid Input**: Returns error response for malformed requests

## Implementation Details

- Output is accumulated during command execution
- Final response sent only when command completes or fails
- Request tracking ensures proper cleanup
- Thread-safe message queuing for response delivery
