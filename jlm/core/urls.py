from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClassRoomViewSet, StudentClassRoomViewSet, FeedbackViewSet
from .views import MeView

router = DefaultRouter()
router.register("classes", ClassRoomViewSet, basename="classes")
router.register("student/classes", StudentClassRoomViewSet, basename="student-classes")

router.register("feedbacks", FeedbackViewSet, basename="feedbacks")

urlpatterns = [
    path("me/", MeView.as_view()),
    path("", include(router.urls)),
]
