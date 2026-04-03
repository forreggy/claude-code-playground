"""
Скрипт инвентаризации кодовой базы TaigaBot Lite.
Запускать из корня репозитория: python3 docs/raw/collect_inventory.py
Результаты записываются в docs/raw/*.txt
"""

import ast
import os
import re
from datetime import datetime
from pathlib import Path

# Скрипт в docs/raw/, parent — docs/, parent.parent — корень репозитория
ROOT = Path(__file__).resolve().parent.parent

# Проверим что ROOT — действительно корень репозитория (есть CLAUDE.md)
if not (ROOT / "CLAUDE.md").exists():
    ROOT = Path.cwd()

OUT_DIR = ROOT / "docs" / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

GENERATION_DATE = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

EXCLUDE_DIRS = {".git", "venv", "__pycache__", "docs"}
EXCLUDE_EXTENSIONS = {".pyc", ".pyo"}


def header(title: str) -> str:
    return f"# Сгенерировано: {GENERATION_DATE}\n# {title}\n{'=' * 60}\n\n"


# ---------------------------------------------------------------------------
# 01_file_tree.txt
# ---------------------------------------------------------------------------

def collect_file_tree() -> None:
    out_path = OUT_DIR / "01_file_tree.txt"
    lines: list[str] = [header("Дерево файлов репозитория")]

    for path in sorted(ROOT.rglob("*")):
        # Пропускаем директории из исключений
        parts = path.relative_to(ROOT).parts
        if any(p in EXCLUDE_DIRS for p in parts):
            continue
        if path.suffix in EXCLUDE_EXTENSIONS:
            continue
        if path.is_file():
            lines.append(str(path.relative_to(ROOT)))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] {out_path.name}: {len(lines) - 1} файлов")


# ---------------------------------------------------------------------------
# 02_python_signatures.txt
# ---------------------------------------------------------------------------

def _get_decorator_str(decorator: ast.expr) -> str:
    """Возвращает строковое представление декоратора."""
    if isinstance(decorator, ast.Name):
        return f"@{decorator.id}"
    elif isinstance(decorator, ast.Attribute):
        return f"@{ast.unparse(decorator)}"
    elif isinstance(decorator, ast.Call):
        return f"@{ast.unparse(decorator)}"
    return f"@{ast.unparse(decorator)}"


