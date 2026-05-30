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

}
ACTION = {
    "register": "register",
    "message": "message",
    "login": "login",
    "publicKey": "publicKey",
    "listAllUsers": "listAllUsers"
}

def make_message(
    content: str,
    recipient: str = "Client",
    sender: str = "Server",
    action: str = ACTION["message"]
) -> bytes:
    return json.dumps({
        "action": action,
        "properties": {
            "sender": sender,
            "recipient": recipient,
            "content": content
        }
    }).encode()