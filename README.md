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
| `BinOutputSource` | `gura` | The complete `BinOutput` tree, used by generators and the **BinOutput Viewer** |

Values: `dimbreath` = [DimbreathBot/AnimeGameData](https://github.com/DimbreathBot/AnimeGameData),
`gura` = [GuraFoundation/YuanShenResources](https://gitlab.com/GuraFoundation/YuanShenResources).
TextMaps always come from the Excel source, because Excel text hashes must
resolve against the same build. Run `.\quickSetup.bat` after changing either
setting; the web UI's Dataset page can also change them.

Setup downloads the complete upstream BinOutput tree, including enemy abilities
and folders not used by the generators. This requires more disk space and
preparation time than the previous limited subset. Rerun setup for
existing datasets to prepare the expanded layout; the viewer can only show
files present in the selected dataset.

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

## Particle Generation
Inspect raw particle-generation evidence without generating pages:
```powershell
python particleGeneration.py --id 10000003 10000073 --output particles.json
```
This uses the configured, prepared dataset and the same character-file discovery
as Advanced Properties. Use `--skilldepot` for a selectable-element character.
The JSON lists generation events, conditional expected particle counts, random
chances, state predicates, modifier lifetimes, reverse modifier-call traces, and
talent configurations that add the ability.

Run a complete coverage audit from the CLI (the web tool is currently hidden
from the tool list):
```powershell
python particleGeneration.py --audit --output particle-audit.json
```
The audit includes every canonical `AVATAR_FORMAL` record and all its candidate
skill depots, without merging Traveler genders or excluding unreleased formal
characters for missing ascension costs. Trial/template variants and non-formal
records are listed separately as exclusions. Incomplete depots and extraction
errors remain explicit entries, not successful coverage.

The JSON contains dataset paths, summary counts, primary and overlapping blocker
counts, candidate event patterns, and each variant's raw evidence and output
status. Candidate patterns are research groupings, **not** automatic approval for
wiki output. The audit never fetches or edits wiki pages. CLI extraction errors
produce a nonzero exit code after the report is written; web jobs retain the
report and fail explicitly. `--output` writes UTF-8 directly, avoiding shell
redirection encoding differences. Omit it to print JSON instead.

Counts are **per event**, not per cast. Separately gated alternatives are not
added together; multiple contributing modifiers may need combining after review.
Modifier lifetimes are not automatically treated as effective particle cooldowns.
Unknown expressions/actions produce unresolved counts and warnings, not guessed
numbers. No detected generation does not establish zero generation. Ability
activation, talent overrides, spawn locations and shared-file coverage still need
validation. Raw extraction alone does not establish a publishable Skill note.

Character Kit's **Include Particle Generation** option (enabled by default) uses
`particlePages.py` to turn reviewed event patterns into Elemental Skill gameplay
notes and an additional **Energy/Data** update. Reviewed mappings cover Arataki
Itto, Bennett, Chongyun, Diluc, Diona, Gorou, Jean, Kaedehara Kazuha, Kamisato
Ayaka, Kaveh, Nahida, Navia, Neuvillette, Thoma, Tighnari and Venti.
Traveler's Hydro, Dendro and Cryo depots are also reviewed for both genders;
Anemo, Geo, Electro and Pyro still produce review reports without automatic
particle notes or Energy/Data replacements.
The mappings supply press/hold, hit-unit and spawn-point semantics, not particle
quantities: counts come from the selected dataset. Generation predicates, local
trigger chains, modifier gates, spawn configurations and the outcome distribution
must match the reviewed pattern. Additional or ambiguous events block automatic
output rather than being silently ignored.

Every enabled run writes `Particle Generation.json` in the character's output
folder with the raw evidence, output status and any review reason. Other
characters—including zero-generation cases—remain review-only until their
semantics have been reviewed. A decimal expectation is emitted only for an
integer guaranteed count plus at most one possible extra particle. Random
generation preserves shared and nested branch identities, so a choice
between four and five particles is correctly represented as 4.5, rather than
mistaken for two independent drops. Nonadjacent outcomes (e.g. zero or two,
despite their average of one) are rejected. Modifier
lifetimes are not generally promoted to effective cooldowns; Nahida's reviewed
7s gate is currently the only rendered particle cooldown.

Use `--noparticles` (or untick **Include Particle Generation**) to disable
particle notes, the report and Energy/Data generation. `--nodatapages True`
disables the Energy/Data update but keeps Skill notes and the report.
Particle output works independently of Advanced Properties. Energy/Data is
fetched live, retains its Traveler-first ordering, and preserves existing
character rows unless `--updateexisting` / **Update Existing Entries** is enabled.
Only changed page revisions are written. Uncertain cases never replace existing
wiki rows. When an Energy/Data update is requested,
an older generated `Energy Data.wikitext` in that character's output directory
is removed first, so skipped or failed updates cannot leave a stale posting file.

## Validation
Run the core Python regression tests from this directory after installing the requirements:
```bash
python -m unittest discover -s tests -p test_tools.py -v
```
The tests use temporary configuration, game data, and output directories; they do not
modify your configured game data or generated output. Enemy-tool tests also require
the tool's existing `Levenshtein` dependency to be installed.

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
- The TextMaps used by tool jobs (including Character Kit) are loaded the
  first time a tool needs them and then kept in memory until the server stops
  (about 3.5 GB). They reload automatically when a new dataset revision is active.
  Dataset setup runs in its own process and releases the loaded TextMaps first.
- One worker runs jobs sequentially to bound memory use and avoid overlapping
  dataset updates. The queue accepts at most ten pending/running jobs.
- Job history and outputs survive restarts. Interrupted jobs are marked failed;
  they are not silently retried. Shutdown waits for queued/running jobs to finish.
  Logs use elapsed timestamps and INFO/WARNING/ERROR levels, with stage messages
  and throttled batch counts. Tracebacks are retained on failure; verbose effect
  dictionaries, per-file save/copy confirmations, and expected Traveler depot skips
  are DEBUG-only. Missing optional files and setup field/readability issues are
  counted warnings. Uncaptured setup command output is streamed through the parent
  reporter; command failures keep their diagnostics and nonzero exit status.
  Shared generators use the same reporting in CLI runs. Intentional CLI payloads
  (JSON, wikitext, paths, and revision listings) remain plain stdout.
  Job status shows the current stage and real completed/total counts where known,
  without a progress bar or weighted overall estimate. Jobs are marked completed
  only after output files are validated. Warnings are counted without changing whether
  optional generation failures stop the tool.
  The Log tab colors warnings/errors and offers **Copy Log** and **Download Full Log**.
  Its preview is limited to the latest 128 KB; exports include the entire log.
  Newly collected hosted jobs retain the full log in browser storage, too.
- Other Languages opens a dedicated generator instead of creating a job. Look up
  an exact name (case insensitive) in the chosen language, or enter a TextMapHash.
  Each distinct set of localized names gets a collapsible result card with Copy,
  translation (`_tl`), romanization (`_rm`), and optional section-header checkboxes.
  Each result also has its own TL/RM checkboxes beside Copy; the top checkboxes apply to all results.
  Double-click empty space in a tool window to maximize it or restore its size.
  Repeated hashes with identical localized names are shown once. Results use the
  original formatter, shared with the desktop tool. A persistent SQLite index under
  `.data/ol` beside the profile makes new name/hash lookups fast without keeping
  another multi-GB copy of the TextMaps in RAM. Each dataset has its own index, reused
  across server restarts and rebuilt transactionally when its TextMaps change.
  Job-based tools (including Character Kit, Enemies, and Stygian Onslaught) use the
  same index instead of loading all TextMaps. Their existing exact-name matching
  and output formatting are unchanged; the desktop tools retain their original loader.
  The first lookup builds the index; to prepare the active dataset before serving
  users, run `python -m webui.languages` (in Docker: `docker exec <container> python -m webui.languages`).
  Allow extra disk space for the indexes and rebuilding them. The existing OL job
  API remains available for compatibility.
  Character Kit uses the original generator.
  Icon generation (and the icon background element) is hidden in the web UI
  while `IMAGE_ASSETS = False` in `webui/tools.py`, until an updated texture
  extraction is available; set it to `True` to restore it. It needs your
  configured local textures/backgrounds. The CLI's `--files True` is unaffected.
  It also fills the Normal Attack, Elemental Skill, and Elemental Burst pages'
  Attribute Scaling sections with the Attribute Scaling tool's tables (same max
  levels, default 11/13/13; needs Node.js). On the command line use
  `python parseCharKit.py ... --levels 11 13 13`, or `--noscaling True` to leave
  the sections empty. If scaling can't be generated (e.g. no Node.js),
  the kit is still written with empty sections and the reason is logged.
- Character Kit detects Aether (`10000005`) and Lumine (`10000007`) automatically.
  It discovers all complete elemental kits from their candidate skill depots,
  skips the incomplete elementless depot, and writes separate `Traveler (Anemo)`,
  `Traveler (Geo)`, etc. folders. All seven elements, including Cryo, are supported.
  Each folder has its own talents, passives, constellations and particle report.
  Wiki titles, character parameters and navboxes use `Traveler (Element)`;
  talent upgrades use that element's region (Geo Normal Attacks use both
  Mondstadt and Liyue). Normal Attack scaling uses `{{Past Memories}}`, and
  Advanced Properties include separately labelled Aether and Lumine sections.
  Cryo's additional Stellar passive is included.
  ```
  python parseCharKit.py --id 10000005
  python parseCharKit.py --id 10000007 --skilldepot 705
  python particleGeneration.py --id 10000005 10000007 --output traveler-particles.json
  ```
  Without a depot override, release versions are looked up separately on each
  elemental wiki article; the common version field/`--ver` is not used.
  With an override, `--ver` works normally. The legacy Traveler checkbox/flag
  is unnecessary. The same behavior applies in the web UI.
  Combat/Energy data-page changes from every element are accumulated into one
  posting file per wiki page under `Traveler/Data Pages`, not competing full-page
  copies in each element folder. Existing entries are still preserved by default.
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
  sections empty. Traveler depots are selected automatically by Character Kit;
  standalone Advanced Properties calls still need an explicit depot. A Normal
  Attack/Skill/Burst with no attacks (e.g. Itto's Burst) gets no Advanced
  Properties section; with `--noap` or when generation fails, the sections stay empty.
- From the same attack data, Character Kit also adds the character to the current
  revisions of Elemental Gauge Theory/Character Data, Internal Cooldown/Data,
  Area of Effect, Hitlag/Data and Targeting/Data (`combatPages.py`),
  written to `Data Pages/` in the character's output folder (only pages that change).
  Rows go in alphabetically in each table: per-element gauge rows (only hits whose
  attackInfo has an `elementType`, Normal Attack talents included; physical hits that
  infusions convert are covered by the page's note, and Normal Attack rows are always
  labelled), ICD rows per section (plus a new ICD Types row for the character's own ICD
  groups; rows of only reaction hits are labelled on both pages, e.g. "(Lunar-Charged)"), hitboxes of
  Skill/Burst/passive/constellation hits (not reaction hits), Normal/Charged Attack
  hitlag (never plunges) that differs from the "Most ... Characters" defaults, and the Skill/Burst
  targeting cylinder. Tables that already list the character are left untouched by
  default. Tick **Update Existing Entries** (CLI: `--updateexisting`) to replace the
  selected character's rows in the generated tables, without changing other characters.
  This can overwrite hand-written notes in those rows; review before posting.
  Charged Attack ICD rows matching the current table's weapon-default rules are
  omitted (including no-ICD catalyst/bow charged attacks); exceptions and
  Lunar/Stellar reaction entries remain.
  Each file is a whole page revision, so review the new rows (names, missing hitlag
  scale defaulting to 0.01) and post it before the page changes again. Use
  `--nodatapages True` (or untick **Update Combat Data Pages**) to skip it; it also
  needs Advanced Properties and network access to the wiki. With **Include
  Particle Generation** enabled, the same data-page option also generates the
  reviewed Energy/Data update described above; that page does not require
  Advanced Properties.
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
  The standalone Attribute Scaling UI does not select Traveler elements;
  use Character Kit for Traveler scaling. Python callers can pass
  `skill_depot=...` to `talent_scaling()`.
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
- **BinOutput Viewer** opens directly without creating a job. Its left-hand
  **Filter By** offers **None**, **Character**, **Enemy**, and **Gadget** radio
  buttons. Entity dropdowns are searchable by name or ID (and internal name/type
  where available); every match is available by scrolling, with large lists
  virtualized to keep the dropdown responsive. Dropdowns use the available
  screen/dialog height and resize with the viewport. Native middle-mouse
  autoscrolling (click or hold-and-drag) is available where supported by the browser.
  Use the arrow keys and Enter to select, or Escape to close the dropdown.
  None browses the complete tree and loads folders on demand; filtered trees
  start fully expanded. Single-subfolder chains appear as compact paths such
  as `Ability / Temp / AvatarAbilities` in either mode.
  Character/enemy/gadget filters find matching
  configs and follow explicit ability and gadget dependencies, including files
  whose names do not match the selected entity. Character discovery also uses
  talent/skill aliases; either Traveler includes shared and Aether/Lumine
  elemental ability files for all seven elements. **Discovery Notes** report
  missing tables, unreadable files, and unresolved ability definitions:
  relevance is a review aid, not a guarantee of exhaustive coverage. Enemy
  discovery recognizes readable names, `ConfigMonster_` names, and explicit
  monster IDs; hash-only filenames without those links may remain unresolved.
  Gadgets are selected by internal `JsonName` and ID, with their type shown.
  Gadget discovery indexes exact entries inside shared config files and follows
  only the selected entry's dependencies, while displaying the original complete
  files and jumping to the selected gadget's entry. The same lookup resolves
  gadgets linked from characters and enemies.
  Missing `JsonName` values, configs, or linked gadget IDs appear in Discovery
  Notes rather than being guessed.
- Completed Character Kit jobs keep their **Game Data** button, opening the
  same BinOutput Viewer beside the output (also while editing), initially
  filtered to the job's character. Relevant files include avatar/monster
  configs, ability and AniEvent files, linked gadgets, character talents,
  and matching `AttackAttenuationExcelConfigData` rows. Files come from the
  current BinOutput/Excel sources, not a snapshot taken when the job ran.
  Filter pills narrow a file to its **Attack Info** blocks or its
  **GenerateElemBall** actions, each labelled with its ability name and JSON path.
  The Attack Info view has a table of contents by ability name (gadget and
  avatar files use the animation event name instead), keys inside `attackInfo`
  are sorted alphabetically, and **Row Highlights** toggles individual rules
  for `attackTag`, `hitImpulseType`, `elementDurability`, `enBreak`,
  `attenuationTag`, `attenuationGroup`, and `strikeType: Blunt` (all on by
  default). **Ctrl+F** searches the open file instead of the page; copying
  includes the full file or currently filtered data. **Clean Decimals** is on
  by default: it removes float32 extraction noise (for example,
  `0.26600000262260437` becomes `0.266`) using the character tool's round-trip
  rule, while preserving integers and non-float32 values. It affects display,
  search, and copied data only; turn it off to inspect original numeric values.
  Large files remain
  virtualized, with a 16 MB per-file viewing limit.
- Text output files have the same search: the magnifier button above the
  preview (or **Ctrl+F** when the Game Data panel is closed) highlights matches,
  with Enter/Shift+Enter or the arrows to step through them.
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

### Previewing the public site locally
Before pushing, run `.\previewSite.bat` (options: `--port 8010`, `--nobuild`). It builds the
frontend and serves it from `python -m webui --hosted` at <http://127.0.0.1:8010>, so the page
behaves like the deployed site (jobs kept by the browser, the dataset picker, no setup or bot
server) while running your working copy's tools on this computer's prepared data. Python changes
need a restart of the preview; frontend changes need a rebuild (or run without `--nobuild`).
`.\startWebUI.bat` remains the full local workshop.

Pushing to `main` redeploys only the frontend (Vercel). Backend changes (anything outside
`frontend/`) reach the site after rebuilding the backend container. Changes to `setupData.py`, its
pipeline files or `BINOUTPUT_PATHS` also need the maintenance command below to re-prepare datasets.

### Spiral Abyss
**Spiral Abyss** (or `python parseMisc.py --abyss latest --ver 7.3`, or a start date instead of
`latest`) writes the `Spiral Abyss/Floors/<date>` page in the layout of the current rotation pages:
the `{{Abyssal Moon Spire}}` header (dates, neighbours and changed floors), Ley Line Disorder per
floor and half, and each changed floor's `{{Domain Enemies}}` levels, targets and enemies. Newer
chambers' enemies come from `BinOutput/MonsterPreview` (GuraFoundation names its files after the
chambers' previews; DimbreathBot's hashed names cannot be matched). The game data has no enemy
counts, waves or spawn notes, so the page is marked as a stub for editors to complete them.