def _get_docstring(node: ast.AST) -> str | None:
    """Возвращает первую строку docstring если есть."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
        docstring = ast.get_docstring(node)
        if docstring:
            first_line = docstring.strip().split("\n")[0]
            return first_line
    return None


def _extract_signatures(source: str, filename: str) -> list[str]:
    """Извлекает сигнатуры функций и классов из Python-файла через AST."""
    results: list[str] = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [f"  [ОШИБКА ПАРСИНГА: {e}]"]

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            entry_lines: list[str] = []

            # Декораторы
            for dec in node.decorator_list:
                entry_lines.append(f"  {_get_decorator_str(dec)}")

            # Сигнатура
            if isinstance(node, ast.ClassDef):
                bases = ", ".join(ast.unparse(b) for b in node.bases) if node.bases else ""
                sig = f"class {node.name}({bases}):" if bases else f"class {node.name}:"
                entry_lines.append(f"  {sig}  [line {node.lineno}]")
            else:
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                try:
                    args_str = ast.unparse(node.args)
                except Exception:
                    args_str = "..."
                returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                sig = f"{prefix} {node.name}({args_str}){returns}:"
                entry_lines.append(f"  {sig}  [line {node.lineno}]")

            # Docstring
            doc = _get_docstring(node)
            if doc:
                entry_lines.append(f'    """{doc}"""')

            results.extend(entry_lines)
            results.append("")

    return results


def collect_python_signatures() -> None:
    out_path = OUT_DIR / "02_python_signatures.txt"
    lines: list[str] = [header("Сигнатуры функций и классов Python")]

    py_files = sorted(
        p for p in ROOT.rglob("*.py")
        if not any(part in EXCLUDE_DIRS for part in p.relative_to(ROOT).parts)
    )

    total_defs = 0
    for py_file in py_files:
        rel = py_file.relative_to(ROOT)
        lines.append(f"\n### {rel}\n")
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            lines.append(f"  [ОШИБКА ЧТЕНИЯ: {e}]\n")
            continue

        sigs = _extract_signatures(source, str(rel))
        lines.extend(sigs)
        count = sum(1 for s in sigs if "def " in s or "class " in s)
        total_defs += count

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] {out_path.name}: {total_defs} def/class в {len(py_files)} файлах")


# ---------------------------------------------------------------------------
# 03_http_endpoints.txt
# ---------------------------------------------------------------------------

def collect_http_endpoints() -> None:
    out_path = OUT_DIR / "03_http_endpoints.txt"
    lines: list[str] = [header("HTTP-эндпоинты (app.router.add_*)")]

    pattern = re.compile(r"app\.router\.add_")
    found = 0

    py_files = sorted(
        p for p in ROOT.rglob("*.py")
        if not any(part in EXCLUDE_DIRS for part in p.relative_to(ROOT).parts)
    )

    for py_file in py_files:
        rel = py_file.relative_to(ROOT)
        try:
            for lineno, line in enumerate(
                py_file.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if pattern.search(line):
                    lines.append(f"{rel}:{lineno}: {line.rstrip()}")
                    found += 1
        except Exception as e:
            lines.append(f"{rel}: [ОШИБКА ЧТЕНИЯ: {e}]")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] {out_path.name}: {found} эндпоинтов")


# ---------------------------------------------------------------------------
# 04_telegram_handlers.txt
# ---------------------------------------------------------------------------

def collect_telegram_handlers() -> None:
    out_path = OUT_DIR / "04_telegram_handlers.txt"
    lines: list[str] = [header("Telegram-хэндлеры (router.message, @router.*, и др.)")]

    pattern = re.compile(
        r"(router\.message|router\.callback_query|router\.my_chat_member|@router\.)"
    )
    found = 0

    py_files = sorted(
        p for p in ROOT.rglob("*.py")
        if not any(part in EXCLUDE_DIRS for part in p.relative_to(ROOT).parts)
    )

    for py_file in py_files:
        rel = py_file.relative_to(ROOT)
        try:
            for lineno, line in enumerate(
                py_file.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if pattern.search(line):
                    lines.append(f"{rel}:{lineno}: {line.rstrip()}")
                    found += 1
        except Exception as e:
            lines.append(f"{rel}: [ОШИБКА ЧТЕНИЯ: {e}]")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] {out_path.name}: {found} хэндлеров")


# ---------------------------------------------------------------------------
# 05_database_schema.txt
# ---------------------------------------------------------------------------

def collect_database_schema() -> None:
    out_path = OUT_DIR / "05_database_schema.txt"
    lines: list[str] = [header("SQL-запросы и схема БД")]

    sql_keywords_re = re.compile(
        r"\b(CREATE TABLE|CREATE INDEX|PRAGMA|INSERT\s+INTO|SELECT\s|UPDATE\s|DELETE\s+FROM)\b",
        re.IGNORECASE,
    )
    # Также ищем строки вида "cursor.execute", "await db.execute" и т.п.
    execute_re = re.compile(r"\.(execute|executemany)\s*\(")

    found = 0

    py_files = sorted(
        p for p in ROOT.rglob("*.py")
        if not any(part in EXCLUDE_DIRS for part in p.relative_to(ROOT).parts)
    )

    for py_file in py_files:
        rel = py_file.relative_to(ROOT)
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            source_lines = source.splitlines()

            # Одиночные строки с SQL
            for lineno, line in enumerate(source_lines, 1):
                if sql_keywords_re.search(line) or execute_re.search(line):
                    lines.append(f"{rel}:{lineno}: {line.rstrip()}")
                    found += 1

            # Многострочные SQL в тройных кавычках
            multiline_re = re.compile(r'("""|\'\'\')(.*?)\1', re.DOTALL)
            for m in multiline_re.finditer(source):
                content = m.group(2)
                if sql_keywords_re.search(content):
                    start_line = source[: m.start()].count("\n") + 1
                    end_line = source[: m.end()].count("\n") + 1
                    lines.append(
                        f"\n{rel}:{start_line}-{end_line} [многострочный SQL]:\n"
                        + "\n".join(f"  {l}" for l in content.strip().splitlines())
                        + "\n"
                    )
                    found += 1

        except Exception as e:
            lines.append(f"{rel}: [ОШИБКА ЧТЕНИЯ: {e}]")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] {out_path.name}: {found} SQL-вхождений")


