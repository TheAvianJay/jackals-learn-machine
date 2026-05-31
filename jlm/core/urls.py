from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClassRoomViewSet, StudentClassRoomViewSet,
    FeedbackViewSet, MeView,
    PreferenceView, NotificationListView,
    NotificationMarkReadView, UnreadCountView,
)

router = DefaultRouter()
router.register("classes", ClassRoomViewSet, basename="classes")
router.register("student/classes", StudentClassRoomViewSet, basename="student-classes")
router.register("feedbacks", FeedbackViewSet, basename="feedbacks")

urlpatterns = [
    path("me/", MeView.as_view()),
    path("preferences/", PreferenceView.as_view()),
    path("notifications/", NotificationListView.as_view()),
    path("notifications/unread/", UnreadCountView.as_view()),
    path("notifications/mark-all-read/", NotificationMarkReadView.as_view()),
    path("notifications/<int:pk>/mark-read/", NotificationMarkReadView.as_view()),
    path("", include(router.urls)),
]