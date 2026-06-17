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
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
    force=True
)

log = logging.getLogger(__name__)

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
        while True:
            gotPing = self.pingStatusOK.wait(pingInterval)
            if not gotPing:
                log.warning("pingUser: timeout, closing connection user=%s addr=%s:%s", self.username, self.__addr[0], self.__addr[1])
                self.__conn.close()
                return
            self.pingStatusOK.clear()

    def __loginUser(self, jsonPacket):
        queryCheckCredentials = """SELECT * FROM USERS WHERE name = (%s) AND password = (%s) """
        credentials=jsonPacket["properties"]
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                log.debug(f"""Executing:\n{queryCheckCredentials}\nlogin: {credentials["login"]}\npassword: {credentials["password"]}""")
                cursor.execute(queryCheckCredentials, (credentials["login"], credentials["password"]))
                result = cursor.fetchone()
                if result is None:
                    self.__conn.send(make_message(TEXT["login_bad_password"],action=ACTION["login"]))
                    # self.__conn.close()
                    log.warning(TEXT["login_fail"].format(username=credentials["login"],addr=f"{self.__addr[0]}:{self.__addr[1]}"))
                    return -1
                if self.__checkAlreadyLogged(credentials["login"]): 
                    self.__conn.send(make_message(TEXT["login_already_online"].format(username=credentials["login"]),action=ACTION["login"]))
                    log.warning(TEXT["login_already_online"].format(username=credentials["login"]))
                    return -1
                self.__conn.send(make_message(TEXT["login_success"].format(username=credentials["login"]),action=ACTION["login"]))
        self.username = credentials["login"]
        self.__afterLoggedIn()

    def __checkAlreadyLogged(self,username:str) -> bool:
        return username in self.__server.listOnlineUsers()

    def __logoutUser(self, jsonPacket):
        log.debug(jsonPacket)
        user=self.getUsername()
        self.__server.userConnMap.pop(user)
        self.__conn.send(make_message(
            content=TEXT["logout_success"].format(username=user),
            action=ACTION["logout"],
            recipient=user
        ))
        self.__conn.close()

    def __registerUser(self, jsonPacket):
        queryAddUser = """INSERT INTO USERS (name, password) VALUES (%s, %s)"""
        credentials=jsonPacket["properties"]
        log.debug(f"""Attempting execution of:\n{queryAddUser}\nlogin: {credentials["login"]}\npassword: {credentials["password"]}""")
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
                log.debug(f"""Executing:\n{queryUpdateLastLoginTime}\nuser: {self.username}""")
                cursor.execute(queryUpdateLastLoginTime, (self.username,))
    
    def __updateIP(self):
        queryUpdateLastKnownIP = """UPDATE users SET ip = (%s) WHERE name=(%s)"""
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                log.debug(f"""Executing:\n{queryUpdateLastKnownIP}\nuser: {self.username}\naddr: {self.__addr}""")
                cursor.execute(queryUpdateLastKnownIP, (self.__addr[0], self.username))
    
    def __updatePulicKey(self, key):
        queryUpdatePubKey = """UPDATE users SET public_key = (%s) WHERE name=(%s)"""
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                log.debug(f"""Executing:\n{queryUpdatePubKey}\nuser: {self.username}\npubKey: {key}""")
                cursor.execute(queryUpdatePubKey, (key, self.username))
        
    def getConn(self):
        return self.__conn
    
    def getUsername(self):
        return self.username
    
    def __isSpoofing(self,jsonPacket) -> bool:
        log.debug("Check Spoofing: %s as %s",self.getUsername(),jsonPacket["properties"]["sender"] )
        return jsonPacket["properties"]["sender"] != self.getUsername()

    def __handleMessage(self, jsonPacket):
        if self.__isSpoofing(jsonPacket):
            log.warning(TEXT["server_spoofing"].format(method="__handleMessage"))
            log.warning(TEXT["user_wrong_sender"].format(username=jsonPacket["properties"]["sender"]))
            self.__conn.send(make_message(TEXT["user_wrong_sender"].format(username=jsonPacket["properties"]["sender"]),recipient=self.getUsername()))
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
            log.warning(f"Key Error: Received invalid packet from {f"{self.__addr[0]}:{self.__addr[1]}"}")
            self.__conn.send(make_message(TEXT["invalid_key"]))
            action = "error"
        #if action !="ping":
        #   log.debug("handleRequest: ",jsonPacket)
        response = None
        match action:
            case "ping":
                log.debug("Received PING: %s", jsonPacket)
                self.pingStatusOK.set()
            case "login":
                log.debug("handleRequest Login: %s", jsonPacket)
                self.__loginUser(jsonPacket)
            case "message":
                log.debug("handleRequest message: %s", jsonPacket)
                self.__handleMessage(jsonPacket)
            case "logout":
                #TODO:
                    # logout w sumie nie potrzebuje info o nazwie uzytkownika, on jest samym soba
                log.debug("handleRequest logout: %s", jsonPacket)
                self.__logoutUser(jsonPacket)
            case "register":
                log.debug("handleRequest register: %s", jsonPacket)
                self.__registerUser(jsonPacket)
            case "listAllUsers":
                allUsers = str(self.__server.listAllUsers())
                response = make_message(content=allUsers,recipient=self.getUsername(),action=ACTION["listAllUsers"])
            case "listOnlineUsers":
                onlineUsers = str(self.__server.listOnlineUsers())
                response = make_message(content=onlineUsers,recipient=self.getUsername(),action=ACTION["listOnlineUsers"])
            case _:
                log.debug("handleRequest Unknown: %s", jsonPacket)
                response = make_message(TEXT["invalid_packet"])
        if response is not None:
            try:
                if self.__isSpoofing(jsonPacket):
                    log.warning("%s is spoofing: %s",self.getUsername(), jsonPacket)
                    self.__conn.send(make_message(TEXT["user_wrong_sender"].format(username=jsonPacket["properties"]["sender"]),recipient=self.getUsername()))
                else:
                    log.debug("msg: %s", jsonPacket)
                    log.debug("response: %s", response)
                    self.__conn.send(response)

            except BrokenPipeError:
                log.warning(TEXT["BrokenPipeError"].format(response=response.decode()))


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
