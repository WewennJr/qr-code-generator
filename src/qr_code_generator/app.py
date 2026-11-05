import io
import base64
import json
import re
import secrets
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlsplit, urljoin

from flask import Flask, abort, g, render_template, request, send_file
from markupsafe import Markup
import qrcode
from PIL import Image, ImageDraw

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4 MB max request body

# Protect against decompression bombs
Image.MAX_IMAGE_PIXELS = 20_000_000

TRANSLATIONS_DIR = Path(__file__).parent / "translations"
BRANDS_DIR = Path(__file__).parent / "static" / "brands"

MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2MB
MAX_LOGO_DIMENSION_PX = 1000  # Downscale oversized logos before embedding
MAX_URL_LENGTH = 2048
MAX_GRADIENT_STOPS = 5
LOGO_MAX_DIMENSION = 0.28  # Logo plate max 28% of QR size for scannability
LOGO_PADDING_RATIO = 0.17  # White border around the logo, relative to the plate
LOGO_PLATE_RADIUS = 0.30  # Relative to the smaller plate side
LOGO_PLATE_SUPERSAMPLE = 4  # Render the logo plate at 4x then downscale

ALLOWED_MODULE_STYLES = {"square", "rounded", "dots", "diamond"}
ALLOWED_EYE_STYLES = {"square", "rounded", "circle"}
ALLOWED_GRADIENT_DIRECTIONS = {"vertical", "horizontal", "diagonal"}
ALLOWED_LOGO_FORMATS = {"PNG", "JPEG", "WEBP"}

HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

APP_LANGUAGES = ["fr", "en", "es", "de", "it", "pt", "nl", "pl"]

BRANDS = {
    "github": {"name": "GitHub", "color": "#181717"},
    "x": {"name": "X", "color": "#000000"},
    "instagram": {"name": "Instagram", "color": "#E4405F"},
    "linkedin": {"name": "LinkedIn", "color": "#0A66C2"},
    "youtube": {"name": "YouTube", "color": "#FF0000"},
    "whatsapp": {"name": "WhatsApp", "color": "#25D366"},
    "facebook": {"name": "Facebook", "color": "#1877F2"},
    "tiktok": {"name": "TikTok", "color": "#0f0f0f"},
    "google": {"name": "Google", "color": "#4285F4"},
    "apple": {"name": "Apple", "color": "#000000"},
    "amazon": {"name": "Amazon", "color": "#FF9900"},
    "microsoft": {"name": "Microsoft", "color": "#5E5E5E"},
    "discord": {"name": "Discord", "color": "#5865F2"},
    "spotify": {"name": "Spotify", "color": "#1DB954"},
    "telegram": {"name": "Telegram", "color": "#26A5E4"},
    "twitch": {"name": "Twitch", "color": "#9146FF"},
    "reddit": {"name": "Reddit", "color": "#FF4500"},
    "pinterest": {"name": "Pinterest", "color": "#BD081C"},
    "snapchat": {"name": "Snapchat", "color": "#FFFC00"},
    "netflix": {"name": "Netflix", "color": "#E50914"},
    "figma": {"name": "Figma", "color": "#F24E1E"},
}

_brand_svgs_cache: Optional[dict] = None


def load_translations(language: str) -> dict:
    if language not in APP_LANGUAGES:
        language = "en"
    translation_file = TRANSLATIONS_DIR / f"{language}.json"
    with translation_file.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_language() -> str:
    return request.accept_languages.best_match(APP_LANGUAGES) or "en"


def get_brands() -> dict:
    """Load bundled SVG brand icons (Id -> name, color, inline-safe svg text)."""
    global _brand_svgs_cache
    if _brand_svgs_cache is None:
        _brand_svgs_cache = {}
        for brand_id, meta in BRANDS.items():
            svg_file = BRANDS_DIR / f"{brand_id}.svg"
            try:
                svg_text = svg_file.read_text(encoding="utf-8")
            except OSError:
                continue
            _brand_svgs_cache[brand_id] = {
                "name": meta["name"],
                "color": meta["color"],
                "svg": Markup(svg_text),
            }
    return _brand_svgs_cache


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------


