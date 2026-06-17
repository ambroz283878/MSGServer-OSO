import json
import logging
import socket
import sys
import threading
import time
from typing import TYPE_CHECKING
import psycopg2
#import keyExchange
import psycopg2.extensions
from server_messages import ACTION, make_message, TEXT

if TYPE_CHECKING:
    from server import Server

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
        while self.pingStatusOK.wait(pingInterval):
            self.pingStatusOK.clear()
        log.warning("pingUser, closing connection user=%s addr=%s:%s", self.username, self.__addr[0], self.__addr[1])
        self.__conn.close()

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
                log.debug("Received PING", jsonPacket)
                self.pingStatusOK.set()
            case "login":
                log.info("handleRequest Login: ", jsonPacket)
                self.__loginUser(jsonPacket)
            case "message":
                log.info("handleRequest message: ", jsonPacket)
                self.__handleMessage(jsonPacket)
            case "logout":
                #TODO:
                    # logout w sumie nie potrzebuje info o nazwie uzytkownika, on jest samym soba
                log.info("handleRequest logout:", jsonPacket)
                self.__logoutUser(jsonPacket)
            case "register":
                log.info("handleRequest register: ", jsonPacket)
                self.__registerUser(jsonPacket)
            case "listAllUsers":
                allUsers = str(self.__server.listAllUsers())
                response = make_message(content=allUsers,recipient=self.getUsername(),action=ACTION["listAllUsers"])
            case "listOnlineUsers":
                onlineUsers = str(self.__server.listOnlineUsers())
                response = make_message(content=onlineUsers,recipient=self.getUsername(),action=ACTION["listOnlineUsers"])
            case _:
                log.info("handleRequest Unknown: ", jsonPacket)
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
