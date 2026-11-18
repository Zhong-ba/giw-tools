import argparse
from contextlib import redirect_stderr, redirect_stdout
import gc
import importlib
import json
import os
from pathlib import Path
import sys
from types import ModuleType

from dataSource import ROOT, data_root
import toolLog as report

# Modules that survive between jobs in the resident worker. Everything else imported from
# this repository is re-imported per job, because legacy modules read the config at import.
PERSISTENT = {'OLGen', 'dataSource', 'toolLog'}


def setup(directory: Path) -> None:
    with (directory / 'request.json').open(encoding='utf-8') as file:
        request = json.load(file)
    from setupData import prepare
    report.stage('Preparing dataset')
    dataset = prepare(Path(request['config_path']))
    (directory / 'output' / 'dataset.json').write_text(
        json.dumps({'dataset': str(dataset), 'status': 'ready'}, indent=2), encoding='utf-8',
    )


def _purge_job_modules() -> None:
    root = ROOT.resolve()
    for name, module in list(sys.modules.items()):
        if name in PERSISTENT or name == 'webui' or name.startswith('webui.'):
            continue
        path = getattr(module, '__file__', None)
        if path and Path(path).resolve().is_relative_to(root):
            del sys.modules[name]


def _shared_textmaps(dataset: str, cache: Path) -> ModuleType:
    """Keep legacy generators on the same persistent index as direct OL lookups."""
    from webui.languages import IndexedTextMap, ensure_index

    module = sys.modules.get('OLGen')
    if module is not None and getattr(module, 'webui_dataset', None) == (dataset, cache):
        return module
    sys.modules.pop('OLGen', None)
    gc.collect()
    module = importlib.import_module('OLGen')

    def load_index(progress_callback=None):
        report.stage('Opening persistent Other Languages index (building it if needed)')
        path = ensure_index(Path(dataset) / 'TextMap', cache)
        module.data = {language: IndexedTextMap(path, language) for language in module.LANGS}
        if progress_callback:
            progress_callback(len(module.LANGS), len(module.LANGS))
        report.info('Using persistent Other Languages index.')

    def find_text_id(text, input_lang='EN'):
        return module.data[input_lang].find_id(text)

    module.load_data = load_index
    module.find_text_id = find_text_id
    module.webui_dataset = (dataset, cache)
    return module


def run_tool(directory: Path) -> None:
    with (directory / 'request.json').open(encoding='utf-8') as file:
        request = json.load(file)
    config = directory / 'config.json'
    os.environ['GENSHIN_TOOLS_CONFIG'] = str(config)
    _purge_job_modules()
    tool = importlib.import_module('webui.tools').TOOLS[request['tool_id']]
    if tool.execute is None:
        raise ValueError(f'{tool.name} runs directly without creating a job.')
    if tool.requires_dataset:
        _shared_textmaps(json.loads(config.read_text(encoding='utf-8'))['RepoPath'],
                        data_root(Path(request['config_path'])) / 'ol')
    argv = sys.argv
    try:
        tool.execute(directory / 'output', request['parameters'])
    finally:
        sys.argv = argv


def serve(connection) -> None:
    """Resident worker loop: receives job directories, replies with an error message or None."""
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    while True:
        try:
            directory = connection.recv()
        except EOFError:
            return
        if directory is None:
            return
        error = None
        with open(Path(directory) / 'log.txt', 'a', encoding='utf-8', buffering=1) as log:
            metadata = json.loads((Path(directory) / 'job.json').read_text(encoding='utf-8'))
            report.configure(log, Path(directory) / 'progress.json', metadata['started_at'])
            stream = report.LogStream()
            with redirect_stdout(stream), redirect_stderr(stream):
                try:
                    run_tool(Path(directory))
                except SystemExit as exit_request:
                    if exit_request.code not in (None, 0):
                        error = f'The tool exited with code {exit_request.code}. Open the log for details.'
                        report.logger.exception(error)
                except Exception as failure:
                    error = f'{type(failure).__name__}: {failure}'
                    report.logger.exception(error)
                finally:
                    stream.flush()
        connection.send(error)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    directory = parser.parse_args().directory.resolve()
    metadata = json.loads((directory / 'job.json').read_text(encoding='utf-8'))
    report.configure(sys.stdout, directory / 'progress.json', metadata['started_at'])
    stream = report.LogStream()
    with redirect_stdout(stream), redirect_stderr(stream):
        try:
            setup(directory)
        except Exception:
            report.logger.exception('Dataset setup failed.')
            raise SystemExit(1)
        finally:
            stream.flush()
