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

## Usage

1. Open `http://127.0.0.1:5002` in your browser
2. Enter a valid URL in the input field
3. Click **Generate** to create your QR code
4. Download the QR code as a PNG image or copy it to your clipboard

## Technology Stack

- **Backend**: Flask 3.x
- **QR Code Generation**: qrcode[pil] 8.x
- **Frontend**: HTML, CSS, JavaScript (no frameworks)

## Configuration

The application runs on `127.0.0.1:5002` by default.

To change the host or port, modify the Flask configuration in `src/qr_code_generator/app.py`.

## License

This project is licensed under the terms of the [LICENSE](LICENSE) file.