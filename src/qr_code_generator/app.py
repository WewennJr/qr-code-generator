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


def generate_qr_code(
    data: str,
    fill_color: str = "#000000",
    back_color: str = "#ffffff",
    gradient_colors: Optional[List[str]] = None,
    gradient_direction: str = "vertical"
) -> io.BytesIO:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    matrix = qr.get_matrix()
    size = len(matrix)
    box_size = 10
    border = 4
    img_size = (size + 2 * border) * box_size
    
    img = Image.new("RGB", (img_size, img_size), hex_to_rgb(back_color))
    draw = ImageDraw.Draw(img)
    
    if gradient_colors and len(gradient_colors) >= 2:
        gradient = generate_gradient_colors(gradient_colors, size)
        
        for y, row in enumerate(matrix):
            for x, cell in enumerate(row):
                if cell:
                    px = (x + border) * box_size
                    py = (y + border) * box_size
                    
                    if gradient_direction == "horizontal":
                        color = gradient[x]
                    elif gradient_direction == "diagonal":
                        color = gradient[min(x + y, size - 1)]
                    else:
                        color = gradient[y]
                    
                    draw.rectangle([px, py, px + box_size, py + box_size], fill=color)
    else:
        fill_rgb = hex_to_rgb(fill_color)
        for y, row in enumerate(matrix):
            for x, cell in enumerate(row):
                if cell:
                    px = (x + border) * box_size
                    py = (y + border) * box_size
                    draw.rectangle([px, py, px + box_size, py + box_size], fill=fill_rgb)
    
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

        form_data.update({
            "url": url,
            "fill_color": fill_color,
            "back_color": back_color,
            "gradient_colors": gradient_colors if gradient_colors else ["#000000"],
            "gradient_direction": gradient_direction,
            "use_gradient": use_gradient,
        })

        if not url:
            error = translations["errors"]["empty_url"]
        elif not (url.startswith("http://") or url.startswith("https://")):
            error = translations["errors"]["invalid_url"]
        else:
            try:
                if use_gradient and len(gradient_colors) >= 2:
                    buf = generate_qr_code(
                        url,
                        fill_color=fill_color,
                        back_color=back_color,
                        gradient_colors=gradient_colors,
                        gradient_direction=gradient_direction,
                    )
                else:
                    buf = generate_qr_code(url, fill_color=fill_color, back_color=back_color)
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
            )
        else:
            buf = generate_qr_code(url, fill_color=fill_color, back_color=back_color)
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