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
    image = models.ImageField(upload_to="question_images/", null=True, blank=True)  # 👈 new
    answer_key = models.TextField(blank=True, default="")
    rubric = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    allow_multiple_correct = models.BooleanField(default=False)  # 👈 new

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
    start_date = models.DateTimeField(null=True, blank=True)   
    due_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    randomize_questions = models.BooleanField(default=False)
    randomize_choices = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class Excuse(models.Model):
    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="excuses"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="excuses"
    )
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("assignment", "student")

    def __str__(self):
        return f"{self.student.username} excused from {self.assignment.title}"
    
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
    
class UserPreference(models.Model):
    THEME_CHOICES = [
        ("system", "System Default"),
        ("light", "Light"),
        ("dark", "Dark"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preference"
    )
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default="system")

    # Notification toggles
    notify_assignment_posted = models.BooleanField(default=True)
    notify_assignment_graded = models.BooleanField(default=True)
    notify_feedback_added = models.BooleanField(default=True)

    # Push notification token (set by the mobile app)
    push_token = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.user.username} preferences"


class Notification(models.Model):
    TYPES = [
        ("assignment_posted", "Assignment Posted"),
        ("assignment_graded", "Assignment Graded"),
        ("feedback_added", "Feedback Added"),
        ("submission_received", "Submission Received"),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications"
    )
    notif_type = models.CharField(max_length=30, choices=TYPES)
    title = models.CharField(max_length=200)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Optional links back to the relevant object
    classroom = models.ForeignKey(
        ClassRoom, on_delete=models.CASCADE,
        null=True, blank=True, related_name="notifications"
    )
    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE,
        null=True, blank=True, related_name="notifications"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notif_type} → {self.recipient.username}"
    
#Profile picture flagging system
#Because students can be stupid and upload inappropriate profile pictures, we need a way for teachers to flag them. 
# This model will store the flags, who flagged them, and the reason. Teachers can then review the flags and take action if necessary.
class ProfilePictureFlag(models.Model):
    flagged_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="flags_received",
    )
    flagged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="flags_given",
    )
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        unique_together = ("flagged_user", "flagged_by")