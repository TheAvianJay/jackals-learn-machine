# core/management/commands/send_available_notifications.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Assignment, Enrollment, UserPreference, Notification

class Command(BaseCommand):
    help = "Send notifications for assignments that just became available"

    def handle(self, *args, **options):
        now = timezone.now()
        # Find assignments whose start_date just passed (within last 5 minutes)
        five_min_ago = now - timezone.timedelta(minutes=5)

        assignments = Assignment.objects.filter(
            is_published=True,
            start_date__gte=five_min_ago,
            start_date__lte=now,
        )

        for assignment in assignments:
            enrollments = Enrollment.objects.filter(
                classroom=assignment.classroom
            ).select_related("student")

            for enrollment in enrollments:
                student = enrollment.student
                # Don't send duplicate
                if Notification.objects.filter(
                    recipient=student,
                    assignment=assignment,
                    notif_type="assignment_posted",
                ).exists():
                    continue

                pref, _ = UserPreference.objects.get_or_create(user=student)
                if not pref.notify_assignment_posted:
                    continue

                Notification.objects.create(
                    recipient=student,
                    notif_type="assignment_posted",
                    title="Assignment Now Available",
                    body=f'"{assignment.title}" is now available in {assignment.classroom.name}.',
                    classroom=assignment.classroom,
                    assignment=assignment,
                )

        self.stdout.write(f"Done. Checked {assignments.count()} assignments.")