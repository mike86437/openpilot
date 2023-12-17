import asyncio
import websockets

async def handle_connection(websocket, path):
    try:
        while True:
            message = "Hello World"
            await websocket.send(message)
            await asyncio.sleep(1)
    except websockets.exceptions.ConnectionClosedError:
        print("WebSocket connection closed")

# Start WebSocket server
start_server = websockets.serve(handle_connection, "localhost", 8765)

try:
    # Run the server
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
except KeyboardInterrupt:
    print("Server interrupted, closing...")
finally:
    start_server.close()
    asyncio.get_event_loop().run_until_complete(start_server.wait_closed())
    asyncio.get_event_loop().close()
