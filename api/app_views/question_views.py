from datetime import datetime
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.core.paginator import Paginator
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from api.serializers import RegisterSerializer, LoginSerializer
from rest_framework.response import Response
from rest_framework import status
from api.tasks import email_task
from api.authentication import JWTAuthentication, IsAdminUser
from api.models import (DailyQuestions, UserStreak, QuestionLike, Reactions, ReactionLike)
from TellMe import py_jwt_token


class AddQuestion(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)
    authentication_classes = (JWTAuthentication,)  # your custom one

    def post(self, request):
        question_text = request.data.get('question')
        question_for_str = request.data.get('question_for')  # format: "YYYY-MM-DD"

        if not question_text or not question_for_str:
            return Response({"error": "Missing 'question' or 'question_for'"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            question_for_date = datetime.strptime(question_for_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"error": "Invalid 'question_for' format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if a question already exists for the day
        if DailyQuestions.objects.filter(question_for__date=question_for_date, status__id=1).exists():
            return Response({"error": f"A question already exists for {question_for_date}"}, status=status.HTTP_409_CONFLICT)

        question = DailyQuestions.objects.create(
            question=question_text,
            created_by=request.user,  # you'll need this field in your model
            question_for=question_for_date,
            status_id=1  # assuming 1 is 'active'
        )

        return Response({"message": f"Question for {question_for_date} added successfully."}, status=status.HTTP_201_CREATED)


class LikeQuestion(APIView):
    permission_classes = (IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)  # your custom one
    
    def post(self, request):
        user = request.user
        question_id = request.data.get("question_id")
        is_like = request.data.get('is_like')
        is_unliked = request.data.get("is_unliked")
        if not question_id and (is_like or is_unliked):
            return Response({"error": "Missing question_id"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            question_object = DailyQuestions.objects.get(id=question_id)
        except DailyQuestions.DoesNotExist:
            return Response({"error": "Question does not exists"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            like_obj = QuestionLike.objects.get(user=user, question_id=question_id)
        except QuestionLike.DoesNotExist:
            like_obj = None

        # LIKE
        if is_like and not is_unliked:
            if like_obj and like_obj.status_id == 1:
                return Response({"error": "You have already liked this question."}, status=status.HTTP_400_BAD_REQUEST)

            question_object.like_count += 1
            QuestionLike.objects.update_or_create(
                user=user,
                question_id=question_id,
                defaults={'status_id': 1}
            )

        # UNLIKE
        elif is_unliked and not is_like:
            if like_obj and like_obj.status_id == 1:
                if question_object.like_count > 0:
                    question_object.like_count -= 1
                QuestionLike.objects.update_or_create(
                    user=user,
                    question_id=question_id,
                    defaults={'status_id': 2}
                )
            else:
                return Response({"error": "You haven't liked this question yet."}, status=status.HTTP_400_BAD_REQUEST)

        else:
            return Response({"error": "Invalid value"}, status=status.HTTP_400_BAD_REQUEST)

        question_object.save()

        # Update user streak
        streak_obj, _ = UserStreak.objects.get_or_create(user=user)
        streak_obj.update_streak(timezone.now())

        return Response({"success": "Action successful"}, status=status.HTTP_200_OK)
    

class LikeComment(APIView):
    permission_classes = (IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)  # your custom one
    
    def post(self, request):
        user = request.user
        question_id = request.data.get("question_id")
        reaction_id = request.data.get("reaction_id")
        is_like = request.data.get('is_like')
        is_unliked = request.data.get("is_unliked")
        
        if not question_id and not reaction_id and (is_like or is_unliked):
            return Response({"error": "Missing question_id"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            question_object = DailyQuestions.objects.get(id=question_id)
        except DailyQuestions.DoesNotExist:
            return Response({"error": "Question does not exists"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            reaction_obj = Reactions.objects.get(id=reaction_id)
        except Reactions.DoesNotExist:
            reaction_obj = None
            
        try:
            reaction_like_obj = ReactionLike.objects.get(user=user, question_id=question_id, reaction_id=reaction_obj.id)
        except ReactionLike.DoesNotExist:
            reaction_like_obj = None
            
        #LIKE
        if is_like and not is_unliked:
            if reaction_like_obj and reaction_like_obj.status_id == 1:
                return Response({"error": "You have already liked this reaction."}, status=status.HTTP_400_BAD_REQUEST)

            reaction_obj.like_count += 1
            
            QuestionLike.objects.update_or_create(
                user=user,
                question_id=question_id,
                defaults={'status_id': 1}
            )