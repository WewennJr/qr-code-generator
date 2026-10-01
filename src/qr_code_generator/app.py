import io
import base64
import json
from pathlib import Path

from flask import Flask, render_template, request, send_file
import qrcode

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


def generate_qr_code(data: str) -> io.BytesIO:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
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

    if request.method == "POST":
        url = request.form.get("url", "").strip()

        if not url:
            error = translations["errors"]["empty_url"]
        elif not (url.startswith("http://") or url.startswith("https://")):
            error = translations["errors"]["invalid_url"]
        else:
            try:
                buf = generate_qr_code(url)
                qr_code_data = base64.b64encode(buf.getvalue()).decode("utf-8")
            except Exception as e:
                error = f'{translations["errors"]["generation"]}: {str(e)}'

    return render_template(
        "index.html",
        qr_code_data=qr_code_data,
        error=error,
        translations=translations,
        language=language,
    )


@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url", "").strip()

    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return "Invalid URL", 400

    buf = generate_qr_code(url)

    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=True,
        download_name="qrcode.png",
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002)