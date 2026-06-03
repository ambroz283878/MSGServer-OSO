from dotenv import load_dotenv
import json
import os
import socket
from time import sleep
from server_messages import TEXT, ACTION, make_message
import ast
load_dotenv()

port = int(os.getenv('SRV_PORT'))
addr = os.getenv('SRV_ADDR')

server = socket.socket()

try:
    server.connect((addr, port))
except ConnectionRefusedError:
    exit(-1)

print (server.recv(1024).decode())

user=input("Enter your username: ")
passwd=input("Enter your password: ")

listUsers=make_message(content="",sender=user,recipient="Server",action=ACTION["listAllUsers"])
login=("""{"action":"login", "properties":{"login":"%s", "password":"%s"}}""" % (user, passwd)).encode()
listOnline=make_message(content="",sender="Client",recipient="Server", action=ACTION["listOnlineUsers"])
msgPiwo=make_message(content="Piwo", sender=user, recipient="tester", action=ACTION["message"])
# json_packet="""{"action":"register","properties":{"login":"Rassena","password":"elozelo"}}"""
ping=make_message(content=TEXT["ping"],sender="Client",recipient="Server",action=ACTION["ping"])
server.send(login)
print(server.recv(1024).decode())
sleep(1)
server.send(listUsers)
sleep(1)
print(server.recv(1024).decode())

server.send(listOnline)
onlineUsersMSG=server.recv(1024).decode()
onlineUsersJSON=json.loads(onlineUsersMSG)
onlineUsersSTR=onlineUsersJSON["properties"]["content"]
onlineUsers= ast.literal_eval(onlineUsersSTR)
print("ONLINE USERS:\n", onlineUsers)
print("TYPE:\n", type(onlineUsers))
onlineUsers.remove(user)
sleep(10)
for onlineUser in onlineUsers:
    msg=make_message(content="Hello "+onlineUser, sender=user, recipient=onlineUser, action=ACTION["message"])
    server.send(msg)


# while input()!='exit':
server.send(ping)
while True:
    msg=server.recv(1024).decode()
    print(msg+"\n")
    server.send(input().encode())
    server.send(ping)

server.close()