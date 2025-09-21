
import json
from pathlib import Path
from typing import List, Optional, Tuple
from app.utils.models import ImageCategory, ImageStyle
from google.adk.tools import FunctionTool
from google.genai.types import Tool, FunctionDeclaration, Schema, Type


STYLE_PRESETS_PATH = (
    Path(__file__).resolve().parent.parent / "routes" / "style.json"
)

with STYLE_PRESETS_PATH.open("r", encoding="utf-8") as preset_file:
    raw_presets: dict[str, dict[str, str]] = json.load(preset_file)

STYLE_PRESETS: dict[str, Tuple[str, ImageCategory]] = {
    key.lower().strip(): (
        str(entry.get("prompt", "")).strip(),
        ImageCategory(entry.get("category", ImageCategory.TEMPLATE.value))
        if entry.get("category") in ImageCategory._value2member_map_
        else ImageCategory.TEMPLATE,
    )
    for key, entry in raw_presets.items()
}


def get_predefined_styles(
    style_value: Optional[str] = None,
) -> Tuple[Optional[str], Optional[ImageCategory], Optional[str]]:
    """
    Resolve style text and category from a potentially namespaced style value.
    """

    # --- Handle missing ---
    if style_value is None:
        return None, None, None

    # Extract raw string
    raw_value = style_value.value if isinstance(style_value, ImageStyle) else style_value
    if not isinstance(raw_value, str):
        raw_value = str(raw_value)

    raw_value = raw_value.strip()
    if not raw_value:
        return None, None, None

    key_norm = raw_value.lower()
    presets = STYLE_PRESETS

    if not presets:
        return None, None, None

    direct_match = presets.get(key_norm)
    if direct_match:
        prompt, category = direct_match
        return prompt, category, key_norm

    # --- Namespaced match ---
    attempts: List[Tuple[Optional[ImageCategory], str]] = []
    if ":" in key_norm:
        prefix, suffix = key_norm.split(":", 1)
        try:
            category = ImageCategory(prefix.strip().lower())
        except ValueError:
            category = None
        attempts.append((category, suffix or prefix))

    # Add raw fallback
    attempts.append((None, key_norm))

    # --- Check attempts ---
    for candidate_category, candidate in attempts:
        match = presets.get(candidate)
        if match:
            prompt, category = match
            resolved_category = category or candidate_category or ImageCategory.TEMPLATE
            return prompt, resolved_category, candidate

    # --- Nothing matched: fallback to normalized key ---
    return None, None, None


style_function_tool = FunctionTool(func=get_predefined_styles)
style_function_tool.custom_metadata = {
    "tool": Tool(
        function_declarations=[
            FunctionDeclaration(
                name="get_predefined_styles",
                description="Resolve style prompt metadata from a provided style value.",
                parameters=Schema(
                    type=Type.OBJECT,
                    properties={
                        "style_value": Schema(
                            type=Type.STRING,
                            description=(
                                "Optional style identifier or namespaced key to resolve "
                                "into a preset prompt and category."
                            ),
                            nullable=True,
                        )
                    },
                ),
            )
        ]
    ).model_dump(exclude_none=True),
}
