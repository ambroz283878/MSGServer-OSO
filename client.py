import os
import socket
from dotenv import load_dotenv

load_dotenv()

port = int(os.getenv('SRV_PORT'))
addr = os.getenv('SRV_ADDR')

server = socket.socket()

try:
    server.connect((addr, port))
except ConnectionRefusedError:
    exit(-1)

print (server.recv(1024).decode())

json_packet="""{
    "action":"login",
    "properties":
    {
        "login":"Ambroz",
        "password":"$ekret123"
    }
    
}"""
server.send(json_packet.encode())
while input()!='exit':
    msg=server.recv(1024).decode()
    print(msg)
server.close()