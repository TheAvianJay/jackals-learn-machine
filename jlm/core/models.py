from django.conf import settings
from django.db import models
from django.utils import timezone

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

    assignment = models.ForeignKey(
        "Assignment",
        on_delete=models.CASCADE,
        related_name="questions",
        null=True,
        blank=True
    )

    max_points = models.FloatField(default=1)

class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

# For MCQ: store choices as related objects. 
# For FILL/SHORT: ignore this model.
# Bellow is the submission and submission answer 
# models, which are used to store student responses
# to questions. Each submission is linked to a 
# classroom and a student, and can have multiple 
# answers (one per question). The response field 
# in SubmissionAnswer can store either the selected 
# choice index for MCQs or the text response for 
# FILL/SHORT questions.
class Submission(models.Model):
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions")
    assignment = models.ForeignKey(
        "Assignment",
        on_delete=models.CASCADE,
        related_name="submissions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(default=timezone.now)

    total_score = models.FloatField(default=0)
    is_graded = models.BooleanField(default=False)

class SubmissionAnswer(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="submission_answers")
    response = models.TextField(blank=True, default="")

    # NEW:
    is_correct = models.BooleanField(null=True, blank=True)  # null = not graded yet
    points = models.FloatField(default=0)

class Assignment(models.Model):
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, related_name="assignments")
    title = models.CharField(max_length=200)
    due_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
    
class Feedback(models.Model):
    answer = models.ForeignKey(
        SubmissionAnswer,
        on_delete=models.CASCADE,
        related_name="feedback"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="given_feedback"
    )
    comment = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    # ✅ ADD THESE
    edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    pinned = models.BooleanField(default=False)

    def __str__(self):
        return f"Feedback by {self.teacher} on Answer {self.answer_id}"