# Remote Command Server/Client - HTTPS/WSS Secure Edition

A secure remote command execution system with HTTPS and WebSocket Secure (WSS) support for encrypted communication.

## 🔒 Security Features

- **HTTPS Communication**: All HTTP requests are encrypted using SSL/TLS
- **WSS (WebSocket Secure)**: Real-time streaming uses encrypted WebSocket connections
- **Self-Signed Certificates**: Automatic SSL certificate generation for immediate use
- **Certificate Validation**: Configurable SSL certificate validation
- **Fallback Support**: Automatic fallback to HTTP if HTTPS fails

## 🚀 Quick Start

### 1. Install Dependencies

```bash
python setup.py
```

Or manually:
```bash
pip install -r requirements.txt
```

### 2. Start the Server (Target PC)

```bash
python server.py
```

The server will:
- Generate SSL certificates automatically if none exist
- Start HTTPS server on port 5000
- Enable WSS for real-time streaming
- Display connection information

### 3. Start the Client (Control PC)

```bash
python client.py
```

The client will:
- Ask for target PC IP address
- Ask if you want to use HTTPS (recommended: Yes)
- Test connection with automatic HTTP fallback
- Open web interface on http://localhost:8080

## 🛡️ Security Information

### SSL Certificates

The server automatically generates self-signed SSL certificates on first run:
- `server.crt` - SSL certificate
- `server.key` - Private key

**Important**: Self-signed certificates will show browser warnings. This is normal and safe for trusted networks.

### HTTPS vs HTTP

- **HTTPS (Recommended)**: All communication is encrypted
- **HTTP (Fallback)**: Unencrypted communication for compatibility

### Network Security

- Only run on trusted networks
- Firewall rules should restrict access to port 5000
- Consider using proper CA-signed certificates for production

## 📁 Files

- `server.py` - HTTPS/WSS server for target PC
- `client.py` - HTTPS client and web interface
- `templates/index.html` - Secure web interface
- `requirements.txt` - Python dependencies
- `setup.py` - Installation script
- `server.crt` - SSL certificate (auto-generated)
- `server.key` - SSL private key (auto-generated)

## 🔧 Configuration

### Server Configuration

The server accepts several security options:
- Automatic SSL certificate generation
- Configurable SSL context
- CORS settings for WebSocket connections

### Client Configuration

The client provides security options:
- HTTPS preference setting
- SSL certificate verification (disabled for self-signed)
- Automatic HTTP fallback

## 🌐 Web Interface Features

- 🔒 Secure WebSocket connections (WSS)
- 📡 Real-time command streaming
- 🛑 Command termination
- 📝 Interactive input support
- 📊 Live status indicators
- 📜 Command history
- 🔄 Automatic reconnection

## ⚠️ Security Warnings

1. **Self-Signed Certificates**: Browser will show security warnings
2. **Network Access**: Only use on trusted networks
3. **Command Execution**: Server executes commands with current user privileges
4. **Certificate Storage**: Keep `server.key` file secure

## 🔍 Troubleshooting

### HTTPS Connection Issues

If HTTPS fails:
1. Check if certificates exist (`server.crt`, `server.key`)
2. Verify firewall allows port 5000
3. Client will automatically fallback to HTTP
4. Check server logs for SSL errors

### Browser Certificate Warnings

For self-signed certificates:
1. Click "Advanced" in browser warning
2. Click "Proceed to [hostname] (unsafe)"
3. This is safe for trusted networks

### WebSocket Connection Issues

If WSS fails:
1. WebSocket will fallback to polling
2. Check browser console for errors
3. Verify target server is accessible
4. Check if port 5000 is blocked

## 📝 Development

To extend or modify:
1. Server SSL configuration in `generate_self_signed_cert()`
2. Client security options in `RemoteClient` class
3. WebSocket security in `templates/index.html`

## 📄 License

This is educational/development software. Use responsibly and only on networks you own or have permission to use.
