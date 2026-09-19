#!/usr/bin/env python3
import json
import sys
import subprocess
import os

# luna only by default; astra/sol/terra are added by user config (roster.json / env map) once tested live.
DEFAULT_MODEL_MAP = {"luna": "gpt-5.6-luna"}


def _read_map(raw):
    raw = raw.strip()
    text = raw if raw.startswith("{") else open(os.path.expanduser(raw)).read()
    data = json.loads(text)
    if isinstance(data, dict) and isinstance(data.get("models"), dict):
        data = data["models"]
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in data.items()):
        raise ValueError("model map must be a JSON object of alias -> slug strings")
    return data


def load_model_map():
    """Defaults < ~/.config/agents-inc/roster.json < AGENTS_INC_MODEL_MAP < CODEXAGENT_MODEL_MAP.

    Env values are a JSON object string (starts with "{") or a path to a JSON file.
    Malformed override: warn on stderr, keep the rest, never raise.
    """
    merged = dict(DEFAULT_MODEL_MAP)
    roster = os.path.join(os.environ.get("HOME", ""), ".config/agents-inc/roster.json")
    sources = [("roster", roster if os.path.isfile(roster) else None)]
    sources += [(n, os.environ.get(n)) for n in ("AGENTS_INC_MODEL_MAP", "CODEXAGENT_MODEL_MAP")]
    for label, raw in sources:
        if not raw:
            continue
        try:
            merged.update(_read_map(raw))
        except (OSError, ValueError) as exc:
            sys.stderr.write("WARN: ignoring malformed model map from %s: %s; using defaults\n" % (label, exc))
    return merged


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
    model_map = load_model_map()
    models = sorted(model_map)
    default_model = "luna" if "luna" in model_map else models[0]
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "tools": [
                {
                    "name": "DelegateAgent",
                    "description": "Delegate a task to an agent (Codex models: %s)" % ", ".join(models),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string"
                            },
                            "model": {
                                "type": "string",
                                "enum": models,
                                "default": default_model
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
    if len(sys.argv) == 3 and sys.argv[1] == "--resolve-model":
        # Used by scripts/codexagent.sh: print slug for alias, exit 1 if unknown.
        _slug = load_model_map().get(sys.argv[2])
        if not _slug:
            sys.exit(1)
        print(_slug)
    elif len(sys.argv) == 2 and sys.argv[1] == "--list-models":
        print(" ".join(sorted(load_model_map())))
    else:
        main()