def is_valid_hex_color(value: str) -> bool:
    return bool(value) and bool(HEX_COLOR_RE.match(value))


def normalize_hex_value(value: str) -> str:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return f"#{value.upper()}"


def parse_hex_color(value: str, default: str) -> str:
    if value and is_valid_hex_color(value):
        return normalize_hex_value(value)
    return default


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = normalize_hex_value(hex_color).lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def interpolate_color(
    color1: Tuple[int, int, int], color2: Tuple[int, int, int], factor: float
) -> Tuple[int, int, int]:
    return tuple(int(c1 + (c2 - c1) * factor) for c1, c2 in zip(color1, color2))


def generate_gradient_colors(colors: List[str], steps: int) -> List[Tuple[int, int, int]]:
    if len(colors) < 2:
        return [hex_to_rgb(colors[0])] * steps

    rgb_colors = [hex_to_rgb(c) for c in colors]
    segment_steps = steps // (len(rgb_colors) - 1)
    remainder = steps % (len(rgb_colors) - 1)

    gradient = []
    for i in range(len(rgb_colors) - 1):
        current_steps = segment_steps + (1 if i < remainder else 0)
        for step in range(current_steps):
            factor = step / max(current_steps - 1, 1)
            gradient.append(interpolate_color(rgb_colors[i], rgb_colors[i + 1], factor))

    while len(gradient) < steps:
        gradient.append(rgb_colors[-1])

    return gradient[:steps]


# ---------------------------------------------------------------------------
# Logo handling
# ---------------------------------------------------------------------------


def decode_base64_image(value: str) -> Optional[bytes]:
    """Decode a `data:` URL (or raw base64) into raw image bytes."""
    if not value:
        return None
    if value.startswith("data:") and "," in value:
        header, value = value.split(",", 1)
        header = header.lower()
        if header not in (
            "data:image/png;base64",
            "data:image/jpeg;base64",
            "data:image/webp;base64",
        ):
            return None
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        return None


def sanitize_logo_image(logo_bytes: bytes) -> Optional[bytes]:
    """Validate and re-encode a user-provided logo to a clean PNG.

    Rejects non-raster formats (incl. SVG), strips metadata, and downscale
    oversized images. Returns None if the image is invalid.
    """
    try:
        with Image.open(io.BytesIO(logo_bytes)) as img:
            img_format = img.format
            if img_format not in ALLOWED_LOGO_FORMATS:
                return None
            img.load()

        with Image.open(io.BytesIO(logo_bytes)) as img:
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            if max(img.size) > MAX_LOGO_DIMENSION_PX:
                img.thumbnail((MAX_LOGO_DIMENSION_PX, MAX_LOGO_DIMENSION_PX), Image.Resampling.LANCZOS)

            clean = io.BytesIO()
            img.save(clean, format="PNG")
            clean.seek(0)
            return clean.getvalue()
    except Exception:
        return None


def tint_logo_png(logo_bytes: bytes, rgb: Tuple[int, int, int]) -> bytes:
    """Recolor every opaque pixel of the logo with a solid color (keeps alpha)."""
    img = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    alpha = img.getchannel("A")
    solid = Image.new("RGBA", img.size, (*rgb, 255))
    solid.putalpha(alpha)
    out = io.BytesIO()
    solid.save(out, format="PNG")
    out.seek(0)
    return out.getvalue()


def get_requested_logo() -> Optional[bytes]:
    """Get the logo bytes from either a file upload or a base64 data URL."""
    logo_file = request.files.get("logo_data")
    if logo_file and logo_file.filename:
        logo_bytes = logo_file.read()
        if not logo_bytes or len(logo_bytes) > MAX_LOGO_SIZE:
            return None
        return logo_bytes

    logo_b64 = request.form.get("logo_data", "")
    if logo_b64:
        logo_bytes = decode_base64_image(logo_b64)
        if not logo_bytes or len(logo_bytes) > MAX_LOGO_SIZE:
            return None
        return logo_bytes

    return None


