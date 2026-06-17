import logging
import sys

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, g
from functools import wraps
from hashlib import sha256
import json
import os
import socket
import threading
from time import sleep
from server_messages import TEXT, ACTION, make_message
import ast


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
    force=True
)

log = logging.getLogger(__name__)

# wczytaj zmienne środowiskowe z pliku .env
load_dotenv()
# Ustawiamy nr. portu i adres IP serwera ze zmiennej środowiskowej aby ustanowić połączenie  
port = int(os.getenv('SRV_PORT'))
addr = os.getenv('SRV_ADDR')
server = socket.socket()
lock = threading.Lock()

user_connections: dict[str, socket.socket] = {} # pula połączeń
user_locks: dict[str, threading.Lock] = {} # pula locków

def get_server(username: str = None):
    key = username or session.get("username", "anonymous")
    
    if key not in user_connections or user_connections[key].fileno() == -1:
        s = socket.socket()
        try:
            s.connect((addr, port))
        except ConnectionRefusedError:
            return None
        s.recv(1024)  # welcome
        s.recv(1024)  # pubkey
        user_connections[key] = s
        user_locks[key] = threading.Lock()
    
    return user_connections[key]

def get_lock(username: str = None):
    key = username or session.get("username", "anonymous")
    return user_locks.get(key, threading.Lock())


def ping(username: str):
    while username in user_connections:
        try:
            srv = user_connections.get(username)
            if not srv or srv.fileno() == -1:
                break
            lck = user_locks.get(username, threading.Lock())
            with lck:
                packet = make_message(content="", action=ACTION["ping"], 
                                      sender=username, recipient="Server", mode="ping")
                srv.sendall(packet)
                #srv.recv(1024) - serwer nie odsyła nic po otrzymaniu ping, wątek by się zawiesił lub odebrał niepoprawny pakiet
            sleep(5)
        except Exception:
            log.warning(f"Ping failed for {username}")
            break

def send_and_receive(content: str, action: str = ACTION["message"], 
                     sender: str = "Client", recipient: str = "Server", 
                     mode: str = "Default") -> dict:
    username = session.get("username", "Client")
    srv = get_server(username)
    lck = get_lock(username)
    
    with lck:
        try:
            packet = make_message(
                content=content,
                action=action, 
                sender=session["username"], 
                recipient=recipient, mode=mode)
        except KeyError:
            packet = make_message(
                content=content,
                action=action, 
                sender=sender,
                recipient=recipient,
                mode=mode)
        srv.sendall(packet)
        response = srv.recv(1024)
        return json.loads(response.decode())

def serverRequest(val: str):
    rawJson = send_and_receive(content="", action=val, mode="Default")
    return rawJson["properties"]["content"]

def authCheck():
    try: 
        status = session["validAuth"]
    except KeyError:
        return False
    return status

def authRedirect(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not authCheck():
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

def confirmAuth(username: str):
    session["validAuth"]=True
    threading.Thread(target=ping, args=(username,), daemon=True).start()

app = Flask(__name__)
app.secret_key = os.urandom(32)

@app.teardown_appcontext
def close_server(exception):
    """Zamyka połączenie po każdym request jeśli użytkownik nie jest zalogowany."""
    server = g.pop('server', None)
    if server and not session.get('validAuth'):
        server.close()

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/logout")
def logout():
    username = session.get("username")
    session["validAuth"] = False
    session.pop("username", None)

    if username and username in user_connections:
        try:
            srv = user_connections[username]
            lck = user_locks.get(username, threading.Lock())
            with lck:
                packet = make_message(content="", action=ACTION["logout"],
                                      sender=username, recipient="Server")
                srv.sendall(packet)
        except Exception as e:
            log.warning(f"Logout send error: {e}")
        finally:
            user_connections[username].close()
            del user_connections[username]
            del user_locks[username]

    return redirect(url_for("index"))

@app.route("/login", methods=['GET','POST'])
def login():
    if request.method == 'GET':
        if authCheck():
            return redirect(url_for("welcome"))
        return render_template('login.html')
    username = request.form['user']
    password = request.form['passwd']
    if (username == ""):
        return render_template('login.html', USERNAME_ERR='Enter username')
    if (password == ""):
        return render_template('login.html', PASSWD_ERR='Enter passwd', PREV_USERNAME=username)
    
    session["username"] = username
    get_server(username)  # inicjalizuje socket
    
    passwdHash = sha256(password.encode('utf-8')).hexdigest()
    response = send_and_receive(
        content=passwdHash,
        action=ACTION["login"],
        sender=username, mode="login"
    )


    try:
        result = response["properties"]["content"]
    except KeyError:
        session.pop("username", None)
        return redirect(url_for("login"))
    if result[0] != "S":
        session.pop("username", None)
        return redirect(url_for("login"))
    
    #session["username"]=username
    confirmAuth(username)
    return redirect(url_for("welcome"))

@app.route("/register", methods=['GET','POST'])
def register():
    if request.method == 'GET':
        if authCheck():
            return redirect(url_for("welcome"))
        return render_template('register.html')
    username = request.form['user']
    password = request.form['passwd']
    password2 = request.form['passwd2']

    if (username == ""):
        return render_template('register.html', USERNAME_ERR='Enter username')
    if (password != password2):
        return render_template('register.html', PASSWD_ERR='Passwords don\'t match', PREV_USERNAME=username)
    if (password == ""):
        return render_template('register.html', PASSWD_ERR='Enter passwd', PREV_USERNAME=username)

    passwdHash = sha256(password.encode('utf-8')).hexdigest()
    response = send_and_receive(
    content=passwdHash,
    action=ACTION["register"],
    sender=username, mode="login"
    )

    log.info(response)
    try:
        result = response["properties"]["content"]
    except KeyError:
        session.pop("username", None)
        return redirect(url_for("login"))
    if result[0] != "S":
        session.pop("username", None)
        return redirect(url_for("login"))
    
    #session["username"]=username
    confirmAuth(username)
    return redirect(url_for("welcome"))

@app.route("/welcome", methods=['GET','POSt'])
@authRedirect
def welcome():
    return render_template("welcome.html",USER=session["username"])

@app.route("/message", methods=['GET','POST'])
@authRedirect
def message():
    if request.method == 'POST':
        recipient = request.form['user']
        msg = request.form['msg']
        send_and_receive(content=msg,action=ACTION["message"],sender=session["username"],recipient=recipient)
    onlineUsers=ast.literal_eval(serverRequest(ACTION["listOnlineUsers"]))
    allUsers=ast.literal_eval(serverRequest(ACTION["listAllUsers"]))
    offlineUsers=set(allUsers).difference(set(onlineUsers))
    return render_template("message.html", USERNAME=session["username"], online_users=onlineUsers,offlineUsers=offlineUsers,messages=[])

@app.post("/send_message")
@authRedirect
def send_message():
    pass

if __name__ == '__main__':
    app.run(
        host=os.getenv('FLASK_HOST', '127.0.0.1'),
        port=int(os.getenv('FLASK_PORT', 5000)),
        debug=True,
        use_reloader=False
    )