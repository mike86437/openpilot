import zmq
import time
import logging

logging.basicConfig(level=logging.DEBUG)

def main():
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind("tcp://0.0.0.0:5555")

    try:
        # Publish messages
        for i in range(5):
            message = f"Hello World {i}"
            socket.send_string(message)
            time.sleep(1)

    except Exception as e:
        logging.error(f"Error: {e}")

    finally:
        # Release resources
        socket.close()
        context.term()

if __name__ == "__main__":
    main()
