# WebSocket Architecture v2

## Overview

The new architecture uses an external WebSocket server as a central hub connecting hosts (controllers) and VMs (managed machines).

```
[Host Client v2] ←→ [External WebSocket Server] ←→ [VM Client v2]
     (Controller)         (217.154.254.231:9000)        (Managed PC)
```

## Components

### 1. VM Client v2 (`vmclientv2.py`)
- **Role**: Managed machine that executes commands
- **Endpoint**: `ws://217.154.254.231:9000/api/vm/{vmid}/ws`
- **Capabilities**: 
  - Execute system commands
  - Stream output in real-time
  - Handle interactive commands
  - Auto-reconnection

### 2. Host Client v2 (`Host_serverv2.py`)
- **Role**: Controller that sends commands to VMs
- **Endpoint**: `ws://217.154.254.231:9000/api/host/{hostid}/ws`
- **Capabilities**:
  - Send commands to specific VMs
  - Receive VM responses
  - Web interface for easy management
  - Track connected VMs

## Setup Instructions

### For VM (Managed Machine):
1. Install dependencies:
   ```bash
   pip install websockets>=10.0
   ```

2. Run VM client:
   ```bash
   python vmclientv2.py [optional-vm-id]
   ```

### For Host (Controller):
1. Install dependencies:
   ```bash
   pip install websockets>=10.0 flask
   ```

2. Run Host client:
   ```bash
   python Host_serverv2.py
   ```

3. Access web interface: `http://localhost:8080`

## Message Flow

### Host → Server → VM (Command)
```json
Host sends:
{
    "type": "send_to_vm",
    "host_id": "host-DESKTOP-123",
    "message": "ls -la",
    "metadata": {
        "target_vm_id": "vm-DESKTOP-456",
        "message_type": "command",
        "command_id": "cmd-uuid-123"
    }
}

Server forwards to VM:
{
    "message": "ls -la",
    "type": "command",
    "metadata": {
        "command_id": "cmd-uuid-123"
    }
}
```

### VM → Server → Host (Response)
```json
VM sends:
{
    "type": "command_output",
    "vm_id": "vm-DESKTOP-456",
    "message": "total 8\ndrwxr-xr-x...",
    "metadata": {
        "command_id": "cmd-uuid-123",
        "output_type": "output"
    }
}

Server forwards to Host:
{
    "type": "vm_response",
    "message": "total 8\ndrwxr-xr-x...",
    "metadata": {
        "vm_id": "vm-DESKTOP-456",
        "response_type": "command_output",
        "command_id": "cmd-uuid-123"
    }
}
```

## Server Endpoint Requirements

The external server needs these endpoints:

### WebSocket Endpoints:
- `/api/vm/{vmid}/ws` - For VM clients
- `/api/host/{hostid}/ws` - For Host clients

### HTTP Endpoints (optional):
- `POST /api/vm/{vmid}/send` - Send message to specific VM
- `GET /api/vms` - List connected VMs
- `GET /api/hosts` - List connected hosts

## Web Interface Features

The Host client provides a web interface with:

- **VM Management**: View connected VMs and their status
- **Command Execution**: Send commands to specific VMs
- **Real-time Output**: Stream command output in real-time
- **Command History**: Track executed commands
- **Multi-VM Support**: Manage multiple VMs simultaneously

## Security Considerations

1. **Network Security**: Use secure networks or VPN
2. **Command Filtering**: VMs filter dangerous commands
3. **Authentication**: Consider adding authentication to server
4. **Encryption**: Consider WSS (WebSocket Secure) for production

## Troubleshooting

### VM Client Issues:
- Check network connectivity to server
- Verify WebSocket endpoint is reachable
- Check firewall settings

### Host Client Issues:
- Ensure web interface starts (port 8080)
- Check server connection status
- Verify VM is connected and visible

### Server Issues:
- Confirm server is running on 217.154.254.231:9000
- Check server logs for connection errors
- Verify endpoint paths match

## Migration from v1

### From Old VM_client.py:
- Stop the Flask server
- Run `vmclientv2.py` instead
- No port configuration needed

### From Old Host_server.py:
- Replace target IP configuration
- Run `Host_serverv2.py` instead
- Web interface remains similar

## Testing

### Test VM Connection:
```bash
# Run VM client
python vmclientv2.py test-vm-001

# Check logs for successful connection
```

### Test Host Connection:
```bash
# Run Host client
python Host_serverv2.py

# Open http://localhost:8080
# Check if VMs are listed
```

### Test Command Execution:
1. Ensure both VM and Host clients are connected
2. In Host web interface, select a VM
3. Send a simple command like `whoami`
4. Verify output appears in real-time

## Advanced Usage

### Custom VM ID:
```bash
python vmclientv2.py production-server-01
```

### Multiple VMs:
Run multiple VM clients with different IDs:
```bash
# Terminal 1
python vmclientv2.py web-server

# Terminal 2  
python vmclientv2.py database-server

# Terminal 3
python vmclientv2.py backup-server
```

### Host Scripting:
The Host client can be extended to support automated command execution, scheduling, and monitoring across multiple VMs.
