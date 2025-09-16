# Explanation of `vmclientv2.py`

This document provides a detailed explanation of the `vmclientv2.py` script, its architecture, and how it works.

## 1. Overview

`vmclientv2.py` is a sophisticated Python-based WebSocket client designed to run on a virtual machine (VM) or any remote machine. It connects to a central WebSocket server, registers itself with a unique VM ID, and then listens for commands to execute.

Its primary purpose is to provide a remote shell-like interface over WebSockets, allowing a server to execute commands on the client machine and receive real-time output. It is built to be robust, with features like automatic reconnection, handling of interactive commands, and secure command execution.

## 2. Core Components

The script is built around two main classes: `StreamingCommandExecutor` and `VMWebSocketClient`.

### `StreamingCommandExecutor`

This class is responsible for the low-level task of executing shell commands on the host system.

-   **Command Execution**: It can execute commands and capture their standard output and standard error.
-   **Streaming Output**: Instead of waiting for a command to finish, it streams the output back in real-time. This is achieved by running the command in a separate thread and reading its output incrementally.
-   **Interactive Command Support (PTY)**: For Linux and macOS systems, it uses a pseudo-terminal (PTY) to run commands. This is crucial for interactive commands like `sudo`, `ssh`, or scripts that prompt for user input, as it emulates a real terminal more closely. For Windows or when PTY is not available, it falls back to a standard `subprocess.Popen`.
-   **Security**: It includes a basic safety mechanism (`is_safe_command`) to block potentially dangerous commands like `rm`, `shutdown`, etc.
-   **Process Management**: It keeps track of running processes, allowing them to be stopped (`stop_command`) or receive input (`send_input`).

### `VMWebSocketClient`

This class manages the client's lifecycle and its communication with the WebSocket server.

-   **Connection Management**: It handles connecting to the server (`connect`), disconnecting (`disconnect`), and automatic reconnection (`run_with_reconnect`). If the connection is lost, it will try to reconnect several times before giving up.
-   **Message Protocol**: It understands a specific JSON-based message protocol to communicate with the server. It can handle different message types:
    -   `command`: To execute a new command.
    -   `stop_command`: To terminate a running command.
    -   `send_input`: To send input to a command that is waiting for it (e.g., a password for `sudo`).
    -   `ping`: To respond to server health checks.
    -   `status_request`: To provide its current status.
-   **Asynchronous Operation**: The client is built using Python's `asyncio` library, allowing it to handle network communication and command execution concurrently without blocking.
-   **Heartbeating**: It sends a periodic "heartbeat" message to the server to signal that it is still alive and to keep the WebSocket connection open through firewalls or proxies.
-   **Thread-Safe Message Queue**: It uses an `asyncio.Queue` to allow background threads (like the one reading command output) to safely send messages back to the server via the main asynchronous event loop.

## 3. Workflow

1.  **Initialization**: When `main()` is executed, it determines the `vm_id` (either from a command-line argument or by generating one from the hostname and MAC address) and creates an instance of `VMWebSocketClient`.
2.  **Connection**: The client connects to the WebSocket server at `ws://<server_url>/api/vm/<vm_id>/ws`. Upon connecting, it sends an initial `connection` message with system information.
3.  **Listening Loop**: The client enters the `listen()` loop, where it waits for messages from the server.
4.  **Message Handling**: When a message arrives, `handle_message` parses it.
    -   If it's a `command` message, `handle_command` is called. It uses the `StreamingCommandExecutor` to start the command. A callback function is passed to the executor to handle the output.
    -   The callback function queues the output, completion status, or input prompts into the `message_queue`.
    -   The `process_message_queue` task runs in the background, picks up these queued messages, and sends them to the server.
5.  **Interactive Commands**: If a command requires input (e.g., `sudo` asks for a password), the `StreamingCommandExecutor` detects this prompt. The callback sends a `command_awaiting_input` message to the server. The server can then send a `send_input` message, which is handled by `handle_send_input` to provide the necessary input to the running command.
6.  **Reconnection**: If the connection is lost for any reason, the `run_with_reconnect` logic catches the exception and attempts to reconnect after a short delay.

## 4. How to Run the Client

### Dependencies

The script requires the following Python libraries:

-   `websockets`
-   `asyncio` (part of the standard library in Python 3.7+)

You can install the necessary package using pip:
```bash
pip install websockets
```

### Running the Script

Execute the script from your terminal:

```bash
python vmclientv2.py [vm_id]
```

-   `[vm_id]` is an optional argument. If you provide it, the client will use that ID.
-   If you don't provide a `vm_id`, the script will generate a unique one based on your computer's hostname and MAC address.

The client will then start, connect to the server specified in the `SERVER_URL` variable, and wait for commands.
