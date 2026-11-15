import re
import json
from pathlib import Path

from dataSource import load_config

CONFIG_FILE = load_config()
    

def replace_text(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

        content = re.sub(r"\\\\n", "<br>", content)
        content = re.sub(r"<color=#(FF9999FF|99FFFFFF|80FFD7FF|99FF88FF|FFACFFFF|80C0FFFF|FFE699FF)>(.*?)</color>", r"{{Color|\2}}", content)
        content = re.sub(r'(<br>|")<color=#FFD780FF>(.*?)</color>', r"\1'''\2'''", content)
        content = re.sub(r"<color=#FFD780FF>(.*?)</color>", r"\1", content)
        content = re.sub(r"<color=#3399CCFF>(.*?)</color>", r"{{Color|buzz|\1}}", content)
        content = re.sub(r"<color=#f39001>(.*?)</color>", r"{{Color|bp|\1}}", content)
        content = re.sub(r'·(.*?)(<br>|(?<!\\)")', r"<li>\1</li>\2", content)
        content = re.sub(r"</li><br>", r"</li>", content)
        content = re.sub(r"(<li>.*</li>)", r"<ul>\1</ul>", content)

        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(content)

        print(f"Replacements completed and saved to {file_path}")
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        raise
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise
        
        
def merge_jsons(sources, output_file):
    merged_content = {}
    for source in sources:
        with open(source, 'r', encoding = 'utf-8') as file:
            merged_content.update(json.load(file))
    
    with open(output_file, 'w', encoding = 'utf-8') as file:
        json.dump(merged_content, file, ensure_ascii = False, indent=2)


def numbered_parts(directory, prefix):
    parts = []
    for path in directory.glob(f'{prefix}_*.json'):
        match = re.fullmatch(re.escape(prefix) + r'_(\d+)\.json', path.name)
        if match:
            parts.append((int(match.group(1)), path))
    return [path for _, path in sorted(parts)]


def textmap_sources(directory, lang):
    '''Main map, its numbered parts, then the Medium map and its parts; later files override earlier ones.

    Sources split languages differently (e.g. RU_0/RU_1 vs a single RU, TH_0/TH_1 vs TH_1/TH_2).
    '''
    sources = []
    for prefix in (f'TextMap{lang}', f'TextMap_Medium{lang}'):
        whole = directory / f'{prefix}.json'
        sources += ([whole] if whole.is_file() else []) + numbered_parts(directory, prefix)
    if not sources:
        raise FileNotFoundError(f'No TextMap files found for {lang} in {directory}')
    return sources
        

repl_langs = ["EN"]
merge_langs = ['CHS', 'CHT', 'DE', 'EN', 'ES', 'FR', 'ID', 'IT', 'JP', 'KR', 'PT', 'RU', 'TH', 'TR', 'VI']

textmap_dir = Path(CONFIG_FILE['RepoPath']) / 'TextMap'
for lang in merge_langs:
    merge_jsons(textmap_sources(textmap_dir, lang), textmap_dir / f'TextMap{lang}.json')

for lang in repl_langs:
    replace_text(textmap_dir / f'TextMap{lang}.json')
