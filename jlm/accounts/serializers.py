from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()

class ProfileSerializer(serializers.ModelSerializer):
    profile_picture_url = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False)
    confirm_password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "profile_picture",
            "profile_picture_url",
            "password",
            "confirm_password",
        ]
        read_only_fields = ["id", "role", "profile_picture_url"]
        extra_kwargs = {
            "profile_picture": {"write_only": True, "required": False},
        }

    def get_profile_picture_url(self, obj):
        if not obj.profile_picture:
            return None
        if not obj.profile_picture_approved:
            return None  # Hide flagged/revoked pictures
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.profile_picture.url)
        return obj.profile_picture.url

    def validate(self, data):
        password = data.get("password")
        confirm = data.get("confirm_password")

        if password or confirm:
            if password != confirm:
                raise serializers.ValidationError("Passwords do not match.")
            validate_password(password)

        return data

    def update(self, instance, validated_data):
        validated_data.pop("confirm_password", None)
        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance