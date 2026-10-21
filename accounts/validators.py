from django.core.exceptions import ValidationError


class PasswordPolicyValidator:
    message = "Password must contain at least 8 characters and one number."
    code = "password_policy"

    def validate(self, password, user=None):
        if len(password) < 8 or not any(character in "0123456789" for character in password):
            raise ValidationError(self.message, code=self.code)

    def get_help_text(self):
        return self.message
