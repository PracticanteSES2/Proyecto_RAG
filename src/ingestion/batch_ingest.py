import json
from pathlib import Path

from docx_extractor import extract_docx


RAW_DIR = Path("data/raw")
OUTPUT_DIR = Path("data/processed")


def process_all_documents():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = list(RAW_DIR.glob("*.docx"))

    print(f"Documentos encontrados: {len(files)}")

    for file_path in files:

        print(f"Procesando: {file_path.name}")

        result = extract_docx(str(file_path))

        output_file = OUTPUT_DIR / f"{file_path.stem}.json"

        with open(
            output_file,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                result,
                f,
                ensure_ascii=False,
                indent=2
            )

        print(f"✓ Generado: {output_file}")


if __name__ == "__main__":
    process_all_documents()