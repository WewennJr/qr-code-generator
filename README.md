# QR Code Generator

A simple and customizable web application to generate QR codes from URLs. Built with Python, Flask, and the `qrcode` library.

## Features

- **QR Code Generation** - Generate QR codes from any valid URL
- **Download** - Download QR codes as PNG images
- **Clipboard** - Copy QR codes directly to your clipboard
- **Responsive UI** - Works on desktop and mobile
- **Lightweight** - No external CSS frameworks

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

```bash
# Clone the repository
git clone https://github.com/WewennJr/qr-code-generator.git
cd qr-code-generator

# Install dependencies with uv
uv sync

# Or with pip
pip install -e .
```

### Running the Web App

```bash
# Using uv
uv run qr_code_generator

# Or directly (after pip installation)
qr_code_generator
```

The app will be available at `http://127.0.0.1:5002`

## Requirements

- Python 3.12+
- Flask 3.x
- qrcode[pil] 8.x

## License

This project is licensed under the terms of the [LICENSE](LICENSE) file.