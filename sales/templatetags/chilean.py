from django import template
register=template.Library()

@register.filter
def clp(value):
    try: return f"{int(value):,}".replace(",", ".")
    except (TypeError,ValueError): return value

