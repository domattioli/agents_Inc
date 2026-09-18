#!/usr/bin/env python3
import json
import sys
import subprocess
import os

def send_response(obj):
    """Send JSON-RPC response to stdout."""
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

def handle_initialize(req_id):
    """Handle initialize method."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "delegate-agent-mcp",
                "version": "0.1.0"
            }
        }
    }

def handle_tools_list(req_id):
    """Handle tools/list method."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "tools": [
                {
                    "name": "DelegateAgent",
                    "description": "Delegate a task to an agent (currently: Codex luna model only)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string"
                            },
                            "model": {
                                "type": "string",
                                "enum": ["luna"],
                                "default": "luna"
                            },
                            "cwd": {
                                "type": "string"
                            }
                        },
                        "required": ["prompt"]
                    }
                }
            ]
        }
    }

def handle_tools_call(req_id, params):
    """Handle tools/call method."""
    if params.get("name") != "DelegateAgent":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": "Method not found"
            }
        }

    args = params.get("arguments", {})
    prompt = args.get("prompt")
    model = args.get("model", "luna")
    cwd = args.get("cwd")

    if not prompt:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "Error: prompt required"
                    }
                ],
                "isError": True
            }
        }

    # Resolve script path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, "..", "scripts", "codexagent.sh")

    cmd = [script_path, "--model", model, prompt]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=cwd,
            stdin=subprocess.DEVNULL
        )

        if result.returncode == 0:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": result.stdout
                        }
                    ]
                }
            }
        else:
            error_msg = result.stderr if result.stderr else f"Exit code {result.returncode}"
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": error_msg
                        }
                    ],
                    "isError": True
                }
            }

    except subprocess.TimeoutExpired:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "Error: timeout"
                    }
                ],
                "isError": True
            }
        }
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: {str(e)}"
                    }
                ],
                "isError": True
            }
        }

def main():
    """Main JSON-RPC server loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            # Silently skip malformed JSON
            continue

        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params", {})

        # Notifications have no id
        if req_id is None and method == "notifications/initialized":
            # Notification: no response
            continue

        # Methods with id
        if method == "initialize":
            response = handle_initialize(req_id)
            send_response(response)

        elif method == "tools/list":
            response = handle_tools_list(req_id)
            send_response(response)

        elif method == "tools/call":
            response = handle_tools_call(req_id, params)
            send_response(response)

        else:
            # Unknown method
            if req_id is not None:
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": "Method not found"
                    }
                })

if __name__ == "__main__":
    main()
