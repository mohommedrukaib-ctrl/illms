from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailOrUsernameBackend(ModelBackend):
    """Allow authentication by email or username."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        try:
            if "@" in username:
                user = User.objects.get(email__iexact=username)
            else:
                user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            # Run the default password hasher to mitigate timing attacks
            User().set_password(password)
            return None

        if user.is_deleted:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None