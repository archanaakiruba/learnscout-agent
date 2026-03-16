"""
Mock resource library — returns a verified placeholder URL for all skills.
Resources are illustrative; the skill names and descriptions are real and personalised.
"""

MOCK_URL = "https://learn.microsoft.com/en-us/training/career-paths/"


def get_resources_for_skill(skill: str) -> list[dict]:
    """Return mock resource entries for a skill using the shared placeholder URL."""
    return [{"name": skill, "url": MOCK_URL}]
