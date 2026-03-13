from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClassRoomViewSet, QuestionViewSet, StudentClassRoomViewSet
from .views import MeView

router = DefaultRouter()
router.register("classes", ClassRoomViewSet, basename="classes")
router.register("questions", QuestionViewSet, basename="questions")
router.register("student/classes", StudentClassRoomViewSet, basename="student-classes")

urlpatterns = [
    path("me/", MeView.as_view()),
    path("", include(router.urls)),
]

