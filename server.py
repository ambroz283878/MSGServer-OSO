from dotenv import load_dotenv
import json
import os
import psycopg2
import socket
import threading

def connectionHandler(conn, addr):
  conn.send('Thank you for connecting!\n'.encode()) 

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
    case _:
      conn.send('Invalid action!'.encode())

def loginUser(userConnection,jsonPacket):
  queryCheckCredentials = """SELECT * FROM USERS WHERE USERNAME = (%s) AND PASSWORD = (%s) """
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
  queryAddUser = """INSERT INTO USERS (USERNAME, PASSWORD) VALUES (%s, %s)"""
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