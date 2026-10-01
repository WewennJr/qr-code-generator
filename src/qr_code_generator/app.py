import io
import base64
from flask import Flask, render_template, request, send_file
import qrcode

app = Flask(__name__)


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
    qr_code_data = None
    error = None

    if request.method == "POST":
        url = request.form.get("url", "").strip()
        if not url:
            error = "Veuillez entrer une URL"
        elif not (url.startswith("http://") or url.startswith("https://")):
            error = "L'URL doit commencer par http:// ou https://"
        else:
            try:
                buf = generate_qr_code(url)
                qr_code_data = base64.b64encode(buf.getvalue()).decode("utf-8")
            except Exception as e:
                error = f"Erreur lors de la génération : {str(e)}"

    return render_template("index.html", qr_code_data=qr_code_data, error=error)


@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url", "").strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return "URL invalide", 400

    buf = generate_qr_code(url)
    return send_file(buf, mimetype="image/png", as_attachment=True, download_name="qrcode.png")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002)