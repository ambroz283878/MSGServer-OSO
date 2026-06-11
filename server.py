from dotenv import load_dotenv
import json
import keyExchange
import os
import psycopg2
import socket
from server_messages import ACTION, make_message, TEXT
import threading
from typing import Any, Optional
from user import User

class Server():
    def __init__(self):
        load_dotenv()
        self.dbUrl = os.getenv('DATABASE_URL')
        self.port = int(os.getenv('SRV_PORT'))
        self.maxClientCount = int(os.getenv('SRV_MAX_CONN'))
        self.dbConnection = psycopg2.connect(self.dbUrl)
        self.userConnMap = {}
        self.keys = keyExchange.keyGen()

        print(f"Port: {self.port}\nMax klientów: {self.maxClientCount}")

    def openConnection(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print("Socket successfully created")

        self.server.bind(('0.0.0.0', self.port))
        print("Socket bound to port %s" %(self.port))

    def listen(self):        
        self.server.listen(self.maxClientCount)
        print("socket is listening")

        while True: 
            client, addr = self.server.accept()     
            print('Got connection from', addr)

            threading.Thread(target=self.connectionHandler,args=(client,addr)).start()            

    def connectionHandler(self, conn:socket.socket, addr:tuple[str, int]):
        user = User(self,conn,addr, self.dbConnection)
        conn.send(make_message(TEXT["welcome"]))
        conn.send(make_message(str(self.keys["pub"]),action=ACTION["sendPubKey"]))
        while True:
            try:
                msg = self.validateJsonPacket(conn.recv(1024).decode())
                if msg:
                    user.handleRequest(msg)
                else:
                    conn.send(make_message(TEXT["invalid_packet"]))
            except (BrokenPipeError, ConnectionResetError):
                print("Closing connection")
                self.userConnMap.pop(user.getUsername)
                break

    def insertUser(self, user:User):
        self.userConnMap[user.getUsername()] = user

    # TODO:
        # poprawić/zdefiniować format zwracanych danych
    def listAllUsers(self) -> list:
        with self.dbConnection:
            with self.dbConnection.cursor() as cursor:
                queryAllUsers = """SELECT name FROM users"""
                cursor.execute(queryAllUsers)
                return cursor.fetchall()
            
    def listOnlineUsers(self) -> list:
        return list(self.userConnMap.keys())

    def validateJsonPacket(self, msg: str)->Optional[dict[str, Any]]:
        try:
            packet = json.loads(msg)
            return packet
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            print(f"msg got: {msg}")
            return None
