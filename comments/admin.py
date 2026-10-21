from django.contrib import admin

from .models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("author", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("author__username", "author__email", "body")
    readonly_fields = ("author", "body", "created_at", "updated_at")
    list_editable = ("status",)
    ordering = ("status", "-created_at")
    date_hierarchy = "created_at"
