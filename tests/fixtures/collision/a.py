"""Fixture for cross-file call-collision tests — module A."""


def shared():
    return "a"


def only_in_a():
    return "a-only"
