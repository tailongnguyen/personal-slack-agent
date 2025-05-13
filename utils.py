import re

def markdown_to_slack(md: str) -> str:
    """Convert basic Markdown to Slack-compatible mrkdwn."""
    
    # Bold: **text** or __text__ → *text*
    md = re.sub(r"(\*\*|__)(.*?)\1", r"*\2*", md)

    # Italic: *text* or _text_ → _text_
    md = re.sub(r"(?<!\*)\*(?!\*)(.*?)\*(?!\*)", r"_\1_", md)  # avoid bold
    md = re.sub(r"_(.*?)_", r"_\1_", md)

    # Strikethrough: ~~text~~ → ~text~
    md = re.sub(r"~~(.*?)~~", r"~\1~", md)

    # Inline code: `code` → `code`
    md = re.sub(r"`([^`]*)`", r"`\1`", md)

    # Blockquotes: > text → > text (Slack supports this directly)
    # No conversion needed

    # Links: [text](url) → <url|text>
    md = re.sub(r"\[(.*?)\]\((.*?)\)", r"<\2|\1>", md)

    return md