import io
import base64
import json
from pathlib import Path
from typing import List, Optional, Tuple

from flask import Flask, render_template, request, send_file
import qrcode
from PIL import Image, ImageDraw

app = Flask(__name__)

TRANSLATIONS_DIR = Path(__file__).parent / "translations"

MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2MB
LOGO_MAX_DIMENSION = 0.22  # Logo max 22% of QR code size for scannability


def load_translations(language: str) -> dict:
    translation_file = TRANSLATIONS_DIR / f"{language}.json"

    if not translation_file.exists():
        translation_file = TRANSLATIONS_DIR / "en.json"

    with translation_file.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_language() -> str:
    return request.accept_languages.best_match(["fr", "en"]) or "en"


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def interpolate_color(color1: Tuple[int, int, int], color2: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
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


def embed_logo_in_qr(qr_img: Image.Image, logo_data: bytes) -> Image.Image:
    try:
        logo_img = Image.open(io.BytesIO(logo_data))
        
        if logo_img.mode != "RGBA":
            logo_img = logo_img.convert("RGBA")
        
        qr_width, qr_height = qr_img.size
        max_logo_size = int(min(qr_width, qr_height) * LOGO_MAX_DIMENSION)
        
        logo_img.thumbnail((max_logo_size, max_logo_size), Image.Resampling.LANCZOS)
        
        logo_width, logo_height = logo_img.size
        
        padding = 8
        bg_size = max(logo_width, logo_height) + 2 * padding
        bg_img = Image.new("RGBA", (bg_size, bg_size), (255, 255, 255, 255))
        
        bg_x = (bg_size - logo_width) // 2
        bg_y = (bg_size - logo_height) // 2
        bg_img.paste(logo_img, (bg_x, bg_y), logo_img)
        
        qr_x = (qr_width - bg_size) // 2
        qr_y = (qr_height - bg_size) // 2
        
        qr_img = qr_img.convert("RGBA")
        qr_img.paste(bg_img, (qr_x, qr_y), bg_img)
        
        return qr_img.convert("RGB")
    except Exception:
        return qr_img


def is_finder_pattern(x: int, y: int, size: int, border: int) -> bool:
    """Check if coordinates are within finder pattern areas (7x7 modules at 3 corners)."""
    # Top-left finder
    if border <= x < border + 7 and border <= y < border + 7:
        return True
    # Top-right finder
    if border <= x < border + 7 and size - border - 7 <= y < size - border:
        return True
    # Bottom-left finder
    if size - border - 7 <= x < size - border and border <= y < border + 7:
        return True
    return False


def generate_qr_code(
    data: str,
    fill_color: str = "#000000",
    back_color: str = "#ffffff",
    gradient_colors: Optional[List[str]] = None,
    gradient_direction: str = "vertical",
    logo_data: Optional[bytes] = None
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
    
    if gradient_colors and len(gradient_colors) >= 2:
        gradient = generate_gradient_colors(gradient_colors, module_count)
        
        for y, row in enumerate(matrix):
            for x, cell in enumerate(row):
                if cell:
                    px = x * box_size
                    py = y * box_size
                    
                    # Keep finder patterns solid for scannability
                    if is_finder_pattern(x, y, size, border):
                        color = fill_rgb
                    else:
                        gx = x - border
                        gy = y - border
                        
                        if gradient_direction == "horizontal":
                            color = gradient[max(0, min(gx, module_count - 1))]
                        elif gradient_direction == "diagonal":
                            color = gradient[max(0, min(gx + gy, module_count - 1))]
                        else:
                            color = gradient[max(0, min(gy, module_count - 1))]
                    
                    draw.rectangle([px, py, px + box_size, py + box_size], fill=color)
    else:
        for y, row in enumerate(matrix):
            for x, cell in enumerate(row):
                if cell:
                    px = x * box_size
                    py = y * box_size
                    draw.rectangle([px, py, px + box_size, py + box_size], fill=fill_rgb)
    
    if logo_data:
        img = embed_logo_in_qr(img, logo_data)
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


@app.route("/", methods=["GET", "POST"])
def index():
    language = get_language()
    translations = load_translations(language)

    qr_code_data = None
    error = None
    form_data = {
        "url": "",
        "fill_color": "#000000",
        "back_color": "#ffffff",
        "gradient_colors": ["#000000"],
        "gradient_direction": "vertical",
        "use_gradient": False,
        "logo_preview": None,
    }

    if request.method == "POST":
        url = request.form.get("url", "").strip()
        fill_color = request.form.get("fill_color", "#000000")
        back_color = request.form.get("back_color", "#ffffff")
        use_gradient = request.form.get("use_gradient") == "on"
        gradient_direction = request.form.get("gradient_direction", "vertical")
        
        gradient_colors = []
        for i in range(5):
            color = request.form.get(f"gradient_color_{i}")
            if color:
                gradient_colors.append(color)

        logo_file = request.files.get("logo")
        logo_data = None
        logo_preview = None
        
        if logo_file and logo_file.filename:
            logo_data = logo_file.read()
            if len(logo_data) > MAX_LOGO_SIZE:
                error = translations["errors"]["logo_too_large"]
            else:
                logo_preview = base64.b64encode(logo_data).decode("utf-8")

        form_data.update({
            "url": url,
            "fill_color": fill_color,
            "back_color": back_color,
            "gradient_colors": gradient_colors if gradient_colors else ["#000000"],
            "gradient_direction": gradient_direction,
            "use_gradient": use_gradient,
            "logo_preview": logo_preview,
        })

        if not url:
            error = translations["errors"]["empty_url"]
        elif not (url.startswith("http://") or url.startswith("https://")):
            error = translations["errors"]["invalid_url"]
        elif not error:
            try:
                if use_gradient and len(gradient_colors) >= 2:
                    buf = generate_qr_code(
                        url,
                        fill_color=fill_color,
                        back_color=back_color,
                        gradient_colors=gradient_colors,
                        gradient_direction=gradient_direction,
                        logo_data=logo_data,
                    )
                else:
                    buf = generate_qr_code(url, fill_color=fill_color, back_color=back_color, logo_data=logo_data)
                qr_code_data = base64.b64encode(buf.getvalue()).decode("utf-8")
            except Exception as e:
                error = f'{translations["errors"]["generation"]}: {str(e)}'

    return render_template(
        "index.html",
        qr_code_data=qr_code_data,
        error=error,
        translations=translations,
        language=language,
        form_data=form_data,
    )


@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url", "").strip()
    fill_color = request.form.get("fill_color", "#000000")
    back_color = request.form.get("back_color", "#ffffff")
    use_gradient = request.form.get("use_gradient") == "on"
    gradient_direction = request.form.get("gradient_direction", "vertical")
    
    gradient_colors = []
    for i in range(5):
        color = request.form.get(f"gradient_color_{i}")
        if color:
            gradient_colors.append(color)

    logo_file = request.files.get("logo")
    logo_data = None
    
    if logo_file and logo_file.filename:
        logo_data = logo_file.read()
        if len(logo_data) > MAX_LOGO_SIZE:
            return "Logo too large (max 2MB)", 400

    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return "Invalid URL", 400

    try:
        if use_gradient and len(gradient_colors) >= 2:
            buf = generate_qr_code(
                url,
                fill_color=fill_color,
                back_color=back_color,
                gradient_colors=gradient_colors,
                gradient_direction=gradient_direction,
                logo_data=logo_data,
            )
        else:
            buf = generate_qr_code(url, fill_color=fill_color, back_color=back_color, logo_data=logo_data)
    except Exception:
        return "Generation error", 500

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