import re
import json

with open('scriptconfig.json', 'r', encoding = 'utf-8') as file:
    CONFIG_FILE = json.load(file)
    

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
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        
        
def merge_jsons(file1, file2, output_file):
    with open(file1, 'r', encoding = 'utf-8') as file:
        content1 = json.load(file)
        
    with open(file2, 'r', encoding = 'utf-8') as file:
        content2 = json.load(file)
        
    merged_content = content1
    merged_content.update(content2)
    
    with open(output_file, 'w', encoding = 'utf-8') as file:
        json.dump(merged_content, file, ensure_ascii = False, indent=2)
        

repl_langs = ["CHS", "CHT", "ZHS", "ZHT", "DE", "EN", "ES", "FR", "ID", "JA", "JP", "KO", "KR", "PT", "RU", "TH", "VI", "TR", "IT"]
repl_langs = ["EN"]
merge_langs = {
    "TH": ["TH_0", "TH_1"],
}

for lang, files in merge_langs.items():
    merge_jsons(f'{CONFIG_FILE["RepoPath"]}/TextMap/TextMap{files[0]}.json', f'{CONFIG_FILE["RepoPath"]}/TextMap/TextMap{files[1]}.json', f'{CONFIG_FILE["RepoPath"]}/TextMap/TextMap{lang}.json')

for n in range(0, len(repl_langs)):
    replace_text(f"{CONFIG_FILE['RepoPath']}\TextMap\TextMap" + repl_langs[n] + ".json")
