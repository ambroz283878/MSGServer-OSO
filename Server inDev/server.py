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

import bcrypt


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
        queryCheckCredentials = """SELECT password FROM USERS WHERE name = (%s) """
        credentials=jsonPacket["properties"]
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                log.debug(f"""Executing:\n{queryCheckCredentials}\nlogin: {credentials["login"]}\npassword: {credentials["password"]}""")
                cursor.execute(queryCheckCredentials, (credentials["login"],))
                result = cursor.fetchone()
                print(f"result {result}")
                if result is None:
                    self.__conn.send(make_message(TEXT["login_bad_password"],action=ACTION["login"]))
                    # self.__conn.close()
                    log.warning(TEXT["login_fail"].format(username=credentials["login"],addr=f"{self.__addr[0]}:{self.__addr[1]}"))
                    return -1
                if not bcrypt.checkpw(credentials["password"].encode("utf-8"),result[0].encode("utf-8")):
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
        
        password_hash = bcrypt.hashpw(
            credentials["password"].encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")


        log.debug(f"""Attempting execution of:\n{queryAddUser}\nlogin: {credentials["login"]}\npassword: {credentials["password"]}""")
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                try:
                    cursor.execute(queryAddUser, (credentials["login"], password_hash))
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
                self.__conn.send(make_message(key,action=ACTION["setPubKey"],recipient=self.username))



    def __getPulicKey(self, user):
        queryGetPubKey = """SELECT public_key FROM USERS WHERE name = (%s)"""
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                log.debug(f"""Executing:\n{queryGetPubKey}\nuser: {user}""")
                cursor.execute(queryGetPubKey, (user,))
                result = cursor.fetchone()
                if result is None:
                    self.__conn.send(make_message(TEXT["db_public_key_issue"].format(user=user),action=ACTION["fetchPubKey"],recipient=self.username))
                    log.warning("%s from %s %s:%s", TEXT["db_public_key_issue"].format(user=user), self.username, self.__addr[0],self.__addr[1])
                    return -1
                self.__conn.send(make_message(result[0],action=ACTION["fetchPubKey"],recipient=self.username))

    def getConn(self):
        return self.__conn
    
    def getUsername(self):
        return self.username
    
    def __isSpoofing(self,jsonPacket) -> bool:
        log.debug("Check Spoofing: %s as %s : %s",self.getUsername(),jsonPacket["properties"]["sender"],jsonPacket["properties"]["sender"] != self.getUsername() )
        return jsonPacket["properties"]["sender"] != self.getUsername()

    def __handleMessage(self, jsonPacket):
        # if self.__isSpoofing(jsonPacket):
        #     log.warning(TEXT["server_spoofing"].format(method="__handleMessage"))
        #     log.warning(TEXT["user_wrong_sender"].format(username=jsonPacket["properties"]["sender"]))
        #     self.__conn.send(make_message(TEXT["user_wrong_sender"].format(username=jsonPacket["properties"]["sender"]),recipient=self.getUsername()))
        #     return 1
        
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
        response = None
        
        handleRequest_log_str = f"handleRequest {action} from {self.username} {self.__addr[0]}:{self.__addr[1]} : {jsonPacket} "
        
        action_login_req = ["message","listAllUsers","listOnlineUsers","setPubKey","sendPubKey","fetchPubKey"]

        if action in action_login_req and self.__isSpoofing(jsonPacket):
            log.warning("%s is spoofing: %s",self.getUsername(), jsonPacket)
            self.__conn.send(make_message(TEXT["user_wrong_sender"].format(username=properties["sender"]),recipient=self.getUsername()))
        else:
            match action:
                case "ping":
                    log.debug(handleRequest_log_str)
                    self.pingStatusOK.set()
                case "login":
                    log.debug(handleRequest_log_str)
                    self.__loginUser(jsonPacket)
                case "logout":
                    log.debug(handleRequest_log_str)
                    self.__logoutUser(jsonPacket)
                case "register":
                    log.debug(handleRequest_log_str)
                    self.__registerUser(jsonPacket)


                case "setPubKey":
                    log.debug(handleRequest_log_str)
                    self.__updatePulicKey(properties["content"])
                case "fetchPubKey":
                    log.debug(handleRequest_log_str)
                    self.__getPulicKey(properties["content"])
                case "message":
                    log.debug(handleRequest_log_str)
                    self.__handleMessage(jsonPacket)
                case "listAllUsers":
                    log.debug(handleRequest_log_str)
                    allUsers = str(self.__server.listAllUsers())
                    response = make_message(content=allUsers,recipient=self.getUsername(),action=ACTION["listAllUsers"])
                case "listOnlineUsers":
                    log.debug(handleRequest_log_str)
                    onlineUsers = str(self.__server.listOnlineUsers())
                    response = make_message(content=onlineUsers,recipient=self.getUsername(),action=ACTION["listOnlineUsers"])
                
                case _:
                    log.debug("Unknown %s", handleRequest_log_str)
                    response = make_message(TEXT["invalid_packet"])
            
        if response is not None:
            try:
                log.debug("msg: %s", jsonPacket)
                log.debug("response: %s", response)
                self.__conn.send(response)

            except BrokenPipeError:
                log.warning(TEXT["BrokenPipeError"].format(response=response.decode()))


class Server():
    def __init__(self):
        load_dotenv()

        # Be quiet Pylance

        db_url = os.getenv("DATABASE_URL")
        port_str = os.getenv("SRV_PORT")
        max_conn_str = os.getenv("SRV_MAX_CONN")

        if not db_url:
            raise ValueError("DATABASE_URL is missing or empty")
        if not port_str:
            raise ValueError("SRV_PORT is missing or empty")
        if not max_conn_str:
            raise ValueError("SRV_MAX_CONN is missing or empty")

        try:
            port = int(port_str)
        except ValueError as e:
            raise ValueError(f"Invalid SRV_PORT value: {port_str}") from e
        try:
            max_client_count = int(max_conn_str)
        except ValueError as e:
            raise ValueError(f"Invalid SRV_MAX_CONN value: {max_conn_str}") from e

        self.dbUrl = db_url
        self.port = port
        self.maxClientCount = max_client_count
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
                msg = self.validateJsonPacket(conn.recv(1024).decode(),addr)
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


    def validateJsonPacket(self, msg: str,addr:tuple[str, int])->Optional[dict[str, Any]]:
        try:
            packet = json.loads(msg)
            return packet
        except json.JSONDecodeError as e:
            log.warning(
                "Invalid JSON from client %s:%s: error=%s raw_message=%r",
                addr[0],
                addr[1],
                e,
                msg
            )
            return None
