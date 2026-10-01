# QR Code Generator

A simple web application to generate QR codes from URLs. Built with Flask and the `qrcode` library.

## Features

- Generate QR codes from any valid URL
- Download QR code as PNG
- Copy QR code to clipboard
- Clean, responsive UI
- No external CSS frameworks

## Installation

```bash
uv sync
```

## Usage

```bash
uv run python -m src.qr_code_generator.app
```

Open http://127.0.0.1:5000 in your browser.

## Project Structure

```
src/qr_code_generator/
├── app.py              # Flask application
└── templates/
    └── index.html      # Frontend template with embedded CSS/JS
```

## Requirements

- Python 3.12+
- Flask 3.x
- qrcode[pil] 8.x