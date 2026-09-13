from pathlib import Path


def main() -> None:
    output = Path('artifacts/map-summary.md')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('Example KDE artifact summary.\\n', encoding='utf-8')


if __name__ == '__main__':
    main()
