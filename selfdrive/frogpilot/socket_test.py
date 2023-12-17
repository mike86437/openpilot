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

async def main():
    # Start WebSocket server
    start_server = websockets.serve(handle_connection, "0.0.0.0", 8765)

    try:
        # Run the server
        await start_server
        await asyncio.Future()  # Keep the main coroutine running

    except KeyboardInterrupt:
        print("Server interrupted, closing...")

    finally:
        start_server.close()
        await start_server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
