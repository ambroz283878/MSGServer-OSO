from dotenv import load_dotenv
import json
import os
import socket
from server_messages import TEXT, ACTION, make_message
load_dotenv()

port = int(os.getenv('SRV_PORT'))
addr = os.getenv('SRV_ADDR')

server = socket.socket()

try:
    server.connect((addr, port))
except ConnectionRefusedError:
    exit(-1)

print (server.recv(1024).decode())

user="Admin01"
passwd="elo"

listUsers=make_message(content="",sender=user,recipient="Server",action=ACTION["listAllUsers"])
login="""{"action":"login", "properties":{"login":"Admin01", "password":"elo"}}""".encode()

# json_packet="""{"action":"register","properties":{"login":"Rassena","password":"elozelo"}}"""
server.send(login)
server.send(listUsers)

# while input()!='exit':
while True:
    msg=server.recv(1024).decode()
    print(msg)
    server.send(input().encode())

server.close()