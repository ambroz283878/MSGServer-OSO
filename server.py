from dotenv import load_dotenv
import json
import keyExchange
import os
import psycopg2
import socket
import threading
from user import User

def connectionHandler(conn, addr):
  user = User(conn,addr, dbConnection)
  conn.send('Thank you for connecting!'.encode())
  conn.send(str(user.getSrvPubKey()).encode())

load_dotenv()

dbUrl = os.getenv('DATABASE_URL')
port = int(os.getenv('SRV_PORT'))
maxClientCount = int(os.getenv('SRV_MAX_CONN'))

dbConnection = psycopg2.connect(dbUrl)

print(f"Port: {port}\nMax klientów: {maxClientCount}")

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
print("Socket successfully created")

server.bind(('0.0.0.0', port))
print("Socket bound to port %s" %(port))

server.listen(maxClientCount)
print("socket is listening")

while True: 

  client, addr = server.accept()     
  print('Got connection from', addr)

  threading.Thread(target=connectionHandler,args=(client,addr)).start()