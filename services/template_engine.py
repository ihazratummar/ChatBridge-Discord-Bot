import re

def personalize_message(template: str, user_name: str | None = None, username: str | None = None) -> str:
    """
    Personalizes message templates by replacing any bracket variants of placeholders:
    (name), [name], {name}, <name>, (username), [username], {username}, <username>
    or leading generic Dutch greetings ('Schatje,') with recipient display name.
    Uses lambda replacement to prevent regex backslash/escape crashes from fan display names.
    """
    display_name = (user_name or username or "").strip()
    if not display_name:
        display_name = "Schatje"

    result = template

    # 1. Replace (name), [name], {name}, <name>, (username), [username], {username}, <username> (case-insensitive)
    pattern = r'[\(\[\{\<]\s*(?:name|username)\s*[\)\]\}\>]'
    result = re.sub(pattern, lambda m: display_name, result, flags=re.IGNORECASE)

    # 2. Replace leading generic "Schatje" if present at start of text
    # e.g., "Schatje, ik ben nat..." -> "THA, ik ben nat..."
    if display_name != "Schatje":
        result = re.sub(r'^\s*Schatje\b', lambda m: display_name, result, flags=re.IGNORECASE)

    return result.strip()
