"""Template helpers for the public navigation side panel."""

from django import template

from site_management.models import Exam, ExamLink

register = template.Library()


@register.simple_tag
def sidebar_exam_links():
    """Active exam links grouped by their published exam.

    Returns a list of ``{"exam": Exam, "links": [ExamLink, ...]}`` dicts so the
    public side panel can list every quick link (registration, notification,
    admit card, …) grouped under the exam it belongs to.
    """

    links = (
        ExamLink.objects.filter(
            is_active=True,
            exam__is_active=True,
            exam__status=Exam.Status.PUBLISHED,
        )
        .select_related("exam")
        .order_by("exam__sort_order", "exam__title", "sort_order", "pk")
    )

    groups = []
    groups_by_exam = {}
    for link in links:
        group = groups_by_exam.get(link.exam_id)
        if group is None:
            group = {"exam": link.exam, "links": []}
            groups_by_exam[link.exam_id] = group
            groups.append(group)
        group["links"].append(link)
    return groups
