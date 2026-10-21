import re

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from .models import Comment


User = get_user_model()


class CommunityCommentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="commenter",
            email="commenter@example.com",
            password="Sufficient-pass-321!",
        )

    def test_comments_page_is_public_and_hides_unpublished_comments(self):
        visible = Comment.objects.create(
            author=self.user,
            body="A helpful published note.",
            status=Comment.Status.PUBLISHED,
        )
        Comment.objects.create(
            author=self.user,
            body="This is still in review.",
        )

        response = self.client.get(reverse("comments:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, visible.body)
        self.assertContains(response, "commenter")
        self.assertNotContains(response, "This is still in review.")
        self.assertContains(response, "Log in to comment")

    def test_authenticated_composer_shows_username_and_character_feedback(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("comments:list"))

        self.assertContains(response, "Posting as")
        self.assertContains(response, "commenter")
        self.assertContains(response, "2,000 characters remaining")
        self.assertContains(response, "comments/comments.js")

    def test_authenticated_comment_is_normalized_and_published_immediately(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("comments:list"),
            {
                "body": "  Ｈｅｌｌｏ   community  \r\n\r\n\r\nThanks!  ",
                "author": "999999",
                "author_id": "999999",
            },
        )

        comment = Comment.objects.get()
        self.assertRedirects(response, f"{reverse('comments:list')}#comments")
        self.assertEqual(comment.author, self.user)
        self.assertEqual(comment.body, "Hello community\n\nThanks!")
        self.assertEqual(comment.status, Comment.Status.PUBLISHED)
        self.client.logout()
        public_response = self.client.get(reverse("comments:list"))
        self.assertContains(public_response, comment.body)
        self.assertContains(public_response, self.user.username)

    def test_anonymous_post_redirects_to_login_with_safe_return_path(self):
        response = self.client.post(
            reverse("comments:list"),
            {"body": "A comment from a guest."},
        )

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('comments:list')}",
            fetch_redirect_response=False,
        )
        self.assertFalse(Comment.objects.exists())

    def test_cooldown_limits_repeat_posts_per_account(self):
        self.client.force_login(self.user)
        url = reverse("comments:list")

        self.client.post(url, {"body": "First comment."})
        response = self.client.post(url, {"body": "Second comment."})

        self.assertEqual(Comment.objects.count(), 1)
        self.assertContains(response, "Please wait a little")
        self.assertContains(response, "Second comment.")

    def test_invalid_blank_and_overlong_comments_are_rejected(self):
        self.client.force_login(self.user)
        url = reverse("comments:list")

        blank_response = self.client.post(url, {"body": " \t  \n "})
        self.assertEqual(blank_response.status_code, 200)
        self.assertContains(blank_response, "Please enter a comment")
        self.assertContains(blank_response, 'aria-invalid="true"')
        self.assertFalse(Comment.objects.exists())

        long_response = self.client.post(url, {"body": "x" * 2001})
        self.assertEqual(long_response.status_code, 200)
        self.assertContains(long_response, "2,000 characters or fewer")
        self.assertFalse(Comment.objects.exists())

    def test_textarea_links_errors_and_description_for_screen_readers(self):
        self.client.force_login(self.user)
        url = reverse("comments:list")

        page = self.client.get(url)
        self.assertContains(page, 'aria-describedby="comments-character-count id_body-description id_body-errors"')
        self.assertContains(page, "id_body-description")

        error_response = self.client.post(url, {"body": "   "})
        self.assertContains(error_response, 'aria-invalid="true"')
        self.assertContains(error_response, 'aria-describedby="comments-character-count id_body-description id_body-errors"')

    def test_published_comment_content_is_escaped(self):
        Comment.objects.create(
            author=self.user,
            body="<script>alert('not safe')</script>",
            status=Comment.Status.PUBLISHED,
        )

        response = self.client.get(reverse("comments:list"))

        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert")

    def test_published_comments_are_paginated(self):
        Comment.objects.bulk_create(
            [
                Comment(
                    author=self.user,
                    body=f"Published comment {index}",
                    status=Comment.Status.PUBLISHED,
                )
                for index in range(10)
            ]
        )

        response = self.client.get(reverse("comments:list"))

        self.assertEqual(response.context["page_obj"].paginator.num_pages, 2)
        self.assertContains(response, "Older")

    def test_csrf_protects_comment_submissions(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        page = client.get(reverse("comments:list"))
        self.assertEqual(page.status_code, 200)
        self.assertRegex(
            page.content.decode("utf-8"),
            re.compile(r'name="csrfmiddlewaretoken"'),
        )

        response = client.post(
            reverse("comments:list"),
            {"body": "Missing CSRF token."},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Comment.objects.exists())

    def test_homepage_has_comments_button_and_keeps_eligibility_link(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, reverse("comments:list"))
        self.assertContains(response, reverse("jobs:eligibility_check"))

    def test_comment_admin_is_registered_for_moderation(self):
        self.assertIn(Comment, admin.site._registry)

        self.client.force_login(
            User.objects.create_superuser(
                username="moderator",
                email="moderator@example.com",
                password="Sufficient-pass-321!",
            )
        )
        response = self.client.get(reverse("admin:comments_comment_changelist"))

        self.assertEqual(response.status_code, 200)
