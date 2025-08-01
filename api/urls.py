from api.app_views import accounts_views, dash_views, question_views, reactions_views
from django.urls import path

urlpatterns = [
    path('register/', accounts_views.RegisterUser.as_view(), name="register a new user"),
    path('login/', accounts_views.LoginAPIView.as_view(), name="login a user"),
    path('home/', dash_views.HomeViews.as_view(), name="home views"),
    path('add-question/', question_views.AddQuestion.as_view(), name="add questions"),
    path('like-question/', question_views.LikeQuestion.as_view(), name="like question"),
    path('like-comment/', question_views.LikeComment.as_view(), name="like comment"),
    path('add-reaction-test/', reactions_views.AddReactionTest.as_view(), name="add reaction"),
    # path('add-reaction/', reactions_views.AddReaction.as_view(), name="add reaction")
]
