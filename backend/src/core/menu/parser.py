import base64


def build_vision_content(files: list[dict], prompt: str) -> list[dict]:
    content = []
    for f in files:
        encoded = base64.standard_b64encode(f["data"]).decode("utf-8")
        media_type = f["file_type"]

        if media_type == "application/pdf":
            content.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": encoded,
                    },
                }
            )
        else:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": encoded,
                    },
                }
            )

    content.append({"type": "text", "text": prompt})
    return content


def normalize_ingredient(name: str) -> str:
    return name.strip().lower()
