from django.contrib.auth import get_user_model
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ClassRoom, Enrollment, Question
from .serializers import ClassRoomSerializer, AddStudentSerializer, QuestionSerializer

User = get_user_model()


class IsTeacher(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "TEACHER"


class ClassRoomViewSet(viewsets.ModelViewSet):
    serializer_class = ClassRoomSerializer
    permission_classes = [IsTeacher]

    def get_queryset(self):
        return ClassRoom.objects.filter(teacher=self.request.user)

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)

    @action(detail=True, methods=["post"], url_path="add_student")
    def add_student(self, request, pk=None):
        classroom = self.get_object()

        ser = AddStudentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        username = ser.validated_data["username"]
        student = User.objects.get(username=username)

        Enrollment.objects.get_or_create(classroom=classroom, student=student)
        return Response({"detail": "Student added"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["delete"], url_path=r"remove-student/(?P<student_id>\d+)")
    def remove_student(self, request, pk=None, student_id=None):
        classroom = self.get_object()
        Enrollment.objects.filter(classroom=classroom, student_id=student_id).delete()
        return Response({"detail": "Student removed"}, status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="questions")
    def questions(self, request, pk=None):
        classroom = self.get_object()

        if request.method == "GET":
            qs = Question.objects.filter(classroom=classroom).order_by("-created_at")
            return Response(QuestionSerializer(qs, many=True).data)

        ser = QuestionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save(classroom=classroom, created_by=request.user)
        return Response(ser.data, status=status.HTTP_201_CREATED)


class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [IsTeacher]

    def get_queryset(self):
        return Question.objects.filter(created_by=self.request.user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)