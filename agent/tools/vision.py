"""Optional visual utilities from classic JARVIS projects."""

def ocr_image(image_path: str) -> str:
    from pathlib import Path
    path=Path(str(image_path).strip().strip('"')).expanduser()
    if not path.exists(): raise FileNotFoundError(f"Изображение не найдено: {path}")
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("OCR требует pytesseract и Tesseract OCR. Основной JARVIS продолжит работать без OCR.") from exc
    text=pytesseract.image_to_string(Image.open(path), lang="rus+eng").strip()
    return text if text else "Текст на изображении не найден."
