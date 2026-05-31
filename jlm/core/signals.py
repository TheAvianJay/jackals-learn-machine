from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Submission, Feedback, Assignment, Notification, UserPreference


def get_or_create_pref(user):
    pref, _ = UserPreference.objects.get_or_create(user=user)
    return pref


def create_notification(recipient, notif_type, title, body, classroom=None, assignment=None):
    Notification.objects.create(
        recipient=recipient,
        notif_type=notif_type,
        title=title,
        body=body,
        classroom=classroom,
        assignment=assignment,
    )


@receiver(post_save, sender=Assignment)
def on_assignment_posted(sender, instance, created, **kwargs):
    if not created:
        return

    # Notify all enrolled students
    enrollments = instance.classroom.enrollments.select_related("student").all()
    for enrollment in enrollments:
        student = enrollment.student
        pref = get_or_create_pref(student)
        if not pref.notify_assignment_posted:
            continue
        create_notification(
            recipient=student,
            notif_type="assignment_posted",
            title="New Assignment Posted",
            body=f'"{instance.title}" has been posted in {instance.classroom.name}.',
            classroom=instance.classroom,
            assignment=instance,
        )


@receiver(post_save, sender=Submission)
def on_submission_graded(sender, instance, **kwargs):
    if not instance.is_graded:
        return

    pref = get_or_create_pref(instance.student)
    if not pref.notify_assignment_graded:
        return

    title = instance.assignment.title if instance.assignment else "your submission"
    create_notification(
        recipient=instance.student,
        notif_type="assignment_graded",
        title="Assignment Graded",
        body=f'"{title}" has been graded. You scored {instance.total_score} points.',
        classroom=instance.classroom,
        assignment=instance.assignment,
    )


@receiver(post_save, sender=Feedback)
def on_feedback_added(sender, instance, created, **kwargs):
    if not created:
        return

    student = instance.answer.submission.student
    pref = get_or_create_pref(student)
    if not pref.notify_feedback_added:
        return

    create_notification(
        recipient=student,
        notif_type="feedback_added",
        title="New Feedback",
        body=f'Your teacher left feedback on your submission.',
        classroom=instance.answer.submission.classroom,
        assignment=instance.answer.submission.assignment,
    )