import psycopg2
import keyExchange

class User():
    def __init__(self,server, connection, addr, dbConn):
        self.__server = server
        self.__addr = addr
        self.__dbConn = dbConn
        self.__conn = connection
        self.__serverKeys = keyExchange.keyGen()
        
    def __loginUser(self, jsonPacket):
        queryCheckCredentials = """SELECT * FROM USERS WHERE user = (%s) AND password = (%s) """
        credentials=jsonPacket["properties"]
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                print(f"""Executing:\n{queryCheckCredentials}\nlogin: {credentials["login"]}\npassword: {credentials["password"]}""")
                cursor.execute(queryCheckCredentials, (credentials["login"], credentials["password"]))
                result = cursor.fetchone()
                if result is None:
                    self.__conn.send('Bad password!'.encode())
                    self.__conn.close()
                    print(f"Failed login attempt into account {credentials["login"]} from {self.__addr}")
                    return -1
                self.__conn.send(f'Succesfully logged in as {credentials["login"]}!'.encode())
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
                    cursor.rollback()
                    self.__conn.send('Username already taken!'.encode())
                    return -1
        
            self.__conn.send(f'Succesfully registered as {credentials["login"]}!'.encode())
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
    
    def __updatePulicKey(self):
        queryUpdatePubKey = """UPDATE users SET public_key = (%s) WHERE name=(%s)"""
        with self.__dbConn:
            with self.__dbConn.cursor() as cursor:
                print(f"""Executing:\n{queryUpdatePubKey}\nuser: {self.username}\npubKey: {self.peerPubKey}""")
                cursor.execute(queryUpdatePubKey, (self.peerPubKey, self.username))
    
    def getSrvPubKey(self):
        return self.__serverKeys["pubKey"]
    
    def setPeerPubKey(self, key):
        self.peerPubKey = key
    
    def userAction(self, jsonPacket):
        try:
            action = jsonPacket["action"]
            properties = jsonPacket["properties"]
        except KeyError:
            print(f"Received invalid packet from {self.addr}")
            self.conn.send("Received invalid packet".encode())
        
        match action:
            case _:
                self.conn.send("Invalid action".encode())

    def getConn(self):
        return self.__conn
    
    def getUsername(self):
        return self.username

    def forwardMessage(self, message):
        self.__conn.send(message.encode())
    
    def __afterLoggedIn(self):
        self.__server.insertUser(self)