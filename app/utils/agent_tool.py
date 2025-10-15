
from typing import List, Optional, Tuple

from app.utils.models import ImageCategory, ImageStyle
from google.adk.tools import FunctionTool
from google.genai.types import FunctionDeclaration, Schema, Tool, Type


STYLE_PRESETS: dict[str, Tuple[str, ImageCategory]] = {
    # TEMPLATE category styles
    "polaroid": ("Create an authentic Polaroid-style snapshot that naturally combines two people in the same frame, capturing them in a spontaneous moment. Use gentle flash lighting that falls off around the edges to enhance the retro aesthetic, and add a subtle motion blur to suggest movement while keeping both individuals' facial features unchanged to avoid distortion or smoothing. Place them against a simple off-white curtain background reminiscent of a casual living room, and preserve the intimate pose of the two people hugging as they look toward the camera.", ImageCategory.TEMPLATE),
    "figure": ("Create a 1/7 scale commercialized figurine of the character in the picture, designed in a realistic style and placed within a real environment on a computer desk. The figurine should stand on a round transparent acrylic base, while the computer screen beside it displays the 3D modeling process of this same figurine, creating a natural connection between the physical and digital forms. Next to the monitor, include a toy packaging box styled like a high-quality collectible figure, printed with original artwork that features two-dimensional flat illustrations of the figurine, seamlessly tying the presentation together.", ImageCategory.TEMPLATE),
    "foodie": ("Photograph this product on a table against a solid background, styled in a dramatic modern scene where the key ingredients appear fresh and raw, flying outward in an explosive dynamic arrangement that highlights both freshness and nutritional value. Present the composition as a promotional ad shot without text, ensuring the product remains the central focus while the background incorporates the key brand colors to unify the overall visual impact.", ImageCategory.TEMPLATE),
    "explosive": ("Double exposure, Midjourney style, merging, blending, and overlaying in a stunning composition inspired by Yukisakura. Create an exceptional double exposure masterpiece where the silhouette of the uploaded human figure is harmoniously intertwined with visually striking, rugged landscapes during a lively spring season. Within the silhouette, reveal sun-bathed pine forests, towering mountain peaks, and a lone horse cutting through the trail, each element echoing outward to add depth, narrative, and solitude. Build beautiful tension by setting the figure against a stark monochrome background that maintains razor-sharp contrast, drawing all focus to the richly layered double exposure. Characterize the piece with a vibrant full-color scheme inside the silhouette and crisp, deliberate lines that trace every contour with emotional precision.", ImageCategory.TEMPLATE),
    "card": ("A close-up shot of a hand holding a business card designed to look like a JSON file opened in VS Code, with realistic syntax-highlighted JSON code. The card appears exactly like a VS Code window, complete with toolbar icons and a title bar labeled Business Card.json. The background is softly blurred to keep the focus on the card. The JSON on the card dynamically displays user information in this format: { 'name': 'actual name', 'title': 'actual title', 'email': 'actual email', 'link': 'actual link' }, rendered as realistic highlighted code inside the card.", ImageCategory.TEMPLATE),
    "bubblehead": ("Turn this photo into a bobblehead: enlarge the head slightly, keep the face accurate and cartoonify the body. [Place it on a bookshelf].", ImageCategory.TEMPLATE),
    "keychain": ("A close-up photo of a cute, colorful keychain held by person's hand. The keychain features a chibi-style of the [attached image ]. The keychain is made of soft rubber with bold black outlines and attached to a small silver keyring, neutral background", ImageCategory.TEMPLATE),
    "cyberpank": ("A highly detailed miniature [Cyberpunk] landscape viewed from above, using a tilt-shift lens effect. The scene is filled with toy-like elements, all rendered in high-resolution CG. Dramatic lighting creates a cinematic atmosphere, with vivid colors and strong contrast, emphasizing depth of field and a realistic micro-perspective, making the viewer feel as if overlooking a toy world. The image contains many visual jokes and details worth repeated viewing. Take uploaded image as the reference", ImageCategory.TEMPLATE),
    "gaming": ("Ultra-realistic 3D rendered image that replicates the character design of the person from the uploaded image. The scene is set in a dim and cluttered bedroom from the year 2008. Take the carachter from uploaded image, keep the face and all other details consistent.The character is sitting on the carpet, facing an old-fashioned television that is playing Command & Conquer: Red Alert 3 and a game console controller. The entire room is filled with a nostalgic atmosphere of the year 2008: snack packaging bags, soda cans, posters, and tangled wires are everywhere.The person from the image is captured in the moment of turning her or his head, looking back at the camera over theshoulder. There is an innocent smile on persons iconic ethereally beautiful face. Upper body is slightly twisted, with a natural dynamic, as if person is reacting to being startled by the flash. The flash slightly overexposes face and clothes, making the silhouette stand out more prominently in the dimly lit room. The whole photo appears raw and natural. The strong contrast between light and dark casts deep shadows behind the person. The image is full of tactile feel, with a simulated texture that resembles an authentic film snapshot from 2008. If user inputs different theme - change the video on the screen and the posters in the room accordingly", ImageCategory.TEMPLATE),
    "aging": ("A hyper-realistic portrait of [uploaded person], aged to approximately 60 years old. Preserve the person's facial identity and unique features, but naturally add signs of aging: subtle wrinkles, fine lines, slight sagging skin, natural gray or salt-and-pepper hair, and softened facial contours. Keep the look elegant and dignified, with realistic skin texture and details. Studio photography lighting, cinematic sharpness, ultra-detailed, high-resolution, professional editorial portrait style.", ImageCategory.TEMPLATE),
    "bench": ("Hyper-real studio portrait of [uploaded image] lounging on a park bench; low camera angle with one sneaker sole big in the foreground (strong foreshortening). Bench is painted/wrapped with [the brand that user inputs if none then user any of famous brands, dont ask user to insert it] colors and graphics. Seamless [the colors that user inputs if none - set random bright color yourself, dont ask user] background, premium magazine lighting, soft shadows, clean minimal set, sharp focus, ultra-detailed skin/fabric, 3:4 ratio, no watermark.", ImageCategory.TEMPLATE),
    "restore": ("Please this old photo into 1080 x 1920 pixels, with an aesthetic and modern photography look, making it appear authentic and keep the colors realistic.", ImageCategory.TEMPLATE),
    "isometric": ("Isometric 3D render of [of uploaded image or the text prompt of the user or both], on a plain white background. Soft, even lighting with smooth shadows. Clean, sharp focus, high detail, and warm, natural colors. High-resolution, Blender-style quality.", ImageCategory.TEMPLATE),
    "burning": ("A close-up, cinematic portrait of [uploaded person photo] sitting at the open door of a classic car at night. The scene is filled with blazing orange light, glowing embers, and swirling sparks surrounding the car, as if the air itself is alive with heat and energy. The brilliant glow reflects on the person's face, highlighting a fearless, intense expression with sharp shadows. The shot is closer, emphasizing the dramatic aura, radiant atmosphere, and fiery background that engulfs the scene. Hyper-detailed, photorealistic, gritty, and cinematic style with vivid contrast and glowing intensity.", ImageCategory.TEMPLATE),
    "ads": ("Transform the uploaded {juice bottle} into a {cinematic commercial advertisement} where the entire bottle is visually constructed from fresh {fruit type}. Each {grape/fruit} piece should form the shape of the bottle, with natural stems and leaves integrated seamlessly. Add {morning sunlight} and a {vineyard/orchard background} for realism. Highlight {freshness}, {juiciness}, and {natural quality}. The {label of the original bottle} should remain clearly visible on the fruit-formed surface. Style: {photorealistic}, {high detail}, {premium advertising look}. Ratio: {3:4 or 4:5} — ultra-HD quality.{fruit type} = grapes, oranges, pomegranates, strawberries, etc.", ImageCategory.TEMPLATE),
    "gta": ("Create a GTA-style poster artwork featuring the [uploaded person or theme]. Use the signature Rockstar Games poster design: bold cell-shaded illustration, thick outlines, saturated colors, and cinematic framing. Split the poster into multiple dynamic panels, each showing a different scene or action shot of the subject — such as driving, posing, or holding props relevant to the character/theme. Include urban backdrops, neon lights, and dramatic perspectives to capture the gritty yet stylish GTA aesthetic. The overall composition should feel like an official Grand Theft Auto promotional poster, striking and iconic.", ImageCategory.TEMPLATE),
    "reflection": ("In a dimly lit bathroom, the person from the first picture stands on the left side, seen from behind as they face a mirror above a white sink with a silver faucet, the faint outline of a glass shower visible in the background. Shadows and soft light envelop the real side of the room, creating a subdued, almost eerie stillness, yet in the mirror's reflection emerges the armored warrior from the second picture, unchanged in design and radiant in a focused glow. This contrast between darkness and light bridges the ordinary and the extraordinary, infusing the scene with a mysterious, suspenseful tension as the two worlds seem to meet within the mirror's surface.", ImageCategory.TEMPLATE),
    
    # FIT category styles can be added below if needed.
    # "fit_style_1": ("Your FIT prompt here", ImageCategory.FIT),
}

