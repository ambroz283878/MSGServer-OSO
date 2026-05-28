import psycopg2
class User():
    def __init__(self, connection, addr, dbConn):
        self.__addr = addr
        self.__dbConn = dbConn
        self.__conn = connection
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