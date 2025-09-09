# VM Client v2 - Request-Response Pattern

## Overview

The VM client has been updated to support the new backend request-response pattern using `request_id` for tracking messages and responses.

## Key Changes

### 1. Request-Response Pattern
- **Server sends**: Messages with `request_id` for tracking
- **Client responds**: Same `request_id` in response for correlation
- **Backend waits**: For client response before completing API call

### 2. New Message Flow

#### Command Execution:
```
1. Server → VM: {"message": "ls -la", "type": "command", "request_id": "uuid-123"}
2. VM → Server: {"type": "command_started", "request_id": "uuid-123", ...}
3. VM → Server: {"type": "command_output", "metadata": {"output_type": "output"}, ...}
4. VM → Server: {"type": "command_completed", "request_id": "uuid-123", "metadata": {"exit_code": 0}}
```

#### Status Request:
```
1. Server → VM: {"message": "status", "type": "status_request", "request_id": "uuid-456"}
2. VM → Server: {"type": "status_response", "request_id": "uuid-456", ...}
```

### 3. Backend Integration

The backend now uses:
- `websocket.send_json()` - Sends JSON objects directly
- `request_id` tracking - Correlates requests with responses
- `send_to_vm_and_wait_response()` - Waits for VM response with timeout

### 4. Client Features

#### Message Handling:
- Detects `request_id` in incoming messages
- Sends appropriate responses with same `request_id`
- Handles both new format and backward compatibility

#### Command Execution:
- Tracks active commands with `request_id`
- Sends streaming output during execution
- Sends completion response when command finishes
- Includes exit codes and timing information

#### Error Handling:
- Sends error responses with `request_id`
- Includes detailed error metadata
- Handles timeouts and connection issues

## Usage Examples

### Send Command (Server Side):
```python
# POST /api/vm/{vmid}/send
{
    "message": "whoami",
    "message_type": "command",
    "metadata": {"command_id": "cmd-001"},
    "timeout": 30.0
}
```

### Expected Response Flow:
```json
// 1. Command started
{
    "type": "command_started",
    "request_id": "uuid-123",
    "vm_id": "vm-001",
    "message": "Command started: whoami",
    "metadata": {
        "command_id": "cmd-001",
        "command": "whoami",
        "timestamp": 1694123456.789
    }
}

// 2. Command output (streaming)
{
    "type": "command_output",
    "vm_id": "vm-001", 
    "message": "user\n",
    "metadata": {
        "command_id": "cmd-001",
        "output_type": "output",
        "timestamp": 1694123456.790
    }
}

// 3. Command completion (final response)
{
    "type": "command_completed",
    "request_id": "uuid-123",
    "vm_id": "vm-001",
    "message": "Command completed with exit code: 0",
    "metadata": {
        "command_id": "cmd-001",
        "exit_code": 0,
        "timestamp": 1694123456.795
    }
}
```

## Benefits

1. **Reliable Communication**: Server knows when operations complete
2. **Timeout Handling**: Server can timeout if VM doesn't respond
3. **Correlation**: Messages are properly correlated using `request_id`
4. **Error Recovery**: Better error handling and reporting
5. **Scalability**: Supports multiple concurrent operations

## Backward Compatibility

The client still supports:
- Plain text messages
- Old JSON format without `request_id`
- Legacy command execution patterns

## Testing

To test the new pattern:

1. **Start VM Client**: `python vmclientv2.py`
2. **Send Command**: Use POST endpoint with timeout
3. **Monitor Responses**: Check for proper `request_id` correlation
4. **Verify Completion**: Ensure final response is sent

## Configuration

The client automatically:
- Detects `request_id` in messages
- Sends appropriate responses
- Handles streaming output
- Manages command lifecycle

No additional configuration is required for the request-response pattern.