LIGHTBOX_TEMPLATE_PRESETS: dict[str, Tuple[str, ImageCategory]] = {
    "studio": (
        "A high-resolution, studio-lit product photograph featuring the hero item from the first reference image staged within the context of the second reference image. Use soft three-point lighting with clean diffusion, subtle reflections, and a minimal gradient backdrop. Preserve the product's exact colors, logos, and material textures while emphasizing technical camera guidance such as f/8 aperture, ISO 200, and 1/160 shutter speed. Include negative direction like 'retain design integrity and color accuracy as in source' and 'avoid plain backgrounds or altering brand colors.'",
        ImageCategory.TEMPLATE,
    ),
    "lifestyle": (
        "A lifestyle product showcase that blends the item from the first reference image into the scene of the second reference image. Capture cinematic natural lighting with shallow depth of field so the product stays in sharp focus while the environment supports the story. Describe materials, finishes, and branding exactly as provided and reinforce guardrails such as 'retain design integrity and color accuracy as in source' and 'avoid removing logos or changing patterns.'",
        ImageCategory.TEMPLATE,
    ),
}

STYLE_PRESETS.update(LIGHTBOX_TEMPLATE_PRESETS)
# Provide grouped aliases so the UI can present categorized template presets.
for key, value in list(STYLE_PRESETS.items()):
    prompt, category = value
    if category == ImageCategory.TEMPLATE and ":" not in key:
        STYLE_PRESETS.setdefault(f"styles:{key}", value)

