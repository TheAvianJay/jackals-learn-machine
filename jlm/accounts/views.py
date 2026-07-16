from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from .serializers import ProfileSerializer

class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = ProfileSerializer(
            request.user,
            context={"request": request}
        )
        return Response(serializer.data)

    def patch(self, request):
        # Handle multipart form data for profile picture
        serializer = ProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Save profile picture separately if provided
        if "profile_picture" in request.FILES:
            request.user.profile_picture = request.FILES["profile_picture"]
            request.user.save()

        return Response(
            ProfileSerializer(
                request.user,
                context={"request": request}
            ).data
        )