from dotenv import load_dotenv
import json
import os
import socket
from time import sleep
from server_messages import TEXT, ACTION, make_message
import ast

# wczytaj zmienne środowiskowe z pliku .env
load_dotenv()
# Ustawiamy nr. portu i adres IP serwera ze zmiennej środowiskowej aby ustanowić połączenie  
port = int(os.getenv('SRV_PORT'))
addr = os.getenv('SRV_ADDR')
server = socket.socket()

# Próba połączenia do serwera uywając podanych danych
try:
    server.connect((addr, port))
except ConnectionRefusedError:
    exit(-1)

print (server.recv(1024).decode())

#logowanie
user=input("Enter your username: ")
passwd=input("Enter your password: ")

# request do serwera o podanie listy wszystkich użytkowników
listUsers=make_message(content="",sender=user,recipient="Server",action=ACTION["listAllUsers"])

# request do serwera o uwierzytelnienie używając podanych referencji 
login=("""{"action":"login", "properties":{"login":"%s", "password":"%s"}}""" % (user, passwd)).encode()

#request do serwera o podanie listy aktywnych użytkowników
listOnline=make_message(content="",sender="Client",recipient="Server", action=ACTION["listOnlineUsers"])

# wiadomość do innego uźytkownika
msgPiwo=make_message(content="Piwo", sender=user, recipient="tester", action=ACTION["message"])

# wiadomość HELLO
ping=make_message(content=TEXT["ping"],sender="Client",recipient="Server",action=ACTION["ping"])


server.send(login)
print(server.recv(1024).decode())
sleep(1)
server.send(listUsers)
sleep(1)
print(server.recv(1024).decode())

server.send(listOnline)
#wczytanie listy aktywnych użytkowników z odpowiedzi serwera
onlineUsers=ast.literal_eval(json.loads(server.recv(1024).decode())["properties"]["content"])

print("ONLINE USERS:\n", onlineUsers)
print("TYPE:\n", type(onlineUsers))
onlineUsers.remove(user)
sleep(10)
# wysyłanie wiadomości do wszystkich aktywnych użytkowników
for onlineUser in onlineUsers:
    msg=make_message(content="Hello "+onlineUser, sender=user, recipient=onlineUser, action=ACTION["message"])
    server.send(msg)


# wypisywanie otrzymanych wiadomości z serwera
server.send(ping)
while True:
    msg=server.recv(1024).decode()
    print(msg+"\n")
    userInput=input()
    if userInput == "exit":
        break
    server.send(userInput.encode())
    server.send(ping)

server.close()