import zmq
import time

context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("tcp://0.0.0.0:5555")

# Publish messages
for i in range(5):
    message = f"Hello World {i}"
    socket.send_string(message)
    time.sleep(1)
