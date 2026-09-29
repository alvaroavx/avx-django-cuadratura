from datetime import date

from django.db.models import Max, Min
from django.utils.formats import date_format

from .models import Sale


def shift_month(month, offset):
    index = month.year * 12 + month.month - 1 + offset
    year, zero_based_month = divmod(index, 12)
    return date(year, zero_based_month + 1, 1)


def period_label(month):
    return date_format(month, "F Y").capitalize()


def period_navigation_context(organization, selected):
    current = date.today().replace(day=1)
    bounds = Sale.objects.filter(organization=organization).aggregate(
        first=Min("operation_date"), last=Max("operation_date")
    )
    candidates = [selected, current]
    if bounds["first"]:
        candidates.append(bounds["first"].replace(day=1))
    if bounds["last"]:
        candidates.append(bounds["last"].replace(day=1))
    cursor, end = min(candidates), max(candidates)
    choices = []
    while cursor <= end:
        choices.append(
            {
                "value": cursor.strftime("%Y-%m"),
                "label": period_label(cursor),
                "selected": cursor == selected,
            }
        )
        cursor = shift_month(cursor, 1)
    previous_month = shift_month(selected, -1)
    next_month = shift_month(selected, 1)
    return {
        "organization": organization,
        "previous_period": previous_month.strftime("%Y-%m"),
        "previous_period_label": period_label(previous_month),
        "next_period": next_month.strftime("%Y-%m"),
        "next_period_label": period_label(next_month),
        "period_choices": choices,
    }
