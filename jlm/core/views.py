from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from rest_framework import viewsets, permissions, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import (
    Feedback, UserPreference, Notification, Excuse,
    ClassRoom, Enrollment, Question, Submission, SubmissionAnswer, Assignment, ProfilePictureFlag
)
from .serializers import FeedbackSerializer, UserPreferenceSerializer, NotificationSerializer, ExcuseSerializer


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

class FeedbackViewSet(viewsets.ModelViewSet):
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer

    def perform_create(self, serializer):
        # Count pinned feedbacks
        pinned_count = Feedback.objects.filter(
            answer=serializer.validated_data["answer"], pinned=True
        ).count()

        if pinned_count >= 5:
            raise serializers.ValidationError(
                "Cannot add new feedback: maximum of 5 pinned feedback already exists."
            )

        feedback = serializer.save(teacher=self.request.user)

        # Get all feedbacks for this answer (oldest first), excluding pinned
        qs = Feedback.objects.filter(answer=feedback.answer, pinned=False).order_by("created_at")

        # Delete oldest if more than 5 (non-pinned)
        excess = qs.count() - (5 - pinned_count)
        if excess > 0:
            qs[:excess].delete()

    def perform_update(self, serializer):
        # Set edited flags on update
        serializer.save(edited=True, edited_at=timezone.now())

    def get_queryset(self):
        queryset = super().get_queryset()

        submission_id = self.request.query_params.get("submission")
        answer_id = self.request.query_params.get("answer")

        if submission_id:
            queryset = queryset.filter(answer__submission_id=submission_id)

        if answer_id:
            queryset = queryset.filter(answer_id=answer_id)

        return queryset.order_by("-created_at")

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

        from django.utils import timezone
        from rest_framework.exceptions import ValidationError

        if assignment and assignment.due_date:
            if timezone.now() > assignment.due_date:
                raise ValidationError("Assignment is past due and locked.")

        delete_filter = {
            "classroom": classroom,
            "student": student,
        }
        if assignment is not None:
            delete_filter["assignment"] = assignment

        existing = Submission.objects.filter(
            classroom=classroom,
            student=student,
            assignment=assignment
        ).first()

        if existing:
            if assignment.due_date and timezone.now() > assignment.due_date:
                raise ValidationError("Cannot modify submission after due date.")

            existing.delete()
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
                        ans.points = q.max_points if ans.is_correct else 0
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
                ans.points = q.max_points if ans.is_correct else 0
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
            qs = assignment.questions.all().order_by("created_at")
            return Response(
                QuestionSerializer(qs, many=True, context={"request": request}).data
            )

        # Build mutable data dict from request
        import json
        data = {}
        for key in ["qtype", "prompt", "max_points", "answer_key", "rubric", "allow_multiple_correct"]:
            if key in request.data:
                data[key] = request.data[key]

        # Choices come as a JSON string in the "choices" field
        raw_choices = request.data.get("choices")
        if raw_choices:
            try:
                data["choices"] = json.loads(raw_choices)
            except (json.JSONDecodeError, TypeError):
                data["choices"] = raw_choices  # already parsed

        ser = QuestionSerializer(data=data, context={"request": request})
        ser.is_valid(raise_exception=True)

        image = request.FILES.get("image")
        question = ser.save(
            classroom=classroom,
            assignment=assignment,
            created_by=request.user,
        )

        # Save image separately if provided
        if image:
            question.image = image
            question.save()

        return Response(
            QuestionSerializer(question, context={"request": request}).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=["get"], url_path="student-grades")
    def student_grades(self, request, pk=None):
        classroom = self.get_object()
        enrollments = classroom.enrollments.select_related("student").all()
        assignments = classroom.assignments.prefetch_related("questions").all()
        results = []

        for enrollment in enrollments:
            student = enrollment.student
            total_earned = 0
            total_possible = 0
            assignment_breakdown = []

            for assignment in assignments:
                possible = sum(q.max_points for q in assignment.questions.all())

                is_excused = Excuse.objects.filter(
                    assignment=assignment, student=student
                ).first()

                sub = Submission.objects.filter(
                    classroom=classroom, student=student, assignment=assignment,
                ).first()

                earned = sub.total_score if sub and sub.is_graded else None

                assignment_breakdown.append({
                    "assignment_id": assignment.id,
                    "assignment_title": assignment.title,
                    "possible_points": possible,
                    "earned_points": earned,
                    "submitted": sub is not None,
                    "graded": sub.is_graded if sub else False,
                    "excused": bool(is_excused),
                    "excuse_reason": is_excused.reason if is_excused else None,
                })

                if earned is not None and not is_excused:
                    total_earned += earned
                    total_possible += possible

            overall_percent = (
                round((total_earned / total_possible) * 100, 1)
                if total_possible > 0 else None
            )

            results.append({
                "student_id": student.id,
                "student_username": student.username,
                "overall_percent": overall_percent,
                "total_earned": total_earned,
                "total_possible": total_possible,
                "assignments": assignment_breakdown,
            })

        return Response(results)
    
    @action(detail=True, methods=["patch"], url_path=r"assignments/(?P<aid>\d+)/publish")
    def publish_assignment(self, request, pk=None, aid=None):
        classroom = self.get_object()
        assignment = classroom.assignments.filter(id=aid).first()

        if not assignment:
            return Response({"detail": "Assignment not found."}, status=404)

        assignment.is_published = True
        assignment.save()
        return Response(AssignmentSerializer(assignment).data)
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        # Only allow deleting through the normal flow
        # Published assignments with submissions should not be deletable this way
        if instance.is_published and instance.submissions.exists():
            return Response(
                {"detail": "Cannot delete a published assignment with submissions."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)
    
    @action(detail=True, methods=["delete"], url_path=r"assignments/(?P<aid>\d+)/discard")
    def discard_assignment(self, request, pk=None, aid=None):
        classroom = self.get_object()
        assignment = classroom.assignments.filter(id=aid, is_published=False).first()

        if not assignment:
            return Response(
                {"detail": "Draft assignment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        assignment.delete()
        return Response({"detail": "Draft discarded."}, status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path=r"assignments/(?P<aid>\d+)/submissions")
    def assignment_submissions(self, request, pk=None, aid=None):
        classroom = self.get_object()

        subs = Submission.objects.filter(
            classroom=classroom,
            assignment_id=aid
        ).select_related("student")

        return Response(SubmissionSerializer(subs, many=True).data)
    
    @action(detail=True, methods=["patch"], url_path=r"assignments/(?P<aid>\d+)")
    def update_assignment(self, request, pk=None, aid=None):
        classroom = self.get_object()
        assignment = classroom.assignments.filter(id=aid).first()

        if not assignment:
            return Response(
                {"detail": "Assignment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        ser = AssignmentSerializer(assignment, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

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
                    if q.allow_multiple_correct:
                        # resp_str is comma-separated selected indices e.g. "0,2"
                        selected_indices = set(
                            int(x.strip()) for x in resp_str.split(",") if x.strip().isdigit()
                        )
                        choices = list(q.choices.all())
                        correct_indices = {i for i, c in enumerate(choices) if c.is_correct}
                        ans.is_correct = selected_indices == correct_indices
                    else:
                        selected = int(resp_str)
                        choices = list(q.choices.all())
                        if 0 <= selected < len(choices):
                            ans.is_correct = bool(choices[selected].is_correct)
                        else:
                            ans.is_correct = False
                    ans.points = q.max_points if ans.is_correct else 0
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
        qs = classroom.assignments.filter(
            is_published=True  # 👈 students only see published
        ).order_by("-created_at")
        return Response(AssignmentSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"], url_path=r"assignments/(?P<aid>\d+)/questions")
    def assignment_questions(self, request, pk=None, aid=None):
        classroom = self.get_object()
        assignment = classroom.assignments.filter(id=aid).first()

        if not assignment:
            return Response({"detail": "Assignment not found."}, status=status.HTTP_404_NOT_FOUND)

        qs = (
            Question.objects.filter(classroom=classroom, assignment=assignment)
            .prefetch_related("choices")
            .order_by("created_at")
        )

        return Response(
            StudentQuestionSerializer(qs, many=True, context={"request": request}).data
        )
    
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
        now = timezone.now()

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
    
    @action(detail=True, methods=["get"], url_path="overall-grade")
    def overall_grade(self, request, pk=None):
        classroom = self.get_object()
        assignments = classroom.assignments.all()
        results = []
        total_earned = 0
        total_possible = 0

        for assignment in assignments:
            possible = sum(q.max_points for q in assignment.questions.all())

            # Check if excused
            is_excused = Excuse.objects.filter(
                assignment=assignment,
                student=request.user,
            ).first()

            sub = Submission.objects.filter(
                classroom=classroom,
                student=request.user,
                assignment=assignment,
            ).first()

            earned = sub.total_score if sub and sub.is_graded else None
            submitted = sub is not None
            graded = sub.is_graded if sub else False

            excuse_reason = is_excused.reason if is_excused else None

            results.append({
                "assignment_id": assignment.id,
                "assignment_title": assignment.title,
                "due_date": assignment.due_date,
                "start_date": assignment.start_date,
                "possible_points": possible,
                "earned_points": earned,
                "submitted": submitted,
                "graded": graded,
                "excused": bool(is_excused),
                "excuse_reason": excuse_reason,
            })

            # Only count non-excused graded submissions
            if earned is not None and not is_excused:
                total_earned += earned
                total_possible += possible

        overall_percent = (
            round((total_earned / total_possible) * 100, 1)
            if total_possible > 0 else None
        )

        return Response({
            "classroom_id": classroom.id,
            "classroom_name": classroom.name,
            "overall_percent": overall_percent,
            "total_earned": total_earned,
            "total_possible": total_possible,
            "assignments": results,
        })

class PreferenceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pref, _ = UserPreference.objects.get_or_create(user=request.user)
        return Response(UserPreferenceSerializer(pref).data)

    def patch(self, request):
        pref, _ = UserPreference.objects.get_or_create(user=request.user)
        ser = UserPreferenceSerializer(pref, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class NotificationListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        notifs = Notification.objects.filter(recipient=request.user)
        return Response(NotificationSerializer(notifs, many=True).data)


class NotificationMarkReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Mark all as read
        Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(is_read=True)
        return Response({"detail": "All notifications marked as read."})

    def patch(self, request, pk=None):
        # Mark single notification as read
        notif = Notification.objects.filter(
            id=pk,
            recipient=request.user
        ).first()
        if not notif:
            return Response({"detail": "Not found."}, status=404)
        notif.is_read = True
        notif.save()
        return Response(NotificationSerializer(notif).data)


class UnreadCountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()
        return Response({"unread": count})
    
class ExcuseView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, classroom_id=None, assignment_id=None):
        # List all excuses for an assignment
        excuses = Excuse.objects.filter(
            assignment_id=assignment_id,
            assignment__classroom_id=classroom_id,
            assignment__classroom__teacher=request.user,
        ).select_related("student")
        return Response(ExcuseSerializer(excuses, many=True).data)

    def post(self, request, classroom_id=None, assignment_id=None):
        # Excuse a student
        student_id = request.data.get("student_id")
        reason = request.data.get("reason", "")

        if not student_id:
            return Response({"detail": "student_id required."}, status=400)

        assignment = Assignment.objects.filter(
            id=assignment_id,
            classroom_id=classroom_id,
            classroom__teacher=request.user,
        ).first()

        if not assignment:
            return Response({"detail": "Assignment not found."}, status=404)

        excuse, created = Excuse.objects.get_or_create(
            assignment=assignment,
            student_id=student_id,
            defaults={"reason": reason},
        )

        if not created:
            # Update reason if already excused
            excuse.reason = reason
            excuse.save()

        return Response(ExcuseSerializer(excuse).data, status=201)

    def delete(self, request, classroom_id=None, assignment_id=None, student_id=None):
        excuse = Excuse.objects.filter(
            assignment_id=assignment_id,
            assignment__classroom_id=classroom_id,
            assignment__classroom__teacher=request.user,
            student_id=student_id,
        ).first()

        if not excuse:
            return Response({"detail": "Excuse not found."}, status=404)

        excuse.delete()
        return Response({"detail": "Excuse removed."}, status=204)
    
#flagging profile pictures
#As much as I would like to trust people to take this seriously,
#there are people who like to be rebels so I have to implement a 
# flagging system for profile pictures because we can't trust everyone to be responsible with their profile pictures.

class FlagProfilePictureView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, user_id=None):
        if request.user.id == user_id:
            return Response({"detail": "Cannot flag your own picture."}, status=400)

        target = User.objects.filter(id=user_id).first()
        if not target:
            return Response({"detail": "User not found."}, status=404)

        ProfilePictureFlag.objects.get_or_create(
            flagged_user=target,
            flagged_by=request.user,
            defaults={"reason": request.data.get("reason", "")}
        )
        return Response({"detail": "Flagged successfully."})
    
class FlaggedProfilesView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request):
        flags = ProfilePictureFlag.objects.filter(
            resolved=False
        ).select_related("flagged_user", "flagged_by")

        return Response([{
            "flag_id": f.id,
            "user_id": f.flagged_user.id,
            "username": f.flagged_user.username,
            "profile_picture_url": request.build_absolute_uri(
                f.flagged_user.profile_picture.url
            ) if f.flagged_user.profile_picture else None,
            "flagged_by": f.flagged_by.username,
            "reason": f.reason,
            "created_at": f.created_at,
        } for f in flags])


class ResolveFlagView(APIView):
    permission_classes = [IsTeacher]

    def post(self, request, user_id=None):
        action = request.data.get("action")  # "approve" or "revoke"

        target = User.objects.filter(id=user_id).first()
        if not target:
            return Response({"detail": "User not found."}, status=404)

        if action == "revoke":
            target.profile_picture.delete(save=False)
            target.profile_picture = None
            target.profile_picture_approved = False
            target.save()

        elif action == "approve":
            target.profile_picture_approved = True
            target.save()

        ProfilePictureFlag.objects.filter(flagged_user=target).update(resolved=True)
        return Response({"detail": f"Picture {action}d."})