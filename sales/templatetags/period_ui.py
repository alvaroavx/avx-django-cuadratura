from django import template

from sales.periods import period_navigation_context

register = template.Library()


@register.inclusion_tag("core/period_navigation.html")
def period_navigation(organization, period):
    return period_navigation_context(organization, period)
