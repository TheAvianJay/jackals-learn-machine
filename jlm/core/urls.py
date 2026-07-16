from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClassRoomViewSet, StudentClassRoomViewSet,
    FeedbackViewSet, MeView,
    PreferenceView, NotificationListView,
    NotificationMarkReadView, UnreadCountView,
    ExcuseView,
    FlagProfilePictureView, FlaggedProfilesView, ResolveFlagView,
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
    path(
        "classes/<int:classroom_id>/assignments/<int:assignment_id>/excuses/",
        ExcuseView.as_view(),
    ),
    path(
        "classes/<int:classroom_id>/assignments/<int:assignment_id>/excuses/<int:student_id>/",
        ExcuseView.as_view(),
    ),
    path("", include(router.urls)),
    path("profile/<int:user_id>/flag/", FlagProfilePictureView.as_view()),
    path("flagged-profiles/", FlaggedProfilesView.as_view()),
    path("flagged-profiles/<int:user_id>/resolve/", ResolveFlagView.as_view()),
]