# Logo plate corner radius adapting to the module style (relative to the
# smaller plate side); "circle" plates use a full round shape.
STYLE_LOGO_PLATE_RADIUS = {
    "square": 0.07,
    "rounded": LOGO_PLATE_RADIUS,
    "dots": 0.5,
    "diamond": 0.16,
}


def embed_logo_in_qr(
    qr_img: Image.Image,
    logo_data: bytes,
    back_color: str = "#ffffff",
    style: str = "rounded",
) -> Image.Image:
    """Embed a logo on a clean, anti-aliased plate matching the module style.

    The plate follows the logo aspect ratio (instead of a fixed square) and is
    rendered at 4x resolution then downscaled, so rounded corners and logo
    edges look crisp instead of pixelated.
    """
    try:
        logo = Image.open(io.BytesIO(logo_data))
        if logo.mode != "RGBA":
            logo = logo.convert("RGBA")

        qr_width, qr_height = qr_img.size
        qr_min = min(qr_width, qr_height)
        avail = int(qr_min * LOGO_MAX_DIMENSION)
        padding = int(avail * LOGO_PADDING_RATIO)
        inner_max = max(avail - 2 * padding, 8)
        plate_radius = STYLE_LOGO_PLATE_RADIUS.get(style, LOGO_PLATE_RADIUS)

        # Keep aspect ratio, fit the logo inside the plate with padding
        logo.thumbnail((inner_max * LOGO_PLATE_SUPERSAMPLE, inner_max * LOGO_PLATE_SUPERSAMPLE), Image.Resampling.LANCZOS)
        logo_hiw, logo_hih = logo.size

        plate_hiw = logo_hiw + 2 * padding * LOGO_PLATE_SUPERSAMPLE
        plate_hih = logo_hih + 2 * padding * LOGO_PLATE_SUPERSAMPLE
        hi_radius = int(min(plate_hiw, plate_hih) * plate_radius)

        plate = Image.new("RGBA", (plate_hiw, plate_hih), (0, 0, 0, 0))
        plate_draw = ImageDraw.Draw(plate)
        plate_draw.rounded_rectangle(
            [0, 0, plate_hiw - 1, plate_hih - 1],
            radius=hi_radius,
            fill=(*hex_to_rgb(back_color), 255),
        )
        plate.paste(logo, ((plate_hiw - logo_hiw) // 2, (plate_hih - logo_hih) // 2), logo)

        plate_w = plate_hiw // LOGO_PLATE_SUPERSAMPLE
        plate_h = plate_hih // LOGO_PLATE_SUPERSAMPLE
        plate = plate.resize((plate_w, plate_h), Image.Resampling.LANCZOS)

        qr_img = qr_img.convert("RGBA")
        plate_x = (qr_width - plate_w) // 2
        plate_y = (qr_height - plate_h) // 2

        qr_img.paste(plate, (plate_x, plate_y), plate)

        return qr_img.convert("RGB")
    except Exception:
        return qr_img


# ---------------------------------------------------------------------------
# QR drawing
# ---------------------------------------------------------------------------


def finder_positions(size: int, border: int):
    bs = border
    te = size - border  # top/right edge in module coords
    return [
        (bs, bs),  # top-left
        (te - 7, bs),  # top-right
        (bs, te - 7),  # bottom-left
    ]


def is_finder_pattern(x: int, y: int, size: int, border: int) -> bool:
    """Check if coordinates are within finder pattern areas (7x7 modules at 3 corners)."""
    for fx, fy in finder_positions(size, border):
        if fx <= x < fx + 7 and fy <= y < fy + 7:
            return True
    return False


def draw_module(
    draw: ImageDraw.Draw,
    px: int,
    py: int,
    box_size: int,
    color: Tuple[int, int, int],
    style: str,
):
    """Draw a single QR module based on style."""
    inset = max(1, box_size // 8)
    x0, y0 = px + inset, py + inset
    x1, y1 = px + box_size - inset, py + box_size - inset
    half_cx, half_cy = px + box_size // 2, py + box_size // 2

    if style == "dots":
        draw.ellipse([x0, y0, x1, y1], fill=color)
    elif style == "rounded":
        draw.rounded_rectangle([x0, y0, x1, y1], radius=(box_size - 2 * inset) // 2, fill=color)
    elif style == "diamond":
        draw.polygon(
            [(px + box_size // 2, y0), (x1, half_cy), (px + box_size // 2, y1), (x0, half_cy)],
            fill=color,
        )
    else:  # square
        draw.rectangle([px, py, px + box_size, py + box_size], fill=color)


def draw_finder_eye(
    draw: ImageDraw.Draw,
    fx: int,
    fy: int,
    box_size: int,
    color: Tuple[int, int, int],
    eye_style: str,
):
    """Draw a finder pattern ('eye') as a coherent shape instead of loose modules."""
    x0 = fx * box_size
    y0 = fy * box_size
    x1 = x0 + 7 * box_size
    y1 = y0 + 7 * box_size

    if eye_style == "circle":
        draw.ellipse([x0, y0, x1 - 1, y1 - 1], outline=color, width=box_size)
        dot = 3 * box_size
        cx, cy = x0 + 2 * box_size, y0 + 2 * box_size
        draw.ellipse([cx, cy, cx + dot - 1, cy + dot - 1], fill=color)
    elif eye_style == "rounded":
        draw.rounded_rectangle(
            [x0, y0, x1 - 1, y1 - 1], radius=2 * box_size, outline=color, width=box_size
        )
        dot = 3 * box_size
        cx, cy = x0 + 2 * box_size, y0 + 2 * box_size
        draw.rounded_rectangle(
            [cx, cy, cx + dot - 1, cy + dot - 1], radius=box_size // 2, fill=color
        )
    else:  # square
        draw.rectangle([x0, y0, x1 - 1, y1 - 1], outline=color, width=box_size)
        dot = 3 * box_size
        cx, cy = x0 + 2 * box_size, y0 + 2 * box_size
        draw.rectangle([cx, cy, cx + dot - 1, cy + dot - 1], fill=color)


def generate_qr_code(
    data: str,
    fill_color: str = "#000000",
    back_color: str = "#ffffff",
    gradient_colors: Optional[List[str]] = None,
    gradient_direction: str = "vertical",
    logo_data: Optional[bytes] = None,
    style: str = "square",
    eye_style: str = "square",
    eye_color: Optional[str] = None,
    logo_tint: bool = False,
) -> io.BytesIO:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    matrix = qr.get_matrix()
    size = len(matrix)
    box_size = 10
    border = 4
    img_size = size * box_size

    img = Image.new("RGB", (img_size, img_size), hex_to_rgb(back_color))
    draw = ImageDraw.Draw(img)

    module_count = size - 2 * border
    fill_rgb = hex_to_rgb(fill_color)
    use_gradient = bool(gradient_colors) and len(gradient_colors) >= 2
    gradient = generate_gradient_colors(gradient_colors, module_count) if use_gradient else None

    def color_at(x: int, y: int):
        """Module color at matrix coordinates: gradient-aware, QR color otherwise."""
        if gradient:
            gx = x - border
            gy = y - border
            if gradient_direction == "horizontal":
                return gradient[max(0, min(gx, module_count - 1))]
            if gradient_direction == "diagonal":
                return gradient[max(0, min(gx + gy, module_count - 1))]
            return gradient[max(0, min(gy, module_count - 1))]
        return fill_rgb

    # Without a custom eye color the eyes follow the QR code color
    # (fill color, or the gradient shade at each corner)
    eye_rgb = hex_to_rgb(eye_color) if eye_color else None

    for y, row in enumerate(matrix):
        for x, cell in enumerate(row):
            if not cell or is_finder_pattern(x, y, size, border):
                continue

            px = x * box_size
            py = y * box_size

            color = color_at(x, y)

            draw_module(draw, px, py, box_size, color, style)

    for fx, fy in finder_positions(size, border):
        draw_finder_eye(draw, fx, fy, box_size, eye_rgb or color_at(fx, fy), eye_style)

    if logo_data:
        if logo_tint:
            # Recolor the logo with the QR color at its center (gradient-aware)
            center_gx = max(0, (size - 2 * border) // 2)
            tint_rgb = color_at(center_gx + border, center_gx + border)
            logo_data = tint_logo_png(logo_data, tint_rgb)
        img = embed_logo_in_qr(img, logo_data, back_color, style)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Form parsing
# ---------------------------------------------------------------------------


def validate_url(url: str, translations: dict) -> Tuple[Optional[str], Optional[str]]:
    """Validate and canonicalize the URL. Returns (url, error_language_key)."""
    if not url:
        return None, "errors.empty_url"
    if len(url) > MAX_URL_LENGTH:
        return None, "errors.url_too_long"
    try:
        parts = urlsplit(url)
    except ValueError:
        return None, "errors.invalid_url"
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None, "errors.invalid_url"
    return url, None


def get_error_text(translations: dict, dotted_key: str) -> str:
    section, key = dotted_key.split(".", 1)
    return translations.get(section, {}).get(key, "Error")


def parse_qr_settings(translations: dict) -> Tuple[dict, Optional[bytes], Optional[str]]:
    """Parse and validate shared QR settings from the current request.

    Returns (settings, logo_bytes, error_message).
    """
    errors = []

    url = request.form.get("url", "").strip()
    url, url_error = validate_url(url, translations)
    if url_error:
        errors.append(get_error_text(translations, url_error))

    fill_color = parse_hex_color(request.form.get("fill_color"), "#000000")
    back_color = parse_hex_color(request.form.get("back_color"), "#ffffff")

    use_gradient = request.form.get("use_gradient") == "on"
    gradient_direction = request.form.get("gradient_direction", "vertical")
    if gradient_direction not in ALLOWED_GRADIENT_DIRECTIONS:
        gradient_direction = "vertical"

    gradient_colors = []
    for i in range(MAX_GRADIENT_STOPS):
        color = request.form.get(f"gradient_color_{i}")
        if color and is_valid_hex_color(color):
            gradient_colors.append(normalize_hex_value(color))
        # Unknown/invalid values are silently dropped

    style = request.form.get("style", "square")
    if style not in ALLOWED_MODULE_STYLES:
        style = "square"

    eye_style = request.form.get("eye_style", "square")
    if eye_style not in ALLOWED_EYE_STYLES:
        eye_style = "square"

    eye_color_input = request.form.get("eye_color", "")
    use_eye_color = request.form.get("use_eye_color") == "on"
    eye_color = None
    if use_eye_color and is_valid_hex_color(eye_color_input):
        eye_color = normalize_hex_value(eye_color_input)
    elif use_eye_color:
        errors.append(get_error_text(translations, "errors.invalid_eye_color"))

    logo_bytes = get_requested_logo()
    if request.files.get("logo_data") or request.form.get("logo_data"):
        if logo_bytes is None:
            errors.append(get_error_text(translations, "errors.logo_invalid"))
        else:
            logo_bytes = sanitize_logo_image(logo_bytes)
            if logo_bytes is None:
                errors.append(get_error_text(translations, "errors.logo_invalid"))

    settings = {
        "url": url,
        "fill_color": fill_color,
        "back_color": back_color,
        "use_gradient": use_gradient,
        "gradient_direction": gradient_direction,
        "gradient_colors": gradient_colors,
        "style": style,
        "eye_style": eye_style,
        "eye_color": eye_color,
        "logo_tint": request.form.get("logo_tint") == "on",
    }
    return settings, logo_bytes, (errors[0] if errors else None)


def build_qr_image(settings: dict, logo_bytes: Optional[bytes]) -> io.BytesIO:
    gradient = settings["gradient_colors"] if settings["use_gradient"] and len(settings["gradient_colors"]) >= 2 else None
    return generate_qr_code(
        settings["url"],
        fill_color=settings["fill_color"],
        back_color=settings["back_color"],
        gradient_colors=gradient,
        gradient_direction=settings["gradient_direction"],
        logo_data=logo_bytes,
        style=settings["style"],
        eye_style=settings["eye_style"],
        eye_color=settings["eye_color"],
        logo_tint=settings["logo_tint"],
    )


def build_form_data(settings: dict, logo_b64: Optional[str]) -> dict:
    return {
        "url": settings["url"] or "",
        "fill_color": settings["fill_color"],
        "back_color": settings["back_color"],
        "gradient_colors": settings["gradient_colors"] or ["#000000"],
        "gradient_direction": settings["gradient_direction"],
        "use_gradient": settings["use_gradient"],
        "style": settings["style"],
        "eye_style": settings["eye_style"],
        "use_eye_color": settings["eye_color"] is not None,
        "eye_color": settings["eye_color"] or "#2563eb",
        "logo_tint": settings.get("logo_tint", False),
        "logo_preview": logo_b64,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.before_request
def enforce_same_origin():
    """CSRF guard: browsers send Origin/Referer on POST; reject mismatches.

    Requests without those headers (curl, no-JS tools) are allowed.
    """
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None

    origin = request.headers.get("Origin")
    if origin:
        try:
            if urlsplit(origin).netloc != request.host:
                abort(403)
            return None
        except ValueError:
            abort(403)

    referrer = request.headers.get("Referer")
    if referrer:
        referrer_host = urljoin(referrer, "/")
        try:
            if urlsplit(referrer_host).netloc != request.host:
                abort(403)
        except ValueError:
            abort(403)
    return None


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if request.method == "POST":
        # Generated QR images embed user-provided URLs: never cache them
        response.headers["Cache-Control"] = "no-store"
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    nonce = f"'nonce-{g.get('csp_nonce')}' " if g.get("csp_nonce") else ""
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self'; "
        f"script-src 'self' {nonce}; "
        "form-action 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    )
    return response


@app.route("/", methods=["GET", "POST"])
def index():
    language = get_language()
    translations = load_translations(language)
    g.csp_nonce = secrets.token_urlsafe(16)

    qr_code_data = None
    error = None
    form_data = build_form_data(
        {
            "url": "",
            "fill_color": "#000000",
            "back_color": "#ffffff",
            "use_gradient": False,
            "gradient_direction": "vertical",
            "gradient_colors": ["#000000"],
            "style": "square",
            "eye_style": "square",
            "eye_color": None,
        },
        None,
    )

    if request.method == "POST":
        settings, logo_bytes, error = parse_qr_settings(translations)

        if not error and settings["url"]:
            try:
                buf = build_qr_image(settings, logo_bytes)
                qr_code_data = base64.b64encode(buf.getvalue()).decode("utf-8")
                if logo_bytes:
                    form_data["logo_preview"] = base64.b64encode(logo_bytes).decode("utf-8")
            except Exception:
                error = translations["errors"]["generation"]

        form_data = build_form_data({**settings, "use_eye_color": settings["eye_color"] is not None}, form_data.get("logo_preview"))

    return render_template(
        "index.html",
        qr_code_data=qr_code_data,
        error=error,
        translations=translations,
        language=language,
        form_data=form_data,
        brands=get_brands(),
        csp_nonce=g.csp_nonce,
    )


@app.route("/download", methods=["POST"])
def download():
    language = get_language()
    translations = load_translations(language)

    settings, logo_bytes, error = parse_qr_settings(translations)
    if error:
        return error, 400

    try:
        buf = build_qr_image(settings, logo_bytes)
    except Exception:
        return translations["errors"]["generation"], 500

    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=True,
        download_name="qrcode.png",
    )


def main():
    app.run(host="127.0.0.1", port=5002)


if __name__ == "__main__":
    main()
