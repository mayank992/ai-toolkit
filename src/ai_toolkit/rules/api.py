"""rules' public surface for the dashboard and other features."""


def snapshot(limit=12):
    """The dashboard's view: the rule stack of the most recently used projects."""
    from .inventory import snapshot as build
    return build(limit)