# ---------------------------------------------------------------------------
# 06_env_variables.txt
# ---------------------------------------------------------------------------

def collect_env_variables() -> None:
    out_path = OUT_DIR / "06_env_variables.txt"
    lines: list[str] = [header("Переменные окружения и обращения к конфигурации")]

    pattern = re.compile(r"(os\.getenv|os\.environ|config\.)")
    found = 0

    py_files = sorted(
        p for p in ROOT.rglob("*.py")
        if not any(part in EXCLUDE_DIRS for part in p.relative_to(ROOT).parts)
    )

    for py_file in py_files:
        rel = py_file.relative_to(ROOT)
        try:
            for lineno, line in enumerate(
                py_file.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if pattern.search(line):
                    lines.append(f"{rel}:{lineno}: {line.rstrip()}")
                    found += 1
        except Exception as e:
            lines.append(f"{rel}: [ОШИБКА ЧТЕНИЯ: {e}]")

    # Содержимое .env.example
    env_example = ROOT / ".env.example"
    if env_example.exists():
        lines.append(f"\n\n{'=' * 60}")
        lines.append(f"# Содержимое .env.example")
        lines.append(f"{'=' * 60}\n")
        try:
            lines.append(env_example.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            lines.append(f"[ОШИБКА ЧТЕНИЯ .env.example: {e}]")
    else:
        lines.append("\n[.env.example не найден]")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] {out_path.name}: {found} обращений к конфигурации")


# ---------------------------------------------------------------------------
# 07_requirements.txt
# ---------------------------------------------------------------------------

def collect_requirements() -> None:
    out_path = OUT_DIR / "07_requirements.txt"
    req_file = ROOT / "requirements.txt"

    lines: list[str] = [header("Зависимости проекта (requirements.txt)")]

    if req_file.exists():
        try:
            lines.append(req_file.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            lines.append(f"[ОШИБКА ЧТЕНИЯ: {e}]")
    else:
        lines.append("[requirements.txt не найден]")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] {out_path.name}")


# ---------------------------------------------------------------------------
# 08_html_templates.txt
# ---------------------------------------------------------------------------

def collect_html_templates() -> None:
    out_path = OUT_DIR / "08_html_templates.txt"
    lines: list[str] = [header("HTML-шаблоны (templates/)")]

    templates_dir = ROOT / "templates"
    if not templates_dir.exists():
        lines.append("[Директория templates/ не найдена]")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"[OK] {out_path.name}: директория templates/ не найдена")
        return

    html_files = sorted(templates_dir.rglob("*.html"))

    for html_file in html_files:
        rel = html_file.relative_to(ROOT)
        size = html_file.stat().st_size
        lines.append(f"\n### {rel}  ({size} байт)\n")

        try:
            content = html_file.read_text(encoding="utf-8", errors="replace")
            all_lines = content.splitlines()

            # Первые 5 строк
            lines.append("Первые 5 строк:")
            for i, l in enumerate(all_lines[:5], 1):
                lines.append(f"  {i:3d}: {l}")

            # <script блоки
            lines.append("\n<script> блоки:")
            script_re = re.compile(r"<script", re.IGNORECASE)
            script_found = False
            for lineno, l in enumerate(all_lines, 1):
                if script_re.search(l):
                    snippet = l.rstrip()[:80]
                    lines.append(f"  {lineno:4d}: {snippet}")
                    script_found = True
            if not script_found:
                lines.append("  (нет <script> блоков)")

        except Exception as e:
            lines.append(f"  [ОШИБКА ЧТЕНИЯ: {e}]")

        lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] {out_path.name}: {len(html_files)} шаблонов")


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Корень репозитория: {ROOT}")
    print(f"Выходная директория: {OUT_DIR}")
    print(f"Дата генерации: {GENERATION_DATE}\n")

    collect_file_tree()
    collect_python_signatures()
    collect_http_endpoints()
    collect_telegram_handlers()
    collect_database_schema()
    collect_env_variables()
    collect_requirements()
    collect_html_templates()

    print("\nГотово. Все файлы записаны в docs/raw/")


if __name__ == "__main__":
    main()
