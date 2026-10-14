import os, hmac, hashlib
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from key import salt

load_dotenv()
SECRET = os.environ['SECRET_KEY']
_serializer = URLSafeTimedSerializer(SECRET, salt=salt)


def encode(data):
    return _serializer.dumps(data)


def decode(data, max_age=3600):
    # raises an error if the token is tampered with or too old
    return _serializer.loads(data, max_age=max_age)


# The token is signed but readable, so we never put the plain OTP in it, only a hash.
def hash_otp(otp):
    return hmac.new(SECRET.encode(), otp.encode(), hashlib.sha256).hexdigest()


def otp_matches(stored_hash, typed_otp):
    return hmac.compare_digest(stored_hash, hash_otp(typed_otp.strip()))
