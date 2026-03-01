from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import ClassRoom, Enrollment, Question, Choice

User = get_user_model()


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