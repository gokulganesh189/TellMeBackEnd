from celery import shared_task
from django.core.mail import send_mail


@shared_task
def send_welcome_email(email, name):
    subject = 'Welcome to Our Platform'
    message = f"Hi {name},\n\nThank you for registering!"
    send_mail(subject, message, 'gokulganesh189@gmail.com', [email])