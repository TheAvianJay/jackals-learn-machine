from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Assignment, ClassRoom, Enrollment, Question, Choice, Submission, SubmissionAnswer

User = get_user_model()

print("LOADED core/serializers.py ✅")
# ---------- Roster / Classes ----------

class StudentSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name"]


class EnrollmentSerializer(serializers.ModelSerializer):
    student = StudentSummarySerializer(read_only=True)

    class Meta:
        model = Enrollment
        fields = ["id", "student"]


class ClassRoomSerializer(serializers.ModelSerializer):
    roster = serializers.SerializerMethodField()

    class Meta:
        model = ClassRoom
        fields = ["id", "name", "teacher", "roster"]
        read_only_fields = ["teacher", "roster"]

    def get_roster(self, obj):
        enrollments = obj.enrollments.select_related("student").all()
        return EnrollmentSerializer(enrollments, many=True).data


class AddStudentSerializer(serializers.Serializer):
    username = serializers.CharField()

    def validate_username(self, value):
        try:
            user = User.objects.get(username=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("No user with that username.")

        if getattr(user, "role", None) != "STUDENT":
            raise serializers.ValidationError("User is not a student.")

        return value


# ---------- Questions ----------

class ChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choice
        fields = ["id", "text", "is_correct"]


class QuestionSerializer(serializers.ModelSerializer):
    choices = ChoiceSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = [
            "id",
            "classroom",
            "created_by",
            "qtype",
            "prompt",
            "answer_key",
            "rubric",
            "choices",
            "created_at",
        ]
        read_only_fields = ["classroom", "created_by", "created_at"]

    def validate(self, data):
        qtype = data.get("qtype", getattr(self.instance, "qtype", None))
        choices = self.initial_data.get("choices", None)
        answer_key = data.get("answer_key", getattr(self.instance, "answer_key", ""))

        if qtype == "MCQ":
            if not choices or len(choices) < 2:
                raise serializers.ValidationError("MCQ requires at least 2 choices.")
            if not any(c.get("is_correct") for c in choices):
                raise serializers.ValidationError("MCQ requires at least one correct choice.")

        if qtype == "FILL":
            if not (answer_key or "").strip():
                raise serializers.ValidationError("FILL requires answer_key.")

        return data   # ← THIS LINE FIXES YOUR ERROR

    def create(self, validated_data):
        choices_data = validated_data.pop("choices", [])
        q = Question.objects.create(**validated_data)
        for c in choices_data:
            Choice.objects.create(question=q, **c)
        return q
    def update(self, instance, validated_data):
        choices_data = validated_data.pop("choices", None)

        # update main fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # if choices were provided, replace them (simple MVP approach)
        if choices_data is not None:
            instance.choices.all().delete()
            for c in choices_data:
                Choice.objects.create(question=instance, **c)

        return instance

# ---------- Submissions ----------   
class SubmissionAnswerSerializer(serializers.ModelSerializer):
    question_id = serializers.IntegerField(source="question.id", read_only=True)
    prompt = serializers.CharField(source="question.prompt", read_only=True)
    qtype = serializers.CharField(source="question.qtype", read_only=True)

    # NEW: for MCQ show choice text instead of "0"
    response_display = serializers.SerializerMethodField()

    class Meta:
        model = SubmissionAnswer
        fields = [
            "id",
            "question_id",
            "prompt",
            "qtype",
            "response",          # raw stored value (index/text)
            "response_display",  # human readable
            "is_correct",
            "points",
        ]

    def get_response_display(self, obj):
        if obj.question.qtype != "MCQ":
            return obj.response

        try:
            idx = int(obj.response)
        except Exception:
            return obj.response

        choices = list(obj.question.choices.all())
        if 0 <= idx < len(choices):
            return choices[idx].text
        return obj.response

class SubmissionSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source="student.username", read_only=True)
    assignment_title = serializers.CharField(source="assignment.title", read_only=True, default="")
    answers = SubmissionAnswerSerializer(many=True, read_only=True)

    class Meta:
        model = Submission
        fields = [
            "id",
            "classroom",
            "assignment",
            "assignment_title",
            "student",
            "student_username",
            "created_at",
            "total_score",
            "is_graded",
            "answers",
        ]
        read_only_fields = ["student", "created_at", "total_score", "is_graded", "answers"]
        
class SubmitPayloadSerializer(serializers.Serializer):
    
    """
    Accept either:
      A) {"answers": {"12": "0", "13": "text"}}
      B) {"answers": [{"question": 12, "response": "0"}, ...]}
    Normalize to dict[str, str].
    """
    answers = serializers.JSONField()

    def validate_answers(self, value):
        # Case A: dict
        if isinstance(value, dict):
            if not value:
                raise serializers.ValidationError("answers cannot be empty.")
            return {str(k): str(v) for k, v in value.items()}

        # Case B: list
        if isinstance(value, list):
            if not value:
                raise serializers.ValidationError("answers cannot be empty.")
            out = {}
            for item in value:
                if not isinstance(item, dict) or "question" not in item or "response" not in item:
                    raise serializers.ValidationError(
                        "List answers must be objects with 'question' and 'response'."
                    )
                out[str(item["question"])] = str(item["response"])
            return out

        raise serializers.ValidationError("answers must be an object or a list.")
    

class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        fields = ["id", "classroom", "title", "created_at"]
        read_only_fields = ["classroom", "created_at"]
        