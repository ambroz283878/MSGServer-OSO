from dotenv import load_dotenv
import json
import os
import psycopg2
import socket
import threading

def connectionHandler(conn, addr):
  onNewConnection(conn)

  rawPacket=conn.recv(1024).decode()

  try:
    jsonPacket=json.loads(rawPacket)
  except json.JSONDecodeError:
    print("Received invalid packet")
    conn.close()
    return(-1)
  action=jsonPacket["action"]

  match action:
    case "login":
      loginUser(conn,jsonPacket)
    case "register":
      registerUser(conn,jsonPacket)
    case _:
      conn.send('Invalid action!'.encode())
      return -1
  updateIP(jsonPacket["properties"]["login"], addr)
  updateLastLogin(jsonPacket["properties"]["login"])

def loginUser(userConnection,jsonPacket):
  queryCheckCredentials = """SELECT * FROM USERS WHERE user = (%s) AND password = (%s) """
  credentials=jsonPacket["properties"]
  with dbConnection:
    with dbConnection.cursor() as cursor:
      print(f"""Executing:\n{queryCheckCredentials}\nlogin: {credentials["login"]}\npassword: {credentials["password"]}""")
      cursor.execute(queryCheckCredentials, (credentials["login"], credentials["password"]))
      result = cursor.fetchone()
      if result is None:
        userConnection.send('Bad password!'.encode())
        userConnection.close()
        print(f"Failed login attempt into account {credentials["login"]} from {addr}")
        return -1
      userConnection.send(f'Succesfully logged in as {credentials["login"]}!'.encode())

def registerUser(userConnection,jsonPacket):
  queryAddUser = """INSERT INTO USERS (name, password) VALUES (%s, %s)"""
  credentials=jsonPacket["properties"]
  with dbConnection:
    with dbConnection.cursor() as cursor:
      print(f"""Executing:\n{queryAddUser}\nlogin: {credentials["login"]}\npassword: {credentials["password"]}""")

      try:
        cursor.execute(queryAddUser, (credentials["login"], credentials["password"]))
      except psycopg2.errors.UniqueViolation:
        cursor.rollback()
        userConnection.send('Username already taken!'.encode())
        return -1
      
      userConnection.send(f'Succesfully registered as {credentials["login"]}!'.encode())

def updateIP(username, addr):
  queryUpdateLastKnownIP = """UPDATE users SET ip = (%s) WHERE name=(%s)"""
  with dbConnection:
    with dbConnection.cursor() as cursor:
      print(f"""Executing:\n{queryUpdateLastKnownIP}\nuser: {username}\naddr: {addr}""")
      cursor.execute(queryUpdateLastKnownIP, (addr[0], username))

def updatePublicKey(username, pubKey):
  queryUpdatePubKey = """UPDATE users SET public_key = (%s) WHERE name=(%s)"""
  with dbConnection:
    with dbConnection.cursor() as cursor:
      print(f"""Executing:\n{queryUpdatePubKey}\nuser: {username}\npubKey: {pubKey}""")
      cursor.execute(queryUpdatePubKey, (pubKey, username))

def updateLastLogin(username):
  queryUpdateLastLoginTime="""UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE name=(%s)"""
  with dbConnection:
    with dbConnection.cursor() as cursor:
      print(f"""Executing:\n{queryUpdateLastLoginTime}\nuser: {username}""")
      cursor.execute(queryUpdateLastLoginTime, (username,))

def onNewConnection(userConnection):
  userConnection.send('Thank you for connecting!'.encode())
  userConnection.send("(>>Klucz publiczny serwera<<)".encode())

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