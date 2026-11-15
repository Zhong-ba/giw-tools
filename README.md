# Genshin Wiki Tools
Utilities for generating updates for the [Genshin Impact Wiki](https://genshin-impact.fandom.com) from game data.

## Setup
### 1. Install Requirements
```bash
pip install -r requirements.txt
```
### 2. Create scriptconfig.json
Create a ``scriptconfig.json`` file in the root directory with the following:
```json
{
    "DataSource": "local",
    "RepoPath": "<path to the current version GenshinData>",
    "RepoPathOld": "<path to the previous version GenshinData>",
    "ImgPath": "<path to extracted Texture2D images>",
    "TalentBGPath": "<path to talent backgrounds>",
    "OutputPath": "<output location>"
}
```

### 3. Prepare the data
Install Node.js and the mapper dependencies (`npm --prefix leo ci`), then run:
```powershell
.\quickSetup.bat
```
This merges the TextMaps, cleans English text, and maps the Excel tables. Setup
stops on errors instead of continuing with partially processed data. You can also
run `python setupData.py` directly.

### GitHub data source
To use [DimbreathBot/AnimeGameData](https://github.com/DimbreathBot/AnimeGameData)
instead of a manually downloaded current dataset, set `"DataSource": "github"`
in `scriptconfig.json`, then run `.\quickSetup.bat`.

- Git must be installed. Setup downloads the latest `main` revision with shallow,
  filtered Git history and checks out only `ExcelBinOutput`, `TextMap`, and
  `BinOutput/Monster`, which cover the current tools' data requirements.
- Downloads, mapped tables, and merged TextMaps are cached under
  `.data/AnimeGameData` beside the configuration file. Allow several GB of disk
  space; the upstream TextMaps alone currently exceed 1 GB.
- Python tools and the active Node tools automatically use the prepared cache.
  `RepoPath` is ignored in GitHub mode. No network request happens when a tool
  loads its configuration.
- Rerun quick setup to check for upstream changes. An unchanged, successfully
  prepared revision is reused. A new revision is activated only after the full
  pipeline succeeds; a failed update leaves the last prepared revision selected.
  Older cached revisions are retained, so disk usage grows with updates.
- `RepoPathOld` remains your existing local, already-prepared previous dataset.
  Images and talent backgrounds still come from `ImgPath` and `TalentBGPath`;
  this repository does not provide extracted textures.
- Omit `DataSource` or set it to `"local"` to retain local-data mode.

All tools default to `scriptconfig.json` beside the Python entry points, not a
machine-specific absolute path. Set `GENSHIN_TOOLS_CONFIG` to an alternate config
file to select another profile for both Python and Node. Setup also accepts
`python setupData.py --config "<path to config>"`; use the environment variable
when running tools against that alternate profile afterward.

## Validation
Run the core Python regression tests from this directory after installing the requirements:
```bash
python -m unittest discover -s tests -p test_tools.py -v
```
The tests use temporary configuration, game data, and output directories; they do not
modify your configured game data or generated output. Enemy-tool tests also require
the tool's existing `Levenshtein` dependency to be installed.

## Web interface
The first web version includes **Other Languages**, **Character Kit**, and
**Redirect Builder**, plus dataset setup/update controls, persistent background
jobs, live logs, text/image previews, individual downloads, and ZIP exports.
Existing command-line tools remain available.

### Install and start
Complete the configuration and Node.js mapper dependency steps in Setup above.
Then, from this directory, install the optional web dependencies and build the frontend:
```powershell
python -m pip install -r requirements-web.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
python -m webui
```
Open <http://127.0.0.1:8000>. On Windows, `.\startWebUI.bat` also starts the app
after installation/build. Use `python -m webui --port 8001` for another port.
The existing `GENSHIN_TOOLS_CONFIG` environment variable selects the profile.

- Tool jobs run in one long-lived worker process, each with its own output folder
  under `.data/webui/jobs` beside the profile. Your configured `OutputPath` is not
  modified. Inputs and the resolved dataset are snapshotted for each tool job, and
  config-dependent modules are re-imported for every job.
- The TextMaps used by Other Languages (also used by Character Kit) are loaded the
  first time a tool needs them and then kept in memory until the server stops
  (about 3.5 GB). They reload automatically when a new dataset revision is active.
  Dataset setup runs in its own process and releases the loaded TextMaps first.
- One worker runs jobs sequentially to bound memory use and avoid overlapping
  dataset updates. The queue accepts at most ten pending/running jobs.
- Job history and outputs survive restarts. Interrupted jobs are marked failed;
  they are not silently retried. Shutdown waits for queued/running jobs to finish.
  Logs show real tool progress; no estimated percentage is fabricated.
- Other Languages uses exact TextMap matches and the original formatter.
  Character Kit uses the original generator;
  optional icons still require your configured local textures/backgrounds.
- Dataset setup invokes the existing setup pipeline. Local-data mode modifies
  that dataset in place; GitHub mode activates a successfully prepared revision.
- Outputs/history are retained until you remove their job directories while the
  server is stopped. Generated wikitext is shown as source, not rendered as HTML
  or expanded MediaWiki templates.

### Development and adding tools
For frontend development, run the API with `python -m webui` and, in another
terminal, `npm.cmd --prefix frontend run dev`. Open the Vite URL it prints; API
requests are proxied to port 8000. Rebuild for the Python-served production UI.

Add a Pydantic input model and a runner to `webui/tools.py`, then register a
`Tool` in `TOOLS`. The API publishes its schema and the UI builds a form from
it automatically. Runners execute only in the worker process, and modules from this
repository (except `OLGen`) are re-imported for each job, so legacy globals and CLI
argument parsing do not leak between jobs. Add specialized frontend
controls only when a schema-generated field is insufficient.

Validation:
```powershell
python -m unittest discover -s tests -v
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run lint
```

### Hosting boundary
This release is **local-only**, bound to loopback with local-host and same-origin
request checks. Run one backend process per job directory. The frontend/API split
can support hosting later, but do not expose this version through a public proxy:
it has no user authentication, tenant isolation, quotas, or dataset-upload policy.
Those are required additions before public deployment.