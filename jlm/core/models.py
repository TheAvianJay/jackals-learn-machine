from django.conf import settings
from django.db import models

class ClassRoom(models.Model):
    name = models.CharField(max_length=120)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="classes")

    def __str__(self):
        return self.name

class Enrollment(models.Model):
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, related_name="enrollments")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")

    class Meta:
        unique_together = ("classroom", "student")

class Question(models.Model):
    MCQ = "MCQ"
    FILL = "FILL"
    SHORT = "SHORT"

    QTYPE_CHOICES = [
        (MCQ, "Multiple Choice"),
        (FILL, "Fill in the Blank"),
        (SHORT, "Short Answer"),
    ]

    classroom = models.ForeignKey("ClassRoom", on_delete=models.CASCADE, related_name="questions")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_questions")

    qtype = models.CharField(max_length=10, choices=QTYPE_CHOICES)
    prompt = models.TextField()

    # For FILL: store acceptable answers (normalized later)
    answer_key = models.TextField(blank=True, default="")

    # For SHORT: optional teacher notes / rubric (MVP)
    rubric = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)