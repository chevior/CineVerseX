def neutral_public_copy(value):
    text = str(value or "")
    replacements = (
        ("pan-Indian", "pan-language"),
        ("Pan-Indian", "Pan-language"),
        ("South Indian", "southern-language"),
        ("south Indian", "southern-language"),
        ("Indian", "multi-language"),
        ("India", "the market"),
        ("rural the region", "a remote community"),
        ("rural the market", "a remote community"),
        ("the region", "the story"),
        ("rural", "remote"),
        ("Rural", "Remote"),
        ("regional", "multi-language"),
        ("Regional", "Multi-language"),
    )

    for old, new in replacements:
        text = text.replace(old, new)

    cleanup_replacements = (
        ("rural the market", "a remote community"),
        ("rural the story", "a remote community"),
        ("remote the market", "a remote community"),
        ("remote the story", "a remote community"),
    )

    for old, new in cleanup_replacements:
        text = text.replace(old, new)

    return text
