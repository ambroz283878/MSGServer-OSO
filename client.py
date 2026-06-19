from dotenv import load_dotenv
import json
import os
import socket
from time import sleep
from server_messages import TEXT, ACTION, make_message
import ast

# wczytaj zmienne środowiskowe z pliku .env
load_dotenv()

port_str = os.getenv("SRV_PORT")
addr = os.getenv("SRV_ADDR")

if not port_str:
    raise ValueError("SRV_PORT is missing or empty")

if not addr:
    raise ValueError("SRV_ADDR is missing or empty")

# Ustawiamy nr. portu i adres IP serwera ze zmiennej środowiskowej aby ustanowić połączenie  

try:
    port = int(port_str)
except ValueError as e:
    raise ValueError(f"Invalid SRV_PORT value: {port_str}") from e

server = socket.socket()


# Próba połączenia do serwera uywając podanych danych
try:
    server.connect((addr, port))
except ConnectionRefusedError:
    raise SystemExit("Could not connect to server")

print (server.recv(1024).decode())

#logowanie
user=input("Enter your username: ")
passwd=input("Enter your password: ")

# request do serwera o podanie listy wszystkich użytkowników
listUsers=make_message(content="",sender=user,recipient="Server",action=ACTION["listAllUsers"])




# request do serwera o rejestracje
register=("""{"action":"register", "properties":{"login":"%s", "password":"%s"}}""" % (user, passwd)).encode()

# request do serwera o uwierzytelnienie używając podanych referencji 
login=("""{"action":"login", "properties":{"login":"%s", "password":"%s"}}""" % (user, passwd)).encode()
logout=("""{"action":"logout", "properties":{"login":"%s"}}""" % ("cli test")).encode()

#request do serwera o podanie listy aktywnych użytkowników
listOnline=make_message(content="",sender=user,recipient="Server", action=ACTION["listOnlineUsers"])
listOnlineSpoof=make_message(content="",sender="Client",recipient="Server", action=ACTION["listOnlineUsers"])

# wiadomość do innego uźytkownika
msgPiwo=make_message(content="Piwo", sender=user, recipient="tester", action=ACTION["message"])

# wiadomość HELLO
ping=make_message(content=TEXT["ping"],sender=user,recipient="Server",action=ACTION["ping"])

# request do servera o public_key
# pubkey = "bardzoBezpiecznyKlucz"
pubkey = "JakisKlucz"
setPubKey=("""{"action":"setPubKey", "properties":{"sender":"%s", "content":"%s"}}""" % (user, pubkey)).encode()
fetchPubKey=("""{"action":"fetchPubKey", "properties":{"sender":"%s", "content":"%s"}}""" % (user, user)).encode()

fetchPubKey_error=("""{"action":"fetchPubKey", "properties":{"sender":"%s", "content":"%s"}}""" % (user, "ZlyUser")).encode()

print("register:")
server.send(register)
print(server.recv(1024).decode())
sleep(1)

print()

print("login:")
server.send(login)
print(server.recv(1024).decode())
sleep(1)

print()

print("listUsers:")
print(listUsers)
server.send(listUsers)
sleep(1)
print(server.recv(1024).decode())

print()

print("listOnline:")
print(listOnline)
server.send(listOnline)
sleep(1)
print(server.recv(1024).decode())

print()

print("listOnlineSpoof:")
print(listOnlineSpoof)
server.send(listOnlineSpoof)
sleep(1)
print(server.recv(1024).decode())

# #wczytanie listy aktywnych użytkowników z odpowiedzi serwera
# onlineUsers=ast.literal_eval(json.loads(server.recv(1024).decode())["properties"]["content"])


# print("ONLINE USERS:\n", onlineUsers)
# print("TYPE:\n", type(onlineUsers))
# onlineUsers.remove(user)
# sleep(10)
# # wysyłanie wiadomości do wszystkich aktywnych użytkowników
# for onlineUser in onlineUsers:
#     msg=make_message(content="Hello "+onlineUser, sender=user, recipient=onlineUser, action=ACTION["message"])
#     server.send(msg)


# # wypisywanie otrzymanych wiadomości z serwera
# server.send(ping)

print()



print("setPubKey:")
print(setPubKey)
server.send(setPubKey)
sleep(1)
print(server.recv(1024).decode())

print()

print("fetchPubKey:")
print(fetchPubKey)
server.send(fetchPubKey)
sleep(1)
print(server.recv(1024).decode())

print()

print("fetchPubKey_error:")
print(fetchPubKey_error)
server.send(fetchPubKey_error)
sleep(1)
print(server.recv(1024).decode())

print()

print("logout:")
server.send(logout)
print(server.recv(1024).decode())


# while True:
#     msg=server.recv(1024).decode()
#     print(msg+"\n")
#     userInput=input()
#     if userInput == "exit":
#         break
#     server.send(userInput.encode())
#     server.send(ping)

server.close()