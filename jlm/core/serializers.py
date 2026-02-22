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
        fields = ["id", "classroom", "created_by", "qtype", "prompt", "choices"]
        read_only_fields = ["created_by"]

    def create(self, validated_data):
        choices_data = validated_data.pop("choices", [])
        question = Question.objects.create(**validated_data)
        for c in choices_data:
            Choice.objects.create(question=question, **c)
        return question
