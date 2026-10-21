import re
import unicodedata

from django import forms

from .models import Comment


class CommentForm(forms.ModelForm):
    body = forms.CharField(
        label="Your comment",
        max_length=2000,
        strip=False,
        error_messages={
            "max_length": "Comments must be 2,000 characters or fewer.",
        },
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "maxlength": 2000,
                "required": True,
                "data-comment-body": True,
                "autocomplete": "off",
                "placeholder": "Share a useful question, correction, or experience…",
            }
        ),
    )

    class Meta:
        model = Comment
        fields = ("body",)

    def clean_body(self):
        body = unicodedata.normalize("NFKC", self.cleaned_data["body"])
        body = body.replace("\r\n", "\n").replace("\r", "\n")
        body = "\n".join(re.sub(r"[^\S\n]+", " ", line).strip() for line in body.split("\n"))
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        if not body:
            raise forms.ValidationError("Please enter a comment before submitting.")
        if len(body) > 2000:
            raise forms.ValidationError("Comments must be 2,000 characters or fewer.")
        return body
