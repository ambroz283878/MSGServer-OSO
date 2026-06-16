from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session
from functools import wraps
from hashlib import sha256
import json
import os
import socket
import threading
from time import sleep
from server_messages import TEXT, ACTION, make_message
import ast

# wczytaj zmienne środowiskowe z pliku .env
load_dotenv()
# Ustawiamy nr. portu i adres IP serwera ze zmiennej środowiskowej aby ustanowić połączenie  
port = int(os.getenv('SRV_PORT'))
addr = os.getenv('SRV_ADDR')
server = socket.socket()
lock = threading.Lock()
# Próba połączenia do serwera uywając podanych danych
try:
    server.connect((addr, port))
except ConnectionRefusedError:
    print("Unable to connect to server")
    exit(-1)

print(server.recv(1024))
print(server.recv(1024))
def ping():
    while threading.active_count() > 1:
        try:
            send_and_receive(mode="ping", sender="Client", recipient="Server")
            sleep(5)
        except:
            print("Connection lost")
            exit(-1)

def send_and_receive(content: str, action: str = ACTION["message"], sender: str = "Client", recipient: str = "Server", mode: str = "Default") -> dict:
    with lock:
        packet = make_message(content=content, action=action, sender=sender, recipient=recipient, mode=mode)
        server.sendall(packet)
        response = server.recv(1024)
        return json.loads(response.decode())

def serverRequest(val: str):
    rawJson = send_and_receive(content="", action=val)
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

def confirmAuth():
    session["validAuth"]=True

app = Flask(__name__)
app.secret_key = os.urandom(32)
threading.Thread(target=ping,args=()).start()

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/logout")
def logout():
    session["validAuth"]=False
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
    
    passwdHash = sha256(password.encode('utf-8')).hexdigest()
    response = send_and_receive(
    content=passwdHash,
    action=ACTION["login"],
    sender=username, mode="login"
    )

    try:
        result = response["properties"]["content"]
    except KeyError:
        return redirect(url_for("login"))
    if result[0] != "S":
        return redirect(url_for("login"))
    session["username"]=username
    confirmAuth()
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

    print(response)
    try:
        result = response["properties"]["content"]
    except KeyError:
        return redirect(url_for("register"))
    if result[0] != "S":
        return redirect(url_for("register"))
    session["username"]=username
    confirmAuth()
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
    onlineUsers=eval(serverRequest(ACTION["listOnlineUsers"]))
    allUsers=eval(serverRequest(ACTION["listAllUsers"]))
    return render_template("message.html", USERNAME=session["username"], online_users=onlineUsers,all_users=allUsers,messages=[])

@app.post("/send_message")
@authRedirect
def send_message():
    pass

if __name__ == '__main__':
    app.run(
        host=os.getenv('FLASK_HOST', '0.0.0.0'),
        port=int(os.getenv('FLASK_PORT', 5000)),
        debug=True,
        use_reloader=False
    )