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
from api.authentication import JWTAuthentication
from api.models import (DailyQuestions,Reactions, UserStreak)
from TellMe import py_jwt_token


class HomeViews(APIView):
    permission_classes = (IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def post(self, request):
        user = request.user
        current_time_str = request.data.get('current_time')
        page = int(request.data.get('page', 1))
        page_size = int(request.data.get('page_size', 10))

        if not current_time_str:
            return Response({"error": "Missing 'current_time'"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            current_date = datetime.strptime(current_time_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"error": "Invalid 'current_time'. Format should be YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            question = DailyQuestions.objects.get(
                question_for__date=current_date,
                status__id=1
            )
        except DailyQuestions.DoesNotExist:
            return Response({"message": "No question found for this date."}, status=status.HTTP_204_NO_CONTENT)

        # 🧠 Update user's streak
        streak_obj, _ = UserStreak.objects.get_or_create(user=user)
        streak_obj.update_streak(timezone.now())

        # Reactions pagination
        reactions = Reactions.objects.filter(question=question).order_by("-created_at")
        paginator = Paginator(reactions, page_size)
        paginated = paginator.get_page(page)

        serialized_reactions = []
        for reaction in paginated:
            serialized_reactions.append({
                "user_id": reaction.user.id,
                "username": reaction.user.username,
                "voice_slug": reaction.voice_slug,
                "transcript": reaction.transcript,
                "like_count": reaction.like_count,
                "created_at": reaction.created_at,
                "is_reply": reaction.parent_reaction is not None,
                "parent_reaction_id": reaction.parent_reaction.id if reaction.parent_reaction else None
            })

        return Response({
            "date": current_date.isoformat(),
            "question_id": question.id,
            "question": question.question,
            "like_count": question.like_count,
            "comment_count": question.comment_count,
            "reactions": serialized_reactions,
            "total_pages": paginator.num_pages,
            "current_page": page,
            "streak": {
                "current_streak": streak_obj.current_streak,
                "last_active": streak_obj.last_active
            }
        }, status=status.HTTP_200_OK)