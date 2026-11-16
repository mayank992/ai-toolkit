"""setup's public surface for the dashboard."""


def snapshot():
    """Inventory, health and export preview of this machine's setup."""
    from . import ops, snapshot_tree
    return ops.snapshot(snapshot_tree.load_config())
