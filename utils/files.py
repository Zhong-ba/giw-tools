import json
import os
import shutil
import toolLog as report

# Generated media can carry the text of its wiki File page in a hidden manifest beside it,
# which the bot uses as the description page when uploading.
FILE_PAGES = '.filepages.json'


def write_file(filename, content, overwrite = False):
    new_filename = filename

    if not overwrite:
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(new_filename):
            counter += 1
            new_filename = f"{base}_{counter}{ext}"

    with open(new_filename, 'w', encoding = 'utf-8') as file:
        file.write(content)
        
    report.debug('Saved %s', new_filename)


def _file_pages(directory):
    try:
        with open(os.path.join(directory, FILE_PAGES), 'r', encoding = 'utf-8') as file:
            pages = json.load(file)
    except (OSError, ValueError):
        return {}
    return pages if isinstance(pages, dict) else {}


def write_file_pages(directory, pages):
    '''Designates File page text for media in directory: {file name: wikitext}, merged into the manifest.'''
    merged = {**_file_pages(directory), **pages}
    with open(os.path.join(directory, FILE_PAGES), 'w', encoding = 'utf-8') as file:
        json.dump(merged, file, indent = 2, ensure_ascii = False)


def read_file_page(path):
    '''The File page text designated for a media file, or None.'''
    text = _file_pages(os.path.dirname(os.fspath(path))).get(os.path.basename(os.fspath(path)))
    return text if isinstance(text, str) else None
        

def copy_file(source_path, destination_path):
    if os.path.exists(source_path):
        dest_dir = destination_path.replace(destination_path.split('/')[-1], '')
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        shutil.copy(source_path, destination_path)
        report.debug('Copied %s to %s', source_path, destination_path)
    else:
        report.warning(f'Cannot copy missing file: {source_path}')