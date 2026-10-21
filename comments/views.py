from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts.views import _public_footer_context, _public_navigation_sections
from site_management.models import WebsiteSettings

from .forms import CommentForm
from .models import Comment


COMMENT_PAGE_SIZE = 8
COMMENT_COOLDOWN_SECONDS = 45


@require_http_methods(["GET", "POST"])
def comment_list(request):
    form = CommentForm()
    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path(),
                login_url=reverse("accounts:login"),
            )
        form = CommentForm(request.POST)
        if form.is_valid():
            cooldown_key = f"community-comment-cooldown:{request.user.pk}"
            if not cache.add(cooldown_key, True, COMMENT_COOLDOWN_SECONDS):
                form.add_error(
                    "body",
                    "Please wait a little before submitting another comment.",
                )
            else:
                comment = form.save(commit=False)
                comment.author = request.user
                comment.status = Comment.Status.PUBLISHED
                comment.save()
                messages.success(
                    request,
                    "Thanks for contributing. Your comment is now visible to the community.",
                )
                return redirect(f"{reverse('comments:list')}#comments")

    body_field = form.fields["body"]
    textarea_id = body_field.widget.attrs.get("id") or body_field.widget.attrs.get("name") or "id_body"
    described_by = f"comments-character-count {textarea_id}-description {textarea_id}-errors"
    body_field.widget.attrs["aria-describedby"] = described_by
    if form.errors.get("body"):
        body_field.widget.attrs["aria-invalid"] = "true"

    published = Comment.objects.filter(
        status=Comment.Status.PUBLISHED
    ).select_related("author")
    published_count = published.count()
    total_count = Comment.objects.count()
    page_obj = Paginator(published, COMMENT_PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    return render(
        request,
        "comments/comment_list.html",
        {
            "form": form,
            "page_obj": page_obj,
            "comments": page_obj.object_list,
            "published_count": published_count,
            "total_count": total_count,
            "website_settings": WebsiteSettings.objects.first() or WebsiteSettings(),
            "navigation_sections": _public_navigation_sections(),
            **_public_footer_context(),
        },
    )