### Imaginarium Theater
**Imaginarium Theater** (or `python parseMisc.py --theater latest --ver 7.1`, or a start date) writes the
`Imaginarium Theater/Seasons/<date>` page: the `{{Imaginarium Theater Season}}` header (season number,
dates, neighbours, opening characters, blessing, elements, Special Guest Stars and Climactic Showdown bosses
with levels), then each Act and Arcana Challenge with battle types, stage effects, boss/Arcana descriptions and
`{{Domain Enemies}}` objectives, Bonus/Star Challenges, levels per mode (e.g. `Easy Mode: 75<br>Hard/Visionary
Mode: 85`), advantages and enemies (powerful foes as `{ danger = 1 }`, from
`BinOutput/MonsterPreview/MonsterPreview_RoleCombatLevel.json`). Enemy counts, waves and the main objectives'
time limits and target counts are not in the client data; they are written as `?` and the page is marked as a
stub. The order of stages within a battle follows the data and may differ from the wiki.

### Stygian Onslaught
**Stygian Onslaught** (or `python parseMisc.py --stygian latest --ver 7.2`, or a start date) writes the
`Stygian Onslaught/<date>` event page: the Event infobox and durations (the wiki's end is 03:59:59 eight
days before the data's), the battlefield summary table, each difficulty's objective, Ley Line Disturbance and
opposing lineup (levels, advantages, bullet summaries and mechanics), the enemy descriptions, gallery, total
rewards and Other Languages. The description and Battle Pass mission are only in the data while the event is
the newest one. The announcement summary and HoYoLAB link are not in the game data, and wiki enemy page
names can differ from the in-game names in `{{Card}}`/`{{Enemy}}`, so check those. Gold highlights become
`{{Color|help|...}}` from `TextMap/TextMapEN_Highlights.json`, which dataset setup saves before cleaning the
TextMap.

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
- **Dataset:** visitors pick from the revisions prepared on the server. They cannot
  run setup, change sources, or change server settings. Older revisions may be
  removed to make space. A browser whose picked revision has been removed falls
  back to the default and says so. Run Painmelo locally for other revisions.

Backend (any Docker host with a persistent volume of about 15 GB, and about 8 GB of RAM for the TextMaps):
```bash
docker build -t painmelo .
docker run -d -p 8000:8000 -v painmelo-data:/data \
  -e PAINMELO_CORS_ORIGINS=https://your-site.vercel.app painmelo
docker stop <container>
docker run --rm --entrypoint python -v painmelo-data:/data painmelo -u setupData.py --all-revisions
docker start <container>
```
The first start writes a remote-data profile to `/data/scriptconfig.json`.
`--all-revisions` requires both sources to follow their latest revision. It prepares
available Excel/TextMap and BinOutput history, newest first, skipping commits without
the required data. Stop the backend before running it: pruning must not remove data
used by jobs. Hosted servers launched with `python -m webui --hosted` hold a shared
lock that prevents historical maintenance from running concurrently.

The command reserves 5 GiB while running (`--reserve-gb` changes this), and needs
another 4 GiB of staging space. It removes known older prepared snapshots when needed,
but protects the active dataset and BinOutput references. If no eligible older
snapshot can make enough space, it stops preparing older history. A revision larger
than the staging space can still fail: the reserved space is released on exit.
Interrupted setup may leave `setup.lock` or `history-reserve` in `/data/.data`;
check that no setup process is running before removing either file. Git caches also
grow and are not pruned by this option. Historical BinOutput key recovery uses the
latest readable reference; inspect its warnings for older revisions. Rerun the
maintenance command after each update.

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
Enable **Web Analytics** in the Vercel project before deploying. Keep **Enable access
to System Environment Variables** enabled: the `VERCEL=1` build flag enables the
Analytics component only on Vercel, not in local workshop/preview builds.
The static HTML requests Discord's large-image preview below the Painmelo title, without a description.

Local mode (`python -m webui`, the default) is unchanged: loopback only, with
same-origin checks, server-side jobs and bot queue in the working directory, and
dataset setup available.