for key, value in LIGHTBOX_TEMPLATE_PRESETS.items():
    STYLE_PRESETS.setdefault(f"lightbox:{key}", value)
    STYLE_PRESETS.setdefault(f"template:lightbox:{key}", value)
    STYLE_PRESETS.setdefault(f"template:{key}", value)


def resolve_styles_for_tool(
    style_value: Optional[str] = None,
) -> dict[str, Optional[str]]:
    """Resolve style prompt metadata from a provided style value."""
    
    if style_value is None:
        return {"prompt": None, "category": None, "normalized_style": None}

    raw_value = style_value.value if isinstance(style_value, ImageStyle) else style_value
    if not isinstance(raw_value, str):
        raw_value = str(raw_value)

    raw_value = raw_value.strip()
    if not raw_value:
        return {"prompt": None, "category": None, "normalized_style": None}

    key_norm = raw_value.lower()

    if not STYLE_PRESETS:
        return {"prompt": None, "category": None, "normalized_style": None}

    direct_match = STYLE_PRESETS.get(key_norm)
    if direct_match:
        prompt, category = direct_match
        return {
            "prompt": prompt,
            "category": category.value if isinstance(category, ImageCategory) else category,
            "normalized_style": key_norm,
        }

    # Namespaced match
    attempts: List[Tuple[Optional[ImageCategory], str]] = []
    if ":" in key_norm:
        prefix, suffix = key_norm.split(":", 1)
        try:
            category = ImageCategory(prefix.strip().lower())
        except ValueError:
            category = None
        attempts.append((category, suffix or prefix))

    attempts.append((None, key_norm))

    for candidate_category, candidate in attempts:
        match = STYLE_PRESETS.get(candidate)
        if match:
            prompt, category = match
            resolved_category = category or candidate_category or ImageCategory.TEMPLATE
            return {
                "prompt": prompt,
                "category": resolved_category.value if isinstance(resolved_category, ImageCategory) else resolved_category,
                "normalized_style": candidate,
            }

    return {"prompt": None, "category": None, "normalized_style": None}


style_function_tool = FunctionTool(func=resolve_styles_for_tool)
style_function_tool.custom_metadata = {
    "tool": Tool(
        function_declarations=[
            FunctionDeclaration(
                name="resolve_styles_for_tool",
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
