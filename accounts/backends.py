from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get("email")
        if not identifier or password is None:
            return None

        identifier = identifier.strip().casefold()
        user_model = get_user_model()
        matches = {
            user.pk: user
            for user in user_model._default_manager.filter(
                username__iexact=identifier
            )
        }
        matches.update(
            {
                user.pk: user
                for user in user_model._default_manager.filter(
                    email__iexact=identifier
                )
            }
        )

        if len(matches) != 1:
            user_model().set_password(password)
            return None

        user = next(iter(matches.values()))
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
