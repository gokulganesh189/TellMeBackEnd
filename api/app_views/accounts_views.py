from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from api.serializers import RegisterSerializer, LoginSerializer
from rest_framework.response import Response
from rest_framework import status
from api.tasks import email_task
from TellMe import py_jwt_token


class RegisterUser(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            email_task.send_welcome_email.delay(user.email, user.name)  # Celery task
            return Response({"message": "User registered successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            token = py_jwt_token.generate_tokens(user)
            return Response({
                'refresh': token.get('refresh'),
                'access': token.get('access'),
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'name': user.name
                }
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)