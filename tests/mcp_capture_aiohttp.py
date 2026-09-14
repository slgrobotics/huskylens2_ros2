import asyncio
import json
import base64
import aiohttp

"""
Retrieve the image from HuskyLens 2 MCP Server using aiohttp and SSE.

This script connects to the MCP server, initializes the session, and requests the recognition result.

Usage:
    python3 mcp_capture_aiohttp.py

Output:
    Connecting to HuskyLens 2 MCP Server at http://172.17.1.165:3000...
    Session established. Message endpoint: http://172.17.1.165:3000/message?session_id=76d1f93a-ddb9-1c5b-9b9b-743f105033ab
    Sending initialization request...
    Initialization response received: {'jsonrpc': '2.0', 'id': 1, 'result': {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'Huskylens MCP Server', 'version': '1.0.1'}}}
    Requesting frame and recognition data from HuskyLens 2...
    IP: processing returned image...
    OK: Successfully saved frame to huskylens_captured_frame.jpg
    Tool text message: [
        {
            "algorithm" : 2,
            "content" : "",
            "height" : 129,
            "id" : 0,
            "name" : "keyboard",
            "width" : 392,
            "xCenter" : 204,
            "yCenter" : 411
        },
        {
            "algorithm" : 2,
            "content" : "",
            "height" : 228,
            "id" : 0,
            "name" : "chair",
            "width" : 257,
            "xCenter" : 150,
            "yCenter" : 114
        }
    ]

====== Why Async/aiohttp is Common for MCP - vs. "requests" library =======
    Persistent Streaming (SSE): MCP transport over HTTP uses a Server-Sent Events connection. 
    This is a long-lived, open HTTP connection where the server continuously streams data down to the client.

    Non-Blocking Execution: requests is strictly synchronous and blocks your script's execution while waiting for data.
    If you want to listen for incoming server notifications while simultaneously sending POST commands,
    aiohttp handles this concurrently using Python's asyncio event loop without needing complex threading.

    Ecosystem Alignment: Official and community MCP client libraries in Python are built on top of asyncio to natively handle these persistent event streams.

"""

HUSKYLENS_MCP_URL = "http://172.17.1.165:3000"

async def pull_image_from_mcp():
    print(f"Connecting to HuskyLens 2 MCP Server at {HUSKYLENS_MCP_URL}...")
    
    async with aiohttp.ClientSession() as session:
        # 1. Establish the long-lived SSE connection
        async with session.get(f"{HUSKYLENS_MCP_URL}/sse") as sse_response:
            if sse_response.status != 200:
                print(f"Failed to connect to SSE endpoint: {sse_response.status}")
                return

            message_endpoint = None
            
            # Read lines until we find the message endpoint from the SSE event
            async for line in sse_response.content:
                line_str = line.decode('utf-8').strip()
                if line_str.startswith("data:"):
                    path = line_str[5:].strip()
                    if path.startswith("/"):
                        message_endpoint = f"{HUSKYLENS_MCP_URL}{path}"
                    else:
                        message_endpoint = path
                    break

            if not message_endpoint:
                print("Could not resolve MCP message endpoint.")
                return

            print(f"Session established. Message endpoint: {message_endpoint}")

            # Helper function to send a command and wait for the response on the SSE stream
            async def send_mcp_request(payload):
                async with session.post(message_endpoint, json=payload) as post_resp:
                    if post_resp.status not in (200, 202):
                        text = await post_resp.text()
                        raise Exception(f"POST failed with status {post_resp.status}: {text}")
                
                # Read upcoming SSE stream chunks to find the response matching our request ID
                target_id = payload.get("id")
                async for line in sse_response.content:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith("data:"):
                        try:
                            data = json.loads(line_str[5:].strip())
                            if data.get("id") == target_id or "result" in data or "error" in data:
                                return data
                        except json.JSONDecodeError:
                            continue

            # 2. Send MCP Initialize Request
            print("Sending initialization request...")
            init_payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "Pi-MCP-Client", "version": "1.0"}
                },
                "id": 1
            }
            init_result = await send_mcp_request(init_payload)
            print("Initialization response received:", init_result)

            # 3. Send initialized notification
            notif_payload = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            }
            await session.post(message_endpoint, json=notif_payload)

            # 4. Call the correct tool to get recognition results and image payload
            print("Requesting frame and recognition data from HuskyLens 2...")
            tool_payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "self.get_recognition_result", # Fixed tool name (singular)
                    "arguments": {
                        "algorithm": 2
                    }
                },
                "id": 2
            }
            
            tool_result = await send_mcp_request(tool_payload)

            # Parse the tool payload content
            try:
                content = tool_result.get("result", {}).get("content", [])
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type")
                        
                        # Handle direct MCP image block type
                        if item_type == "image":
                            print("IP: processing returned image...")
                            img_base64 = item.get("data")
                            if img_base64:
                                image_bytes = base64.b64decode(img_base64)
                                output_file = "huskylens_captured_frame.jpg"
                                with open(output_file, "wb") as f:
                                    f.write(image_bytes)
                                print(f"OK: Successfully saved frame to {output_file}")
                        
                        # Handle text logs if any are returned alongside
                        elif item_type == "text":
                            print("Tool text message:", item.get("text"))

                #print("Full tool result received (checking structure):")
                #print(json.dumps(tool_result, indent=2))
                
            except Exception as e:
                print(f"Error parsing tool output: {e}")
                print("Raw tool result:", tool_result)


if __name__ == "__main__":
    asyncio.run(pull_image_from_mcp())

