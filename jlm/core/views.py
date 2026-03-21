from django.contrib.auth import get_user_model
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ClassRoom, Enrollment, Question, Submission, SubmissionAnswer
from .serializers import (
    AssignmentSerializer,
    ClassRoomSerializer,
    AddStudentSerializer,
    QuestionSerializer,
    StudentQuestionSerializer,
    SubmissionSerializer,
    SubmitPayloadSerializer,
)
from django.utils import timezone
User = get_user_model()

class IsTeacher(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "TEACHER"

class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({
            "id": request.user.id,
            "username": request.user.username,
            "role": request.user.role,
        })

class ClassRoomViewSet(viewsets.ModelViewSet):
    serializer_class = ClassRoomSerializer
    permission_classes = [IsTeacher]

    def get_queryset(self):
        return ClassRoom.objects.filter(teacher=self.request.user)

    def _parse_answers(self, request):
        raw = request.data.get("answers", None)

        if isinstance(raw, dict):
            answers_dict = {str(k): str(v) for k, v in raw.items()}
        elif isinstance(raw, list):
            answers_dict = {}
            for item in raw:
                if isinstance(item, dict) and "question" in item and "response" in item:
                    answers_dict[str(item["question"])] = str(item["response"])
                else:
                    raise ValueError("Invalid answers list format. Use {question, response} objects.")
        else:
            raise ValueError("answers must be an object (dict) or a list.")

        if not answers_dict:
            raise ValueError("answers cannot be empty.")

        return answers_dict

    def _create_submission(self, *, classroom, student, answers_dict, assignment=None):
        delete_filter = {
            "classroom": classroom,
            "student": student,
        }
        if assignment is not None:
            delete_filter["assignment"] = assignment

        Submission.objects.filter(**delete_filter).delete()

        sub = Submission.objects.create(
            classroom=classroom,
            student=student,
            assignment=assignment,
        )

        question_filter = {"classroom": classroom}
        if assignment is not None:
            question_filter["assignment"] = assignment

        qs = Question.objects.filter(**question_filter).prefetch_related("choices")
        qmap = {str(q.id): q for q in qs}

        for qid_str, resp in answers_dict.items():
            q = qmap.get(str(qid_str))
            if not q:
                continue

            resp_str = str(resp)

            ans = SubmissionAnswer.objects.create(
                submission=sub,
                question=q,
                response=resp_str,
            )

            if q.qtype == "MCQ":
                try:
                    selected = int(resp_str)
                    choices = list(q.choices.all())
                    if 0 <= selected < len(choices):
                        ans.is_correct = bool(choices[selected].is_correct)
                        ans.points = 1 if ans.is_correct else 0
                    else:
                        ans.is_correct = False
                        ans.points = 0
                except Exception:
                    ans.is_correct = False
                    ans.points = 0
                ans.save()

            elif q.qtype == "FILL":
                accepted = fill_answers(q.answer_key)
                given = normalize(resp_str)
                ans.is_correct = given in accepted
                ans.points = 1 if ans.is_correct else 0
                ans.save()

            # SHORT stays ungraded

        sub.total_score = sum(a.points for a in sub.answers.all())
        sub.is_graded = not sub.answers.filter(question__qtype="SHORT").exists()
        sub.save()

        return sub

    # Override create to set teacher as current user
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

    @action(detail=True, methods=["get"], url_path="submissions")
    def submissions(self, request, pk=None):
        classroom = self.get_object()
        subs = Submission.objects.filter(classroom=classroom).select_related("student").prefetch_related("answers__question")
        return Response(SubmissionSerializer(subs, many=True).data)
    
    @action(detail=True, methods=["patch"], url_path=r"submissions/(?P<sid>\d+)/grade")
    def grade_submission(self, request, pk=None, sid=None):
        classroom = self.get_object()

        # Find the submission for this class
        sub = (
            Submission.objects.filter(id=sid, classroom=classroom)
            .prefetch_related("answers__question")
            .first()
        )

        if not sub:
            return Response(
                {"detail": "Submission not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        answers_map = request.data.get("answers", {})
        if not isinstance(answers_map, dict):
            return Response(
                {"detail": "answers must be an object map: {answer_id: points}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Apply points to SHORT answers only
        for ans in sub.answers.all():
            if ans.question.qtype != "SHORT":
                continue

            key = str(ans.id)
            if key not in answers_map:
                continue

            try:
                pts = float(answers_map[key])
            except Exception:
                return Response(
                    {"detail": f"Invalid points for answer {ans.id}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            ans.points = max(0, pts)
            ans.is_correct = None
            ans.save()

        # Recompute total score
        sub.total_score = sum(a.points for a in sub.answers.all())
        sub.is_graded = True
        sub.save()

        return Response(SubmissionSerializer(sub).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get", "post"], url_path="assignments")
    def assignments(self, request, pk=None):
        classroom = self.get_object()

        if request.method == "GET":
            qs = classroom.assignments.all().order_by("-created_at")
            return Response(AssignmentSerializer(qs, many=True).data)

        ser = AssignmentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save(classroom=classroom)
        return Response(ser.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=["get", "post"], url_path=r"assignments/(?P<aid>\d+)/questions")
    def assignment_questions(self, request, pk=None, aid=None):
        classroom = self.get_object()
        assignment = classroom.assignments.filter(id=aid).first()
        if not assignment:
            return Response({"detail": "Assignment not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.method == "GET":
            qs = assignment.questions.all().order_by("-created_at")
            return Response(QuestionSerializer(qs, many=True).data)

        ser = QuestionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save(
            classroom=classroom,
            assignment=assignment,
            created_by=request.user,
        )
        return Response(ser.data, status=status.HTTP_201_CREATED)

# Below is the code for the StudentViewSet which allows students to view their enrolled classrooms and ask questions.

class IsStudent(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "STUDENT"
    
def normalize(s: str) -> str:
    return (s or "").strip().lower()

def fill_answers(answer_key: str):
    return [normalize(x) for x in (answer_key or "").split(",") if normalize(x)]

class StudentClassRoomViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ClassRoomSerializer
    permission_classes = [IsStudent]

    def get_queryset(self):
        return ClassRoom.objects.filter(enrollments__student=self.request.user).distinct()

    def _parse_answers(self, request):
        raw = request.data.get("answers", None)

        if isinstance(raw, dict):
            answers_dict = {str(k): str(v) for k, v in raw.items()}
        elif isinstance(raw, list):
            answers_dict = {}
            for item in raw:
                if isinstance(item, dict) and "question" in item and "response" in item:
                    answers_dict[str(item["question"])] = str(item["response"])
                else:
                    raise ValueError("Invalid answers list format. Use {question, response} objects.")
        else:
            raise ValueError("answers must be an object (dict) or a list.")

        if not answers_dict:
            raise ValueError("answers cannot be empty.")

        return answers_dict

    def _create_submission(self, *, classroom, student, answers_dict, assignment=None):
        delete_filter = {
            "classroom": classroom,
            "student": student,
        }
        if assignment is not None:
            delete_filter["assignment"] = assignment

        Submission.objects.filter(**delete_filter).delete()

        sub = Submission.objects.create(
            classroom=classroom,
            student=student,
            assignment=assignment,
        )

        question_filter = {"classroom": classroom}
        if assignment is not None:
            question_filter["assignment"] = assignment

        qs = Question.objects.filter(**question_filter).prefetch_related("choices")
        qmap = {str(q.id): q for q in qs}

        for qid_str, resp in answers_dict.items():
            q = qmap.get(str(qid_str))
            if not q:
                continue

            resp_str = str(resp)

            ans = SubmissionAnswer.objects.create(
                submission=sub,
                question=q,
                response=resp_str,
            )

            if q.qtype == "MCQ":
                try:
                    selected = int(resp_str)
                    choices = list(q.choices.all())
                    if 0 <= selected < len(choices):
                        ans.is_correct = bool(choices[selected].is_correct)
                        ans.points = 1 if ans.is_correct else 0
                    else:
                        ans.is_correct = False
                        ans.points = 0
                except Exception:
                    ans.is_correct = False
                    ans.points = 0
                ans.save()

            elif q.qtype == "FILL":
                accepted = fill_answers(q.answer_key)
                given = normalize(resp_str)
                ans.is_correct = given in accepted
                ans.points = 1 if ans.is_correct else 0
                ans.save()

            # SHORT stays ungraded

        sub.total_score = sum(a.points for a in sub.answers.all())
        sub.is_graded = not sub.answers.filter(question__qtype="SHORT").exists()
        sub.save()

        return sub

    @action(detail=True, methods=["get"], url_path="assignments")
    def assignments(self, request, pk=None):
        classroom = self.get_object()
        qs = classroom.assignments.all().order_by("-created_at")
        return Response(AssignmentSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"], url_path=r"assignments/(?P<aid>\d+)/questions")
    def assignment_questions(self, request, pk=None, aid=None):
        classroom = self.get_object()
        assignment = classroom.assignments.filter(id=aid).first()

        if not assignment:
            return Response(
                {"detail": "Assignment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = (
            Question.objects.filter(classroom=classroom, assignment=assignment)
            .prefetch_related("choices")
            .order_by("-created_at")
        )

        return Response(StudentQuestionSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], url_path=r"assignments/(?P<aid>\d+)/submit")
    def submit_assignment(self, request, pk=None, aid=None):
        classroom = self.get_object()
        assignment = classroom.assignments.filter(id=aid).first()

        if not assignment:
            return Response(
                {"detail": "Assignment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 🔒 LOCK SUBMISSION AFTER DUE DATE
        if assignment.due_date and assignment.due_date < timezone.now():
            return Response(
                {"detail": "This assignment is past due and can no longer be submitted."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            answers_dict = self._parse_answers(request)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        sub = self._create_submission(
            classroom=classroom,
            student=request.user,
            assignment=assignment,
            answers_dict=answers_dict,
        )

        return Response(SubmissionSerializer(sub).data, status=status.HTTP_201_CREATED)
        
    @action(detail=True, methods=["get"], url_path=r"assignments/(?P<aid>\d+)/my-submission")
    def my_assignment_submission(self, request, pk=None, aid=None):
        classroom = self.get_object()
        assignment = classroom.assignments.filter(id=aid).first()
        if not assignment:
            return Response({"detail": "Assignment not found."}, status=status.HTTP_404_NOT_FOUND)

        sub = (
            Submission.objects.filter(
                classroom=classroom,
                student=request.user,
                assignment=assignment,
            )
            .select_related("student")
            .prefetch_related("answers__question__choices")
            .order_by("-created_at")
            .first()
        )

        if not sub:
            return Response({"detail": "No submission yet."}, status=status.HTTP_404_NOT_FOUND)

        return Response(SubmissionSerializer(sub).data, status=status.HTTP_200_OK)