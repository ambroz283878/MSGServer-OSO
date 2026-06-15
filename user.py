import json
import socket
import threading
import time
from typing import TYPE_CHECKING
import psycopg2
#import keyExchange
import psycopg2.extensions
from server_messages import ACTION, make_message, TEXT

if TYPE_CHECKING:
    from server import Server

class User():
    def __init__(self,server:"Server", connection:socket.socket, addr:tuple[str, int], dbConn:psycopg2.extensions.connection):
        self.__server = server
        self.__addr = addr
        self.__dbConn = dbConn
        self.__conn = connection
        self.username : str = "Client"
        self.pingStatusOK = threading.Event()
    
    def pingUser(self):
        pingInterval = 15
        while self.pingStatusOK.wait(pingInterval):
            self.pingStatusOK.clear()
        print("Connection lost")
        self.__conn.close()

    def __loginUser(self, jsonPacket):
        queryCheckCredentials = """SELECT * FROM USERS WHERE name = (%s) AND password = (%s) """
        credentials=jsonPacket["properties"]
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                print(f"""Executing:\n{queryCheckCredentials}\nlogin: {credentials["login"]}\npassword: {credentials["password"]}""")
                cursor.execute(queryCheckCredentials, (credentials["login"], credentials["password"]))
                result = cursor.fetchone()
                if result is None:
                    self.__conn.send(make_message(TEXT["login_bad_password"],action=ACTION["login"]))
                    # self.__conn.close()
                    print(TEXT["login_fail"].format(username=credentials["login"],addr=self.__addr))
                    return -1
                self.__conn.send(make_message(TEXT["login_success"].format(username=credentials["login"]),action=ACTION["login"]))
        self.username = credentials["login"]
        self.__afterLoggedIn()

    def __registerUser(self, jsonPacket):
        queryAddUser = """INSERT INTO USERS (name, password) VALUES (%s, %s)"""
        credentials=jsonPacket["properties"]
        print(f"""Attempting execution of:\n{queryAddUser}\nlogin: {credentials["login"]}\npassword: {credentials["password"]}""")
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                try:
                    cursor.execute(queryAddUser, (credentials["login"], credentials["password"]))
                except psycopg2.errors.UniqueViolation:
                    # TODO:
                        # I have error here (rollback)
                    # cursor.rollback()
                    self.__conn.send(make_message(TEXT["register_user_taken"].format(username=credentials["login"]),action=ACTION["register"]))
                    return -1
        
            self.__conn.send(make_message(TEXT["register_success"].format(username=credentials["login"]),action=ACTION["register"]))
        self.username = credentials["login"]
        self.__afterLoggedIn()

    def __updateLastLogin(self):
        queryUpdateLastLoginTime="""UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE name=(%s)"""
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                print(f"""Executing:\n{queryUpdateLastLoginTime}\nuser: {self.username}""")
                cursor.execute(queryUpdateLastLoginTime, (self.username,))
    
    def __updateIP(self):
        queryUpdateLastKnownIP = """UPDATE users SET ip = (%s) WHERE name=(%s)"""
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                print(f"""Executing:\n{queryUpdateLastKnownIP}\nuser: {self.username}\naddr: {self.__addr}""")
                cursor.execute(queryUpdateLastKnownIP, (self.__addr[0], self.username))
    
    def __updatePulicKey(self, key):
        queryUpdatePubKey = """UPDATE users SET public_key = (%s) WHERE name=(%s)"""
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                print(f"""Executing:\n{queryUpdatePubKey}\nuser: {self.username}\npubKey: {key}""")
                cursor.execute(queryUpdatePubKey, (key, self.username))
        
    def getConn(self):
        return self.__conn
    
    def getUsername(self):
        return self.username
    
    def __handleMessage(self, jsonPacket):
        if jsonPacket["properties"]["sender"] not in [self.getUsername(), "Client"]:
            print("Spoofing attack suspected, packet discarded")
            self.__conn.send(make_message(TEXT["user_wrong_sender"].format(username=self.username),recipient=self.getUsername()))
            # print(jsonPacket["properties"]["sender"], self.getUsername())
            return 1
        
        msg=json.dumps(jsonPacket).encode()
        targetUsername = jsonPacket["properties"]["recipient"]

        if targetUsername in self.__server.listOnlineUsers():
            for i in self.__server.userConnMap[targetUsername]: # send message to all user session with this username
                i.getConn().send(msg)
            return 0

        self.__conn.send(make_message(TEXT["user_offline"].format(username=targetUsername),recipient=self.getUsername()))
        return 1

    def __afterLoggedIn(self):
        self.__server.insertUser(self)
        self.__updateLastLogin()
        self.__updateIP()
        #self.__updatePulicKey()
        threading.Thread(target=self.pingUser).start()

    def handleRequest(self,jsonPacket:dict):
        try:
            action = jsonPacket["action"]
            properties = jsonPacket["properties"]
        except KeyError:
            print(f"Key Error: Received invalid packet from {self.__addr}")
            self.__conn.send(make_message(TEXT["invalid_key"]))
        
        if action !="ping":
            print("handleRequest: ",jsonPacket)
        response = None
        match action:
            case "ping":
                #print("Received PING", jsonPacket)
                self.pingStatusOK.set()
            case "login":
                print("handleRequest Login: ", jsonPacket)
                self.__loginUser(jsonPacket)
            case "message":
                print("handleRequest message: ", jsonPacket)
                self.__handleMessage(jsonPacket)
            case "register":
                print("handleRequest register: ", jsonPacket)
                self.__registerUser(jsonPacket)
            case "listAllUsers":
                allUsers = str(self.__server.listAllUsers())
                response = make_message(content=allUsers,recipient=self.getUsername(),action=ACTION["listAllUsers"])
            case "listOnlineUsers":
                onlineUsers = str(self.__server.listOnlineUsers())
                response = make_message(content=onlineUsers,recipient=self.getUsername(),action=ACTION["listOnlineUsers"])
            case _:
                print("handleRequest Unknown: ", jsonPacket)
                response = make_message(TEXT["invalid_packet"])
        if response is not None:
            try:
                self.__conn.send(response)
            except BrokenPipeError:
                print(f"Unable to send respond - Broken Pipe. Response:{response.decode()}")
