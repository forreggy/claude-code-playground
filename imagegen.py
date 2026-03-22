"""Генерация картинки МЕМ ДНЯ через OpenAI Image API и наложение подписи через Pillow.

Экспортирует единственную публичную функцию generate_meme_image(),
которая генерирует картинку по промпту, накладывает текстовую подпись
и возвращает BytesIO с PNG, готовый для bot.send_photo().
При любой ошибке возвращает None — никогда не бросает исключение наружу.
"""

import base64
import io
import logging

import openai
from PIL import Image, ImageDraw, ImageFont

import config

logger = logging.getLogger(__name__)

_client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_START_SIZE = 48
_FONT_MIN_SIZE = 16
_PADDING_X = 40


def _overlay_caption(image_bytes: bytes, caption: str) -> io.BytesIO:
    """Наложить текстовую подпись на полупрозрачную плашку внизу картинки.

    Принимает PNG-байты и строку подписи на русском языке.
    Возвращает BytesIO с готовым PNG.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size

    # Загрузка шрифта с fallback
    font = None
    for font_size in range(_FONT_START_SIZE, _FONT_MIN_SIZE - 1, -2):
        try:
            candidate = ImageFont.truetype(_FONT_PATH, font_size)
        except OSError:
            logger.warning(
                "Шрифт %s не найден, используем встроенный (кириллица может не отображаться)",
                _FONT_PATH,
            )
            candidate = ImageFont.load_default()
            font = candidate
            break

        # Проверяем помещается ли текст по ширине
        bbox = candidate.getbbox(caption)
        text_width = bbox[2] - bbox[0]
        if text_width + _PADDING_X * 2 <= width:
            font = candidate
            break
    else:
        # Дошли до минимального размера — используем его
        try:
            font = ImageFont.truetype(_FONT_PATH, _FONT_MIN_SIZE)
        except OSError:
            font = ImageFont.load_default()

    # Создаём overlay для полупрозрачной плашки
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    bar_height = int(height * 0.18)
    bar_top = height - bar_height
    draw.rectangle(
        [(0, bar_top), (width, height)],
        fill=(0, 0, 0, 160),
    )

    # Центрируем текст внутри плашки
    bbox = font.getbbox(caption)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_x = (width - text_width) // 2
    text_y = bar_top + (bar_height - text_height) // 2

    draw.text((text_x, text_y), caption, font=font, fill=(255, 255, 255, 255))

    result = Image.alpha_composite(img, overlay)
    result = result.convert("RGB")

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def generate_meme_image(prompt: str, caption: str) -> io.BytesIO | None:
    """Сгенерировать картинку по промпту и наложить подпись.

    Использует OpenAI Image API для генерации, затем Pillow для наложения
    текстовой подписи на полупрозрачную плашку. Возвращает None при любой ошибке.
    """
    try:
        logger.info("Генерируем картинку МЕМ ДНЯ (модель: %s)", config.IMAGE_MODEL)

        response = await _client.images.generate(
            model=config.IMAGE_MODEL,
            prompt=prompt,
            n=1,
            size=config.IMAGE_SIZE,
            quality=config.IMAGE_QUALITY,
            response_format="b64_json",
        )

        image_bytes = base64.b64decode(response.data[0].b64_json)
        logger.info("Картинка сгенерирована, накладываем подпись")

        result = _overlay_caption(image_bytes, caption)
        logger.info("Картинка МЕМ ДНЯ готова")
        return result

    except Exception:
        logger.error("Ошибка при генерации картинки МЕМ ДНЯ", exc_info=True)
        return None
