# server_messages.py
import json

TEXT = {
    "welcome": "Thank you for connecting!",
    "ping": "Hello!!!!",
    "invalid_packet": "Wrong Json format!",
    "invalid_key":"Received JSON with invalid key",
    "register_user_taken": "Username {username} already taken!",
    "register_success": "Succesfully registered as {username}!",
    "login_success": "Succesfully logged in as {username}!",
    "login_fail": "Failed login attempt into account {username} from {addr}",
    "login_bad_password": "Bad password!",
    "login_already_online": "Failed login attempt into account {username}, already logged in",
    "logout_success": "Succesfully logged out as {username}!",
    "user_offline": "Recipient {username} is offline",
    "user_wrong_sender": "Sender {username} is not accepted by Server!",
    "BrokenPipeError": "Unable to send respond - Broken Pipe. Response:{response}",
    "server_close_connection": "Closing connection: {user}",
    "temp_response": "You sneaky bastard... -> {reason}",


}
ACTION = {
    "register": "register",
    "message": "message",
    "ping": "ping",
    "login": "login",
    "logout": "logout",
    "fetchPubKey": "fetchPubKey",
    "setPubKey": "setPubKey", # z klienta do serwera, klient ustawia swój klucz publiczny w bazie danych
    "sendPubKey": "sendPubKey", # z serwera do klienta, odpowiada na request o klucz publiczny innego klienta
    "listAllUsers": "listAllUsers",
    "listOnlineUsers": "listOnlineUsers"
}

def make_message(
    content: str = "",
    recipient: str = "Client",
    sender: str = "Server",
    action: str = ACTION["message"],
    mode: str = "msg"
) -> bytes:
    match mode:
        case "login":
            return json.dumps({
                "action": action,
                "properties": {
                    "login":sender,
                    "password":content
                }
            }).encode()
        case "logout":
            return json.dumps({
                "action": action,
                "properties": {
                    "login":sender
                }
            }).encode()
        
        case "ping":
            return json.dumps({
                "action": ACTION["ping"],
                "properties": {
                    "sender": sender,
                    "recipient": recipient,
                    "content": TEXT["ping"]
                }
            }).encode()
        case _:
            return json.dumps({
                "action": action,
                "properties": {
                    "sender": sender,
                    "recipient": recipient,
                    "content": content
                }
            }).encode()