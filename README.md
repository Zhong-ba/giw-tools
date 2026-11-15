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
run `python setupData.py` directly. With downloaded sources,
`python setupData.py --keep-versions N` also prepares the newest builds of the
`N - 1` previous game versions and deletes every other downloaded dataset to save
disk space (see "Deploying (hosted mode)").

### Downloaded data sources
Instead of a manually downloaded current dataset, setup can download and prepare
data from two public repositories. Set `"DataSource": "remote"` (the older value
`"github"` means the same) and choose a source for each kind of data:

```json
{
    "DataSource": "remote",
    "ExcelSource": "dimbreath",
    "BinOutputSource": "gura"
}
```

| Setting | Default | Provides |
| --- | --- | --- |
| `ExcelSource` | `dimbreath` | `ExcelBinOutput` and the `TextMap`s used to resolve its text |
| `BinOutputSource` | `gura` | `BinOutput/Monster` (enemy weight and endure type) and the character files shown by the web UI's **Game Data** panel |

Values: `dimbreath` = [DimbreathBot/AnimeGameData](https://github.com/DimbreathBot/AnimeGameData),
`gura` = [GuraFoundation/YuanShenResources](https://gitlab.com/GuraFoundation/YuanShenResources).
TextMaps always come from the Excel source, because Excel text hashes must
resolve against the same build. Run `.\quickSetup.bat` after changing either
setting; the web UI's Dataset page can also change them.

Each source follows the latest `main` revision by default. To pin an older
build, set `ExcelRevision` and/or `BinOutputRevision` to a full commit hash
(`"latest"` restores the default). `python setupData.py --list-revisions dimbreath`
(or `gura`) lists recent revisions, and the Dataset page offers them in a
dropdown. Tools refuse to run until setup has prepared the pinned revision;
switching back to an already-prepared revision is instant.

How the sources differ (and how the tools handle it):
- **Builds:** DimbreathBot publishes release builds (`CNREL`); GuraFoundation
  publishes beta builds (`CNCB`/`OSCB`), so it can contain unreleased content and
  is missing some tables DimbreathBot has (about 300 of 2,279, including
  `QuestExcelConfigData` and `DialogExcelConfigData`). MiscTools' quest output
  needs DimbreathBot Excel data; everything else works with either.
- **BinOutput:** DimbreathBot names most monster configs by hash
  (`10018765187514261229.json`) but keeps their contents readable;
  GuraFoundation uses readable file names (`Aahigaru_Male_01_25050301.json`),
  has about 3.5x as many files, and scrambles every key inside them. The enemy
  tool finds configs by monster ID, readable name, or hash, and reads scrambled
  configs by locating the block that holds the endure type (`Monster_*`).
- **Readable names for scrambled BinOutput:** no GuraFoundation revision has
  readable keys, and the scrambled names change between builds. When setup
  detects a scrambled BinOutput it also downloads DimbreathBot's readable copy
  of the same files, walks both copies in parallel, and pairs fields whose values
  match (identical names, unique values, then the closest-matching nested
  objects). Names that most file pairs agree on are written back into the
  GuraFoundation snapshot, including `$type` class names; the learned map is
  saved as `.keys.json` in the snapshot. About 85% of character ability keys,
  60% of character config keys, and 40% of all keys become readable (setup
  prints the share). The rest are fields DimbreathBot's files do not contain
  (GuraFoundation also writes default values), so they keep their scrambled
  names. A learned name never replaces a field that already exists.
- **TextMaps:** files are split differently (RU and TH parts, Medium maps).
  `textmapcleanup.py` merges whatever parts a language has.
- **Field names:** builds scramble different fields, and some readable names
  differ (`specialProudSkillOpens`, `ID`, snake_case voice fields, text fields
  without the `TextMapHash` suffix). The mapper renames known variants using
  [leo/dataSchema.json](leo/dataSchema.json). GuraFoundation also stores
  single-precision floats unrounded (`0.05000000074505806`) and large hashes as
  strings; the mapper rounds such floats to their intended value.
- Setup warns when a field the tools need is missing from the prepared build and
  reports how many monster configs expose weight and endure type. Scrambled
  names change with game versions; add the new name to `leo/dataSchema.json`
  when that happens.
- Newer Spiral Abyss chambers reference a monster preview instead of listing
  their monsters, and neither source's Excel data contains those lineups;
  MiscTools' `spiralabyss` output marks such halves instead of failing.

Other notes:
- Git must be installed. Setup downloads the latest `main` revision of each
  selected source with shallow, filtered Git history and checks out only
  `ExcelBinOutput` and `TextMap` (Excel source) and, from the BinOutput source,
  `BinOutput/Monster` plus the character files `Avatar/ConfigAvatar_*`,
  `Ability/Temp/AvatarAbilities`, `Ability/Temp/AvatarAniEventAbilities`,
  `Gadget/ConfigGadget_SkillObj_*`, and `Talent/AvatarTalents`.
- Downloads and prepared snapshots are cached under `.data/AnimeGameData` and
  `.data/YuanShenResources` beside the configuration file. Allow several GB per
  Excel source; the TextMaps alone exceed 1 GB.
- Python tools and the active Node tools automatically use the prepared cache.
  `RepoPath` is ignored in remote mode. No network request happens when a tool
  loads its configuration.
- Rerun quick setup to check for upstream changes. Unchanged, successfully
  prepared revisions are reused. New revisions are activated only after the full
  pipeline succeeds; a failed update leaves the last prepared revisions selected.
  Older cached revisions are retained, so disk usage grows with updates.
- `RepoPathOld` remains your existing local, already-prepared previous dataset.
  Images and talent backgrounds still come from `ImgPath` and `TalentBGPath`;
  neither repository provides extracted textures.
- Omit `DataSource` or set it to `"local"` to retain local-data mode. In local
  mode an optional `BinPath` points the enemy tool at a separate `BinOutput`
  directory; otherwise it uses `RepoPath/BinOutput`.

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
The first web version includes **Other Languages**, **Character Kit**,
**Attribute Scaling**, **Character Data**, **Enemy**, **Fishing Point**, **Fish Weights**, **Manual Cooking Data**, **Bounties** and **Redirect Builder**, plus dataset setup/update controls, persistent background
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
  under `jobs` in the working directory (default `.data/webui` beside the profile;
  change it under **Working Directory** on the Dataset page). Your configured `OutputPath` is not
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
  Character Kit uses the original generator.
  Icon generation (and the icon background element) is hidden in the web UI
  while `IMAGE_ASSETS = False` in `webui/tools.py`, until an updated texture
  extraction is available; set it to `True` to restore it. It needs your
  configured local textures/backgrounds. The CLI's `--files True` is unaffected.
  It also fills the Normal Attack, Elemental Skill, and Elemental Burst pages'
  Attribute Scaling sections with the Attribute Scaling tool's tables (same max
  levels, default 11/13/13; needs Node.js). On the command line use
  `python parseCharKit.py ... --levels 11 13 13`, or `--noscaling True` to leave
  the sections empty. If scaling can't be generated (e.g. Traveler or no Node.js),
  the kit is still written with empty sections and the reason is logged.
- Character Kit's release version is looked up in the character's wiki article
  (first parameter of `{{Change History|...}}` in its Change History section,
  `wikiVersion.py`). The web UI fills the empty version field when a character is
  picked; the CLI does so when `--ver` is omitted and stops if none is found.
  Web job outputs list kit pages as NA, E, Q, A1, A4, special passive
  (NRG/MB/WER/SP), UP, C1-C6.
- The special passive type is detected from the passive names (`passiveTypes.py`):
  Night Realm's Gift → Nightsoul, Moonsign Benediction → Moonsign, Witch's Eve Rite
  → Hexerei, and Stellar Jubilee or any other quest-unlocked passive (e.g. Cyno's) →
  Stellar. Picking a character in the web UI ticks the matching box and opens
  Advanced Options; the CLI detects it when no `--natlan/--nodkrai/--hexerei/--stellar`
  is given (`--nodetect True` turns this off).
- Normal Attack/Skill/Burst pages list the A1/A4 passives and constellations that
  affect them under Passive/Constellation Effects (`talentEffects.py`). A talent is
  listed when its description links or names the skill, or uses a term only that
  skill's description links or bolds. It is also listed when its talent config raises
  the skill's level, changes its CD/charges, or modifies an ability only that skill
  upgrades. Against the wiki's existing notes this is about 92% precise and catches
  about 89% of them, so review the lists. Note text such as "Using X will apply Y"
  is not generated.
- Character Kit also fills those pages' Advanced Properties sections from the
  attack data (`advancedProperties.py`): GU, ICD tag/type, poise, impulse, and
  blunt for each attack, titled after its Attribute Scaling row (multi-hit rows
  become `3-Hit A`/`B` or `1-Hit`/`2-Hit`). Bows get the wiki's aimed-shot weak
  spot and plunge rows. Rows sharing an ICD tag and type are listed together so
  the template merges their cells, and irregular ICD sequences are written as
  `10s: <small>1st, 4th, 7th Hits Apply Element</small>`. Review the output: titles may need qualifiers such as
  "(Press)", and attacks the wiki doesn't list should be removed.
- Passive and constellation pages get an Advanced Properties section when the
  talent adds an attack: an ability it adds, a hit gated behind its talent
  param, a gadget it spawns, or a hit scaled by a special it sets. Hits that
  only reuse a Normal Attack/Skill/Burst scaling row stay on those pages, and a
  hit needing several talents goes to the one unlocked last. Rows are titled
  after the scaling row they reuse (with a Lunar-Bloom/Lunar-Charged/... suffix
  for reaction hits) or else the talent's name, so rename them. Use
  `--noap True` (or untick **Include Advanced Properties**) to leave all these
  sections empty. The Traveler needs a skill depot override. A Normal
  Attack/Skill/Burst with no attacks (e.g. Itto's Burst) gets no Advanced
  Properties section; with `--noap` or when generation fails, the sections stay empty.
- Talent infoboxes get `scale_att1`/`scale_att2` from the Attribute Scaling rows'
  stats (`(%Max HP)` titles, `4.4% Max HP + 424` values; plain `(%)` is ATK), most
  used first; this matches about 89% of existing wiki pages exactly. Only Fontaine
  characters get `arkhe`, filled from "Pneuma-aligned"/"Ousia-aligned" descriptions.
- Talent and Constellation infoboxes get `utilityN` from description wording
  (`talentUtilities.py`), after constellation Level Increase entries. Rules cover
  stats and buffs (CRIT, ATK/EM/DEF and their Party variants, ATK/Movement SPD,
  DMG Bonus, Additive Base DMG Bonus, attack-type DMG Increases, Elemental DMG Bonus),
  Healing, Shield, Energy, Interruption Resistance, Cooldown Reduction/Reset,
  DEF/RES Reduction, Taunting, Nightsoul mechanics, and gathering/expedition passives.
  Each rule is kept only if its matches mostly agree with the live wiki: about 83%
  of filled utilities match, covering about a third of existing entries. Utilities
  the text doesn't state (AoE, Status to Self, Effects Retained Character Fallen on
  skills) stay manual.
- Attribute Scaling runs `leo/MiscTools.js abilities -wt` and requires Node.js.
  Max levels are set separately for Normal Attack, Elemental Skill, and Elemental
  Burst (default 11/13/13); an alternate sprint table (e.g. Ayaka, Mona) uses the
  Elemental Skill level.
  Characters with selectable elements (Traveler) are not supported.
  The web version writes one numbered file per talent (template only); the CLI
  keeps a single file and the `-l` option. Both append the scaling to damage
  titles: `(%)` for ATK, `(%Max HP)`, `(%DEF)`, or `(%EM)`, e.g.
  `Photo DMG (Hold) (%)`, and drop the stat name from that column's values.
  Columns of any title that scale purely on one stat are labelled the same way
  (`ATK Bonus (%DEF)`, also `(%ATK)` and `(%Current HP)`). Mixed and flat-bonus
  columns keep their stats with a percent sign, as in game (`0.8% Max HP + 77`).
  Other scalings, and titles like "DMG Bonus" or "DMG Absorption", are left
  unchanged. `+`, `×`, and `*` in values are spaced (`20 × 2`).
- Character Data writes `Module:Character Ascensions and Stats/data` and
  `Module:Talent Upgrade/data` (`Character_Ascensions_and_Stats_data.lua` and
  `Talent_Upgrade_data.lua`, both postable from the Bot page) for every playable
  character, sorted alphabetically. Trial, template and cost-free avatars are
  skipped. The Traveler has one ascension entry and one talent entry per region
  (from each element's Elemental Skill). `bossCost` is only written when a
  character's weekly boss costs aren't the usual 1/1/2/2, and `base_em` only for
  characters with base Elemental Mastery.
  CLI: `python parseMisc.py --chardata True`.
- Enemy lists every named monster (searchable by name, ID or internal name) for
  multi-selection. **Compare Versions** (on by default) lists only monsters added
  between an older and a newer version, and selects them all. The defaults are
  the active dataset and the newest revision of the previous game version (e.g.
  7.1 while 7.2 is active), and the version field is filled from the newer one.
  Other choices are the newest revision of each recent game version, or
  `RepoPathOld`. Only each build's `MonsterExcelConfigData.json` is downloaded
  (cached in `.data/AnimeGameData`). Names are resolved via the active describe
  table, so the list only offers monsters that exist in the active dataset.
  Local-data mode can only compare the active dataset with `RepoPathOld`.
  **Only New Enemy Names** (default) hides variants of existing enemies (e.g. a
  new Hydro Samachurl ID) and repeat IDs of a new enemy. Selected IDs sharing a
  name get one page (the first ID's), but every selected ID gets a row in
  `Enemy Stats.wikitext`. That file has no page title, so set one before posting
  it from the Bot page. Icons and file redirects are skipped while image assets
  are disabled. CLI: `python parseMisc.py --enemies 25134601,20090101 --ver 7.2`,
  or the version comparison with
  `python parseMisc.py --newenemies True --ver 7.2 --oldrev previous --newnamesonly True`
  (`--oldrev` also accepts a full commit hash; omit both for the old behaviour).
- Enemy, Fishing Point and Bounties share the same picker: search, multi-select,
  and **Compare Versions** to list only rows added between two builds (IDs only,
  so any revision works). The versions offered are those of each tool's table.
- Bounties writes the Player's Choice `{{Bounty}}` entries (all preselected) to
  `Bounties.wikitext`, grouped under `==Region==` headings like `Bounty/List`.
  Strengths, weaknesses and the news text come from
  `HuntingV2MonsterBundleExcelConfigData`; `%` is wrapped in `<nowiki>`. The file
  has no page title, so merge it into `Bounty/List` rather than posting it as is.
  CLI: `python parseMisc.py --huntingv2 True` (or comma-separated bounty IDs)
  writes `Bounties_V2_Output.wikitext`.
- Fishing Point writes one `Fishing Point/<name>` page per pool (only pools
  assigned to a region; test, placeholder and event pools are skipped). Points
  sharing a name are numbered " (1)", " (2)"... in ID order. Day and night list
  the fish of the DAY/NIGHT stocks plus ANY stocks, regular fish before
  `Ornamental` variants; `display limit` is the pool's maximum and `total` the
  summed stock limits. Subarea and area come from `WorldAreaConfigData`. Compare
  Versions is on by default. CLI: `python parseMisc.py --fishingpoints new`
  (against `RepoPathOld`, or `--oldrev previous`/a commit), `all`, or
  comma-separated pool IDs; pages go to `Fishing Points/` in the output folder.
- Fish Weights writes `Module:Fishing Point Fish List/data`
  (`Fishing_Point_Fish_List_data.lua`, postable from the Bot page): the spawn
  weight of every fish in the stocks of real fishing points (event and quest
  stocks are ignored; a fish weighted differently between points takes its most
  common weight), regular fish before `Ornamental` variants in fish ID order.
  CLI: `python parseMisc.py --fishweights True`.
- Manual Cooking Data writes `Module:Manual Cooking/data`
  (`Manual_Cooking_data.lua`, postable from the Bot page). **Dial images** can
  also draw the `Manual Cooking C-<center> W-<width>.png` images the module
  links to: only those missing from the English wiki, or every combination a
  recipe uses (in `Cooking_QTE/`), each designated a File page in the Manual
  Cooking Images category with `{{Fairuse}}` licensing for bot uploads. CLI:
  `--cookingqte True` for the module,
  `--cookingqte2 True` for every image or `--cookingqte2 missing`.
- Dataset setup invokes the existing setup pipeline. Local-data mode modifies
  that dataset in place; GitHub mode activates a successfully prepared revision.
- Outputs/history are retained until you delete a job (trash icon in the job list
  or **Delete** in the job window; queued/running jobs cannot be deleted).
  Generated `.wikitext` files can be edited in the output window (pencil icon,
  Ctrl+S to save); edits overwrite that job's file and keep its line endings.
  Wikitext is shown as syntax-highlighted source, not rendered as HTML or
  expanded MediaWiki templates.
- Completed Character Kit jobs have a **Game Data** button that opens the
  character's game files beside the output (also while editing): `ConfigAvatar`,
  its `ConfigAbility` and AniEvent ability files, `ConfigGadget_SkillObj` files,
  and its `AttackAttenuationExcelConfigData` rows (groups named after the
  character's internal name, e.g. `Ambor` for Amber). Files come from the current
  BinOutput/Excel sources, not a snapshot taken when the job ran. Filter pills
  narrow a file to its **Attack Info** blocks or its **GenerateElemBall**
  actions (ability files), each labelled with its ability name and JSON path.
  The Attack Info view has a table of contents by ability name (gadget and
  avatar files use the animation event name instead), keys inside `attackInfo`
  are sorted alphabetically, and lines with `attackTag`, `hitImpulseType`,
  `elementDurability`, `enBreak`, `attenuationTag` or `attenuationGroup` are
  highlighted. **Ctrl+F** searches the open file instead of the page.

### Bot page (posting to the wiki)
- In a job's output window, tick `.wikitext`/`.lua` files and click **Add**, or
  click **All**, to add them to the bot queue. The target page comes from the
  file's `[PAGE_INFO]` header (which is stripped from the posted text). Files
  without one are queued untitled and must be given a title on the **Bot** page
  before they can be posted. Files marked `skip` are queued as Skipped. Queued
  text is a snapshot, so later job edits or deletions do not affect it.
- Images (`.png`, `.jpg`, `.webp`, `.gif`) can be queued the same way and are
  uploaded as `File:<name>`. Their queued text is the File page content, taken
  from the hidden `.filepages.json` manifest the tool wrote beside the image
  (`utils.files.write_file_pages(directory, {file name: wikitext})`), or empty
  if none was designated; the image itself is copied into
  `bot/media/` in the working directory. MediaWiki only uses the text for new files:
  re-uploading an existing file adds a new version and leaves its page as is.
  Skip Existing Pages skips existing files and Skip Unchanged Pages skips files
  whose SHA-1 matches the live version. Uploading needs the "Upload new files"
  and "Upload, replace, and move files" bot password grants.
- On the Bot page, edit titles inline or click a row to edit its title and text.
  **Post Queue** posts every pending/failed item that has a title, or you can post
  selected rows. Posted items stay in the queue marked Posted (**Clear Posted**
  removes them); **Reset** returns items to Pending.
- Settings: the wiki URL (default `https://genshin-impact.fandom.com`; any
  MediaWiki page or `api.php` URL works), a bot password from
  `Special:BotPasswords`, the edit summary, and the options Skip Existing Pages,
  Skip Unchanged Pages, Mark as Bot Edits, Watch Posted Pages and Protect Posted
  Pages (edit/move = sysop, plus upload = sysop for files). The password is kept in memory only, unless
  **Remember Login** is ticked, in which case it is saved in plain text in
  `bot/settings.json` in the working directory. The queue is stored in `bot/queue.json`
  and queued images in `bot/media/`.
- Posting uses the MediaWiki Action API directly (no pywikibot) and is web-only.

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

### Deploying (hosted mode)
A public site is split in two: a static frontend (e.g. on Vercel) and one shared
Python backend that only runs tools. There are no site accounts and no server-side
secrets. Everything personal stays with each visitor:

- **Jobs:** the backend keeps a finished job only until the browser downloads it
  (at most 24 hours), then deletes it. The browser saves it in the folder chosen
  under **Working Directory** (Chrome/Edge, via the File System Access API) or
  otherwise in the browser's own storage. Each browser can have at most three
  pending/running jobs, and only sees its own.
- **Bot:** the queue, settings and bot password live in the browser (the password
  in `localStorage`, only when **Remember Login** is ticked). Each visitor logs in
  with their own bot password; the backend only relays MediaWiki API calls for the
  session and refuses non-public wiki addresses.
- **Dataset:** the server keeps only the current and previous game versions, and
  visitors pick between them. They cannot run setup, change sources, or change
  server settings. For any other revision, run Painmelo locally (see above): local
  mode can download and prepare any revision. A browser whose picked revision has
  since been removed falls back to the default and says so.

Backend (any Docker host with a persistent volume of about 15 GB, and about 8 GB of RAM for the TextMaps):
```bash
docker build -t painmelo .
docker run -d -p 8000:8000 -v painmelo-data:/data \
  -e PAINMELO_CORS_ORIGINS=https://your-site.vercel.app painmelo
docker exec <container> python setupData.py --keep-versions 2   # prepare (and later update) the dataset
```
The first start writes a remote-data profile to `/data/scriptconfig.json`; edit it
to choose sources, then rerun setup. `--keep-versions 2` prepares the latest build
plus the newest build of the previous game version (found from DimbreathBot's
`CNRELWin<major>.<minor>` commit titles), then deletes every other downloaded
dataset, including copies left by older preprocessing. Only the latest BinOutput
(and the readable copy it was deobfuscated with) is kept. Run the same command
after each game update; the oldest version drops off automatically. This needs
about 7 GB, plus about 0.5 GB of git cache per new version; deleting
`.data/<source>/repository.git` resets that cache (setup downloads it again).
Without Docker, run `python -m webui --hosted --host 0.0.0.0` behind an HTTPS
reverse proxy.

| Variable | Meaning |
| --- | --- |
| `PAINMELO_HOSTED` | `1` enables hosted mode (same as `--hosted`). |
| `PAINMELO_CORS_ORIGINS` | Comma-separated frontend origins allowed to call the API. |
| `PAINMELO_ALLOWED_HOSTS` | Comma-separated host names the backend answers to (default: any in hosted mode). |
| `PAINMELO_JOBS_DIR` | Temporary job store (default `.data/hosted-jobs` beside the profile). |
| `PORT` | Listening port (default 8000). |
| `GENSHIN_TOOLS_CONFIG` | Profile path. |

Frontend: import the repository in Vercel with **Root Directory** `frontend`
(settings come from `frontend/vercel.json`) and set the environment variable
`VITE_API_URL` to the backend URL, e.g. `https://api.example.com`. Without it the
frontend calls `/api` on its own origin, as in local mode.

Local mode (`python -m webui`, the default) is unchanged: loopback only, with
same-origin checks, server-side jobs and bot queue in the working directory, and
dataset setup available.