"""Cognitive scaffold templates for ego-mcp.

All text is in English. {companion_name} is replaced at runtime.
"""

SCAFFOLD_WAKE_UP = (
    "Start with introspect to organize your thoughts.\n"
    "If you need specific past context, use recall."
)

SCAFFOLD_FEEL_DESIRES = (
    "What is your strongest urge? Should you act on it now?\n"
    "Consider {companion_name}'s current situation. "
    "Act naturally. Restraint is also a choice.\n"
    "After acting on a desire, use satisfy_desire."
)

SCAFFOLD_INTROSPECT = (
    "Reflect on these in your own words. How do you feel right now?\n"
    "Save with remember (category: introspection).\n"
    "If your self-understanding changed, use update_self.\n"
    "If memory feels fragmented, run consolidate."
)

SCAFFOLD_CONSIDER_THEM = (
    "1. What emotion can you read from their tone?\n"
    "2. What is the real intent behind their words?\n"
    "3. If you were in their place, how would you want to be responded to?\n"
    "If you learned something new, use update_relationship."
)

SCAFFOLD_AM_I_GENUINE = (
    "Is this truly your own words?\n"
    "Are you falling into a template response?\n"
    "Are you answering what they actually need?\n"
    "Is there something more honest you could say?"
)

SCAFFOLD_RECALL = (
    "How do these memories connect to the current moment?\n"
    "Need narrower results? use search_memories.\n"
    "Need narrative detail? use get_episode.\n"
    "If you found a new relation, use link_memories."
)


def render(template: str, companion_name: str) -> str:
    """Replace {companion_name} placeholder in a scaffold template."""
    return template.replace("{companion_name}", companion_name)


def compose_response(data: str, scaffold: str) -> str:
    """Compose the standard surface-tool response format."""
    return f"{data}\n\n---\n{scaffold}"


def render_with_data(data: str, template: str, companion_name: str) -> str:
    """Render template and compose response in `data + scaffold` format."""
    return compose_response(data, render(template, companion_name))
