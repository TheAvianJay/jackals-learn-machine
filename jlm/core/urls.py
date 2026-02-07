from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClassRoomViewSet, QuestionViewSet

router = DefaultRouter()
router.register("classes", ClassRoomViewSet, basename="classes")
router.register("questions", QuestionViewSet, basename="questions")

urlpatterns = [
    path("", include(router.urls)),
]
