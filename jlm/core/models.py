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
    class Type(models.TextChoices):
        MULTIPLE_CHOICE = "MC", "Multiple Choice"
        FILL_BLANK = "FB", "Fill in the Blank"
        SHORT_ANSWER = "SA", "Short Answer"

    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, related_name="questions")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_questions")
    qtype = models.CharField(max_length=2, choices=Type.choices)
    prompt = models.TextField()

class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
