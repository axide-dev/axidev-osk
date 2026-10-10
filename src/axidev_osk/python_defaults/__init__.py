"""Python stand-ins for what the Lua layer will provide.

Everything in this package is replaced by Lua files later: the ``osk``
helper surface, the ``osk.std`` library, and the default profile. Code outside
this package must not contain keyboard layouts, key behavior, or profile
policy. See ``PURIFICATION_PLAN.md``.
"""
