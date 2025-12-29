
import jwt
import bcrypt
import datetime
import logging
from src.db_manager import DBManager

SECRET_KEY = "super_secret_key_rsi_power_zone" # In prod, use env var
ALGORITHM = "HS256"
TOKEN_EXPIRATION_HOURS = 72

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_token(username: str) -> str:
    expiration = datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXPIRATION_HOURS)
    payload = {
        "sub": username,
        "exp": expiration
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token

def verify_token(token: str) -> str:
    """Returns username if valid, else None"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def init_default_user():
    """Ensure default user longman6 exists"""
    db = DBManager()
    user = db.get_user("longman6")
    if not user:
        logging.info("Creating default user: longman6")
        hashed = hash_password("14501450")
        db.create_user("longman6", hashed)
