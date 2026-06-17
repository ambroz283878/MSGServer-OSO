import sys

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
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
    force=True
)

log = logging.getLogger(__name__)

class Server():
    def __init__(self):
        load_dotenv()
        self.dbUrl = os.getenv('DATABASE_URL')
        self.port = int(os.getenv('SRV_PORT'))
        self.maxClientCount = int(os.getenv('SRV_MAX_CONN'))
        self.dbConnection = psycopg2.connect(self.dbUrl)
        self.userConnMap = {}
        self.keys = keyExchange.keyGen()


        log.info("Server config: port=%s max_clients=%s", self.port, self.maxClientCount)

    def openConnection(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        log.info("Socket successfully created")

        self.server.bind(('0.0.0.0', self.port))
        log.info("Socket bound to port %s" %(self.port))

    def listen(self):        
        self.server.listen(self.maxClientCount)
        log.info("socket is listening")

        while True: 
            client, addr = self.server.accept()     
            log.info("Got connection from %s:%s", addr[0], addr[1])

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
            except (BrokenPipeError, ConnectionResetError,OSError):
                log.warning(TEXT["server_close_connection"].format(user=f"{user.getUsername()} {addr[0]}:{addr[1]}"))
                try:
                    self.userConnMap.pop(user.getUsername())
                except (AttributeError, KeyError): #if a user didn't yet log in, username would be null and cause this error
                    pass
                exit(-1)

    def insertUser(self, user:User):
        try:
            self.userConnMap[user.getUsername()].append(user)
        except KeyError:
            self.userConnMap[user.getUsername()] = [user]


    def listAllUsers(self) -> list[str]:
        with self.dbConnection:
            with self.dbConnection.cursor() as cursor:
                queryAllUsers = """SELECT name FROM users"""
                cursor.execute(queryAllUsers)
                return [row[0] for row in cursor.fetchall()]
            
    def listOnlineUsers(self) -> list[str]:
        return sorted(list(self.userConnMap.keys()))


    def validateJsonPacket(self, msg: str)->Optional[dict[str, Any]]:
        try:
            packet = json.loads(msg)
            return packet
        except json.JSONDecodeError as e:
            log.warning(
                "Invalid JSON from client: error=%s raw_message=%r",
                e,
                msg
            )
            return None
