import jwt, datetime
from django.conf import settings
from django.utils import timezone



def create_token(payload):
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return token

def generate_tokens(user):
    now = timezone.now()
    payload = {'email':user.email, "user_id":user.id, "exp":now + datetime.timedelta(minutes=120)}
    access_token = create_token(payload)
    refresh_payload = {'email':user.email, "user_id":user.id, "exp":now + datetime.timedelta(days=7)}
    refresh_token = create_token(refresh_payload)
    return {
        'access': access_token,
        'refresh': refresh_token
    }