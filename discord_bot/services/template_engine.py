import re

def personalize_message(template: str, user_name: str | None = None, username: str | None = None) -> str:
    """
    Personalizes message templates by replacing any bracket variants of placeholders:
    (name), [name], {name}, <name>, (username), [username], {username}, <username>
    or generic Dutch greetings ('Schatje', 'Schat') anywhere in text with recipient display name.
    Uses lambda replacement to prevent regex backslash/escape crashes from fan display names.
    """
    display_name = (user_name or username or "").strip()
    if not display_name or display_name.lower() in ("fan", "user", "schatje", "schat"):
        display_name = "Schatje"

    result = template

    # 1. Replace (name), [name], {name}, <name>, (username), [username], {username}, <username> (case-insensitive)
    pattern = r'[\(\[\{\<]\s*(?:name|username)\s*[\)\]\}\>]'
    if display_name != "Schatje":
        result = re.sub(pattern, lambda m: display_name, result, flags=re.IGNORECASE)
    else:
        result = re.sub(pattern, lambda m: "Schatje", result, flags=re.IGNORECASE)

    # 2. Replace generic Dutch pet names "Schatje" or "Schat" anywhere in the template
    # e.g., "Hey schatje, ik lig..." -> "Hey Harr, ik lig..."
    if display_name != "Schatje":
        result = re.sub(r'\bSchatje\b', lambda m: display_name, result, flags=re.IGNORECASE)
        result = re.sub(r'\bSchat\b', lambda m: display_name, result, flags=re.IGNORECASE)

    return result.strip()
