from django.contrib.auth.models import AbstractUser, BaseUserManager, UnicodeUsernameValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


# Canonical qualification codes shared with the jobs eligibility engine
# (see jobs.models.QUALIFICATION_DEFINITIONS).
QUALIFICATION_CHOICES = [
    ("10th", "10th Pass / Matriculation"),
    ("12th", "12th Pass / Intermediate"),
    ("iti", "ITI (Industrial Training)"),
    ("diploma", "Diploma / Polytechnic"),
    ("graduate", "Graduate / Bachelor's Degree"),
    ("btech", "B.Tech / B.E."),
    ("postgraduate", "Postgraduate / Master's Degree"),
]


class EmailUserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, username, email, password=None, **extra_fields):
        if not username:
            raise ValueError("A username is required.")
        if not email:
            raise ValueError("An email address is required.")
        username = username.strip().casefold()
        email = self.normalize_email(email.strip()).casefold()
        extra_fields.setdefault("full_name", username)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")

        return self.create_user(username, email, password, **extra_fields)


class EmailUser(AbstractUser):
    username = models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        validators=[UnicodeUsernameValidator()],
    )
    email = models.EmailField(_("email address"), unique=True)
    full_name = models.CharField(_("full name"), max_length=150)
    date_of_birth = models.DateField(
        _("date of birth"),
        null=True,
        blank=True,
        help_text="Used to check exam eligibility against each exam's date-of-birth window.",
    )
    qualification = models.CharField(
        _("highest qualification"),
        max_length=30,
        blank=True,
        default="",
        choices=QUALIFICATION_CHOICES,
        help_text="Highest completed qualification, used for exam eligibility matching.",
    )

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    objects = EmailUserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="accounts_username_case_insensitive_uniq",
            ),
            models.UniqueConstraint(
                Lower("email"),
                name="accounts_email_case_insensitive_uniq",
            ),
        ]

    def __str__(self):
        return self.username
