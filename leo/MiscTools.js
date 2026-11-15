const { ArgumentParser, RawDescriptionHelpFormatter } = require("argparse");
const { SingleBar } = require("cli-progress");
const { writeFileSync } = require("fs");
const { join } = require("path");
const stringify = require("json-stringify-pretty-compact");
const CONFIG = require("./config");

/**
 * Loads a mapped table that only some data sources provide (for example, GuraFoundation has no QuestExcelConfigData).
 */
function optionalRequire(name) {
  try {
    return require(join(OPTIONS.input_dir, `${name}.json`));
  } catch (error) {
    if (error.code !== "MODULE_NOT_FOUND") throw error;
    return null;
  }
}

/**
 * Options set by command line arguments and defaults.
 */
const OPTIONS = {
  option: null,
  input_dir: CONFIG.RepoPath + "/MappedExcelBinOutput_EN",
  output_dir: CONFIG.OutputPath,
  output_file: null,
  print: false,
  questId: null,
  chapterId: null,
  characterName: null,
  characterId: null,
  levels: [11,13,13],
  scheduleId: null,
  toText: false,
  wikitext: false,
  showIds: false,
  debug: false,
}

/**
 * Excel Files.
 */
const EXCELS = {
  AvatarExcelConfigData: require(OPTIONS.input_dir + "/AvatarExcelConfigData.json"),
  AvatarSkillDepotExcelConfigData: require(OPTIONS.input_dir + "/AvatarSkillDepotExcelConfigData.json"),
  AvatarSkillExcelConfigData: require(OPTIONS.input_dir + "/AvatarSkillExcelConfigData.json"),
  AvatarTalentExcelConfigData: require(OPTIONS.input_dir + "/AvatarTalentExcelConfigData.json"),
  ChapterExcelConfigData: require(OPTIONS.input_dir + "/ChapterExcelConfigData.json"),
  CombineExcelConfigData: require(OPTIONS.input_dir + "/CombineExcelConfigData.json"),
  /*DialogExcelConfigData: require(OPTIONS.input_dir + "/DialogExcelConfigData.json"),*/
  FettersExcelConfigData: require(OPTIONS.input_dir + "/FettersExcelConfigData.json"),
  FishExcelConfigData: require(OPTIONS.input_dir + "/FishExcelConfigData.json"),
  FishStockExcelConfigData: require(OPTIONS.input_dir + "/FishStockExcelConfigData.json"),
  HomeWorldFurnitureExcelConfigData: require(OPTIONS.input_dir + "/HomeWorldFurnitureExcelConfigData.json"),
  MainQuestExcelConfigData: require(OPTIONS.input_dir + "/MainQuestExcelConfigData.json"),
  MonsterDescribeExcelConfigData: require(OPTIONS.input_dir + "/MonsterDescribeExcelConfigData.json"),
  ProudSkillExcelConfigData: require(OPTIONS.input_dir + "/ProudSkillExcelConfigData.json"),
  QuestExcelConfigData: optionalRequire("QuestExcelConfigData"),
  TowerFloorExcelConfigData: require(OPTIONS.input_dir + "/TowerFloorExcelConfigData.json"),
  TowerLevelExcelConfigData: require(OPTIONS.input_dir + "/TowerLevelExcelConfigData.json"),
  TowerScheduleExcelConfigData: require(OPTIONS.input_dir + "/TowerScheduleExcelConfigData.json"),
  GCGDeckExcelConfigData: require(OPTIONS.input_dir + "/GCGDeckExcelConfigData.json"),
  GCGGameExcelConfigData: require(OPTIONS.input_dir + "/GCGGameExcelConfigData.json"),
  GCGGameRewardExcelConfigData: require(OPTIONS.input_dir + "/GCGGameRewardExcelConfigData.json"),
  GCGWeekLevelExcelConfigData: require(OPTIONS.input_dir + "/GCGWeekLevelExcelConfigData.json"),
}

/**
 * Main Function
 */
function main() {

  // Parse the Arguments.
  const parser = new ArgumentParser({
    description: "Genshin Data Excel Mapping Additional Tools.",
    formatter_class: RawDescriptionHelpFormatter,
  });

  parser.add_argument('option', {
    nargs: 1,
    help: `Action to perform. \
      combine=Crafting Recipes, \
      quest=Quest Dialogue (questId), \
      chapter=Chapter with Quest Dialogue (chapterId), \
      voiceover=Character Voice-Overs (characterId, characterName), \
      abilities=Character Talents and Constellations, \
      spiralabyss=Spiral Abyss enemies (scheduleId), \
      fishstock=Fish Stock, \
      tcgstages=Genius Invokation TCG Stages`,
    choices: ["combine", "quest", "chapter", "voiceover", "abilities", "spiralabyss", "fishstock", "tcgstages"]
  });
  parser.add_argument("-i", "--input", { help: "input directory of maxed Excels JSONs." });
  parser.add_argument("-o", "--output", { help: "output directory." });
  parser.add_argument("-f", "--file", { help: "output file name." });
  parser.add_argument("-p", "--print", { action: "store_const", const: true, help: "print to console." });
  parser.add_argument("-q", "--questId", { help: "Quest ID." });
  parser.add_argument("-c", "--chapterId", { help: "Chapter ID." });
  parser.add_argument("-charName", "--characterName", { help: "Character Name, separated by semicolon." });
  parser.add_argument("-charId", "--characterId", { help: "Character Id, separated by semicolon." });
  parser.add_argument("-l", "--levels", { help: "Max talent scaling level, separated by semicolon." });
  parser.add_argument("-s", "--scheduleId", { help: "Schedule ID." });
  parser.add_argument("-t", "--toText", { action: "store_const", const: true, help: "Convert to Text." });
  parser.add_argument("-wt", "--wikitext", { action: "store_const", const: true, help: "Convert to Wikitext." });
  parser.add_argument("-id", "--showIds", { action: "store_const", const: true, help: "Show dialog and quest IDs." });
  parser.add_argument("-d", "--debug", { action: "store_const", const: true, help: "print debug statements." });

  // Assign the Arguments.
  let parsed_args = parser.parse_args();
  OPTIONS.option = parsed_args.option[0];
  if (parsed_args.input) {
    OPTIONS.input_dir = parsed_args.input;
    Object.keys(EXCELS).forEach(key => {
      EXCELS[key] = require(`${OPTIONS.input_dir}/${key}.json`);
    });
  }
  if (parsed_args.output) OPTIONS.output_dir = parsed_args.output;
  if (parsed_args.file) OPTIONS.output_file = parsed_args.file;
  if (parsed_args.print) OPTIONS.print = parsed_args.print;
  if (parsed_args.questId) OPTIONS.questId = parsed_args.questId;
  if (parsed_args.chapterId) OPTIONS.chapterId = parsed_args.chapterId;
  if (parsed_args.characterName) OPTIONS.characterName = parsed_args.characterName;
  if (parsed_args.characterId) OPTIONS.characterId = parseInt(parsed_args.characterId);
  if (parsed_args.levels) OPTIONS.levels = String(parsed_args.levels).split(";");
  if (parsed_args.scheduleId) OPTIONS.scheduleId = parsed_args.scheduleId;
  if (parsed_args.toText) OPTIONS.toText = parsed_args.toText;
  if (parsed_args.wikitext) OPTIONS.wikitext = parsed_args.wikitext;
  if (parsed_args.showIds) OPTIONS.showIds = parsed_args.showIds;
  if (parsed_args.debug) OPTIONS.debug = parsed_args.debug;

  if (OPTIONS.debug) console.log(OPTIONS);

  // Call function based on options provided and set file name.
  let result = null;
  switch (OPTIONS.option) {
    case "combine": {
      if (!OPTIONS.output_file) OPTIONS.output_file = "combine.json";
      result = getCombine();
      break;
    }
    case "quest": {
      if (!OPTIONS.output_file && !OPTIONS.questId) OPTIONS.output_file = "quests.json";
      else if (OPTIONS.questId) OPTIONS.output_file = `quest_${OPTIONS.questId}.json`;
      if (OPTIONS.questId) result = getQuests(OPTIONS.questId);
      else result = getQuests();
      break;
    }
    case "chapter": {
      if (!OPTIONS.output_file && !OPTIONS.chapterId) OPTIONS.output_file = "chapters.json";
      else if (OPTIONS.chapterId) OPTIONS.output_file = `chapter_${OPTIONS.chapterId}.json`;
      if (OPTIONS.chapterId) result = getChapters(OPTIONS.chapterId);
      else result = getChapters();
      break;
    }
    case "voiceover": {
      if (!OPTIONS.output_file && !OPTIONS.characterName) OPTIONS.output_file = "voiceover.json";
      else if (OPTIONS.characterName) OPTIONS.output_file = `voiceover_${OPTIONS.characterName}.json`;
      if (OPTIONS.characterName) result = getVoiceOvers(OPTIONS.characterName);
      else result = getVoiceOvers();
      break;
    }
    case "abilities": {
      if (!OPTIONS.output_file && !OPTIONS.characterId && !OPTIONS.characterName) OPTIONS.output_file = "abilities.json";
      else if (OPTIONS.characterId) OPTIONS.output_file = `abilities_${OPTIONS.characterId}.json`;
      else if (OPTIONS.characterName) OPTIONS.output_file = `abilities_${OPTIONS.characterName}.json`;
      if (OPTIONS.characterId) result = getCharacter("abilities", OPTIONS.characterId);
      else if (OPTIONS.characterName) result = getCharacter("abilities", OPTIONS.characterName);
      else result = getCharacter("abilities");
      break;
    }
    case "spiralabyss": {
      if (!OPTIONS.scheduleId) return console.log("scheduleId required.")
      if (!OPTIONS.output_file) OPTIONS.output_file = `spiralabyss_${OPTIONS.scheduleId}.txt`;
      result = getSpiralAbyss(OPTIONS.scheduleId);
      break;
    }
    case "fishstock": {
      if (!OPTIONS.output_file) OPTIONS.output_file = `fishstock.json`;
      result = mapFishStock();
      break;
    }
    case "tcgstages": {
      if (!OPTIONS.output_file) OPTIONS.output_file = `tcgstages.json`;
      result = getTCGStages();
      break;
    }
    default: {
      result = null;
      break;
    }
  }

  // Converts result to text based on option and changes file to txt.
  if (result != null && OPTIONS.toText) {
    if (OPTIONS.option == "quest") {
      if (OPTIONS.questId != null) {
        result = questToText(result);
      } else {
        result = result.map(q => questToText(q)).join("\n");
      }
      OPTIONS.output_file = OPTIONS.output_file.replace(".json", ".txt");
    } else if (OPTIONS.option == "chapter") {
      if (OPTIONS.chapterId != null) {
        result = chapterToText(result);
      } else {
        result = Object.values(result).map(c => chapterToText(c)).join("\n");
      }
      OPTIONS.output_file = OPTIONS.output_file.replace(".json", ".txt");
    } else if (OPTIONS.option == "voiceover") {
      result = voiceOverToText(result, OPTIONS.characterName);
      OPTIONS.output_file = OPTIONS.output_file.replace(".json", ".txt");
    } else {
      return console.log(`${OPTIONS.option} does not support text.`);
    }
  }

  if (result != null && OPTIONS.wikitext) {
    if (OPTIONS.option == "chapter") {
      if (OPTIONS.chapterId != null) {
        result = chapterToWikitext(result);
      } else {
        result = Object.values(result).map(c => chapterToWikitext(c)).join("\n");
      }
      OPTIONS.output_file = OPTIONS.output_file.replace(".json", ".txt");
    } else if (OPTIONS.option == "quest") {
      if (OPTIONS.questId != null) {
        result = questToWikitext(result);
      } else {
        result = Object.values(result).map(c => questToWikitext(c)).join("\n");
      }
      OPTIONS.output_file = OPTIONS.output_file.replace(".json", ".txt");
    } else if (OPTIONS.option == "abilities") {
      result = abilitiesToWikitext(result);
      OPTIONS.output_file = OPTIONS.output_file.replace(".json", ".txt");
    } else {
      return console.log(`${OPTIONS.option} does not support wikitext.`);
    }
  }

  // Save output to file
  if (result != null) {
    if (OPTIONS.print) console.log(stringify(result, { maxLength: 100 }));
    else {
      writeFileSync(join(OPTIONS.output_dir, OPTIONS.output_file), OPTIONS.output_file.includes(".json") ? stringify(result, { maxLength: 100 }) : result);
      console.log(`Saved ${OPTIONS.output_file}`);
    }
  }
}

/**
 * Gets the recipes from Crafting and Converting.
 */
function getCombine() {
  let result = []
  for (let i = 0; i < EXCELS.CombineExcelConfigData.length; i++) {
    let recipe = EXCELS.CombineExcelConfigData[i]
    let res = {
      type: recipe.RecipeType,
      result: recipe.ResultItemId,
      resultCount: recipe.ResultItemCount,
      input1: recipe.MaterialItems[0].Id,
      input1Count: recipe.MaterialItems[0].Count
    };
    if (recipe.MaterialItems[1]) {
      res.input2 = recipe.MaterialItems[1].Id,
        res.input2Count = recipe.MaterialItems[1].Count
    }
    if (recipe.MaterialItems[2]) {
      res.input3 = recipe.MaterialItems[2].Id,
        res.input3Count = recipe.MaterialItems[2].Count
    }
    result.push(res);
  }
  return result;
}

/**
 * Maps the fish names to fishing point probabilities.
 * @returns FishStockExcelConfigData with fish names.
 */
function mapFishStock() {
  let result = EXCELS.FishStockExcelConfigData.map(stock => {
    stock.FishWeight = Object.entries(stock.FishWeight).map(([id, value]) => {
      let fish = EXCELS.FishExcelConfigData.find(f => f.Id == id);
      let furn = EXCELS.HomeWorldFurnitureExcelConfigData.find(f => f.Id == fish.ItemId);
      return {
        Name: furn ? `Ornamental ${furn.NameTextMapHash}` : fish ? fish.ItemId : id,
        Value: value
      }
    });
    return stock;
  })
  return result;
}

/**
 * Cleans the dialog object.
 * @param {Object} dialog DialogExcelConfigData object.
 * @returns Dialog with values cleaned.
 */
function cleanDialog(dialog) {
  try {
    return {
      id: dialog.Id,
      name: dialog.TalkRole.Type == "TALK_ROLE_PLAYER" ? "Traveler" : dialog.TalkRole.Type == "TALK_ROLE_MATE_AVATAR" ? "Traveler's Sibling" : dialog.TalkRole.Id,
      text: dialog.TalkContentTextMapHash,
      nextDialogs: dialog.NextDialogs
    }
  } catch (e) {
    console.log(dialog);
    console.error(e);
  }
}

/**
 * Gets the quest from MainQuestExcelConfigData maps dialog. If id not provided, then return all quests.
 * @param {number} [id] Quest id.
 * @returns Quest(s) and its dialog.
 */
function getQuests(id) {
  if (id) {
    let quest = EXCELS.MainQuestExcelConfigData.find(quest => quest.Id == id);
    if (!quest) return console.error(`Quest "${id}" is not a valid id.`)
    return mapQuest(quest);
  } else {
    let result = [];
    const bar = new SingleBar({ stopOnComplete: true });
    bar.start(EXCELS.MainQuestExcelConfigData.length, 0);
    EXCELS.MainQuestExcelConfigData.forEach(quest => {
      result.push(mapQuest(quest));
      bar.increment()
    });
    return result;
  }
}

/**
 * Maps Quest's steps and dialogs
 * @param {Object} quest MainQuestExcelConfigData quest object.
 * @returns Quest with QuestExcelConfigData and DialogExcelConfigData added.
 */
function mapQuest(quest) {
  if (!EXCELS.QuestExcelConfigData) throw new Error("This data source has no QuestExcelConfigData; quest tools need DimbreathBot Excel data.");
  let scenes = EXCELS.QuestExcelConfigData.filter(scene => scene.MainId == quest.Id);
  quest.Scenes = [];
  scenes.forEach(scene => { // `^${scene.SubId}[0-9]{4}$`
    let dialog = EXCELS.DialogExcelConfigData.filter(dialog => String(dialog.Id).match(new RegExp(`^${scene.SubId}.*$`)) && dialog.TalkRole != undefined).map(cleanDialog)
    if (dialog.length > 0) {
      res = {};
      res.Id = scene.Id;
      res.SubId = scene.SubId;
      res.Order = scene.Order;
      if (scene.DescTextMapHash) res.DescTextMapHash = scene.DescTextMapHash
      if (scene.StepDescTextMapHash) res.StepDescTextMapHash = scene.StepDescTextMapHash
      res.Dialog = dialog
      quest.Scenes.push(res);
    }
  });
  return quest;
}

/**
 * Gets the chapter from ChapterExcelConfigData and maps quests. If id not provided, then return all chapters.
 * @param {number} id Chapter id.
 * @returns Chapter(s) and its Quests mapped.
 */
function getChapters(id) {
  if (id) {
    let chapter = EXCELS.ChapterExcelConfigData.find(chapter => chapter.Id == id);
    if (!chapter) return console.error(`Chapter "${id}" is not a valid id.`)
    return {
      Id: chapter.Id,
      ChapterNumTextMapHash: chapter.ChapterNumTextMapHash,
      ChapterTitleTextMapHash: chapter.ChapterTitleTextMapHash,
      ChapterIcon: chapter.ChapterIcon,
      Steps: EXCELS.MainQuestExcelConfigData.filter(quest => quest.ChapterId == chapter.Id).map(mapQuest)
    };
  } else {
    let result = {};
    let quests = {};
    EXCELS.MainQuestExcelConfigData.filter(quest => quest.ChapterId).map(quest => {
      if (quests[quest.ChapterId]) quests[quest.ChapterId].push(quest);
      else quests[quest.ChapterId] = [quest];
    }); 155
    const bar = new SingleBar({ stopOnComplete: true });
    bar.start(EXCELS.ChapterExcelConfigData.length, 0);
    EXCELS.ChapterExcelConfigData.forEach(chapter => {
      result[chapter.Id] = {
        Id: chapter.Id,
        ChapterNumTextMapHash: chapter.ChapterNumTextMapHash,
        ChapterTitleTextMapHash: chapter.ChapterTitleTextMapHash,
        ChapterIcon: chapter.ChapterIcon,
        Steps: quests[chapter.Id] ? quests[chapter.Id].map(mapQuest) : []
      };
      bar.increment()
    });
    return result;
  }
}

/**
 * Converts Chapter to text.
 * @param {Object} chapter Chapter to convert to text.
 * @returns Chapter in text format.
 */
function chapterToText(chapter) {
  if (OPTIONS.debug) console.log(`Converting Chapter ${chapter.Id} to Text.`);
  let result = `${chapter.ChapterNumTextMapHash} - ${chapter.ChapterTitleTextMapHash}, ${chapter.ChapterIcon}\n`
  chapter.Steps.forEach(step => {
    result += questToText(step)
  })
  return result;
}

/**
 * Converts Quest to text.
 * @param {Object} quest Quest to convert to text.
 * @returns Quest and dialog in text format.
 */
function questToText(quest) {
  if (OPTIONS.debug) console.log(`Converting Quest ${quest.Id} to Text.`);
  let result = `${OPTIONS.showIds ? quest.Id + " " : ""}${quest.TitleTextMapHash}\n\t${quest.DescTextMapHash}\n`
  quest.Scenes.forEach(scene => {
    result += `\t${OPTIONS.showIds ? scene.SubId + " " : ""}${scene.DescTextMapHash}${scene.StepDescTextMapHash ? `\n\t${scene.StepDescTextMapHash}` : ""}\n`
    scene.Dialog.forEach(dialog => {
      let text = dialog.text;
      result += `\t\t${OPTIONS.showIds ? dialog.id + " " : ""}${dialog.name}: ${text}\n`
    })
  })
  return result;
}

/**
 * Converts Chapter to Wikitext.
 * @param {Object} chapter Chapter to convert to Wikitext.
 * @returns Chapter in Wikitext format.
 */
function chapterToWikitext(chapter) {
  if (OPTIONS.debug) console.log(`Converting Chapter ${chapter.Id} to Wikitext.`);
  let result = `=${chapter.ChapterNumTextMapHash} - ${chapter.ChapterTitleTextMapHash}=\n`
  chapter.Steps.forEach(step => {
    result += questToWikitext(step)
  })
  return result;
}

/**
 * Converts Quest to Wikitext.
 * @param {Object} quest Quest to convert to Wikitext.
 * @returns Quest and dialog in Wikitext format.
 */
function questToWikitext(quest) {
  if (OPTIONS.debug) console.log(`Converting Quest ${quest.Id} to Wikitext.`);
  let result = `==${OPTIONS.showIds ? quest.Id + " " : ""}${quest.TitleTextMapHash}==\n${quest.DescTextMapHash}\n`
  result += "{{Dialogue start}}\n";
  quest.Scenes.forEach((scene, sceneIndex) => {
    result += `;(${OPTIONS.showIds ? scene.SubId + " " : ""}${scene.DescTextMapHash})${scene.StepDescTextMapHash ? `\n${scene.StepDescTextMapHash}` : ""}\n`
    scene.Dialog.forEach(dialog => {
      let text = dialog.text;
      result += `:'''${OPTIONS.showIds ? dialog.id + " " : ""}${dialog.name}:''' ${text}\n`
    })
    if (sceneIndex < quest.Scenes.length - 1) result += "----\n";
  })
  result += "{{Dialogue end}}\n";
  return result;
}

function replaceTitle(title) {
  if (title == "Skill DMG") return "skilldmg";
  else if (title == "1-Hit DMG") return "hit1";
  else if (title == "2-Hit DMG") return "hit2";
  else if (title == "3-Hit DMG") return "hit3";
  else if (title == "4-Hit DMG") return "hit4";
  else if (title == "5-Hit DMG") return "hit5";
  else if (title == "6-Hit DMG") return "hit6";
  else if (title == "Aimed Shot") return "aimed";
  else if (title == "Charged Attack DMG") return "charged";
  else if (title == "Charged Attack Stamina Cost") return "stamina";
  else if (title == "Plunge DMG") return "plunge";
  else return title
    .replace("{LAYOUT_MOBILE#Tapping}{LAYOUT_PC#Press}{LAYOUT_PS#Press}", "Press")
    .replace(/ /g, "")
    .replace("#", "")
    .replace(":", "")
    .toLowerCase();
}

/**
 * Converts Talent Scaling to Wikitext.
 * @param {Object[]} abilities Array of character abilities.
 * @returns Talent scaling for characters in Wikitext format.
 */
function abilitiesToWikitext(abilities) {
  let abilities_result = abilities.map(character => {
    try {
      // if (character.elements) character.abilities = character.elements[1]; // For Traveler Elemental Alignment.
      return {
        name: character.name,
        talents: character.abilities.talents.filter(talent => talent.levels.length > 0).map(talent => {
          let scaling = {};
          talent.levels.forEach(level => {
            let plunged = false;
            level.values.forEach(({ title, value }, i) => {
              if (title == "Low/High Plunge DMG") {
                scaling[`${i}_plungelow_${level.level}`] = value.split("/")[0];
                scaling[`${i + 1}_plungehigh_${level.level}`] = value.split("/")[1];
                plunged = true;
              } else {
                if (plunged) {
                  scaling[`${i + 1}_${replaceTitle(title)}_${level.level}`] = value;
                } else {
                  scaling[`${i}_${replaceTitle(title)}_${level.level}`] = value;
                }
              }
            })
          })
          let order = [];
          talent.levels[0].values.forEach(({ title }) => {
            if (title == "Low/High Plunge DMG") {
              order.push("plungelow");
              order.push("plungehigh");
            } else {
              order.push(replaceTitle(title));
            }
          });
          let titles = [];
          talent.levels[0].values.forEach(({ title }) => {
            if (title == "Low/High Plunge DMG") {
              titles.push("Low Plunge DMG");
              titles.push("High Plunge DMG");
            } else {
              titles.push(title
                .replace("{LAYOUT_MOBILE#Tapping}{LAYOUT_PC#Press}{LAYOUT_PS#Press}", "Press")
                .replace("#", ""));
            }
          });
          return {
            name: talent.name.replace("Normal Attack: ", ""),
            scaling: scaling,
            order: order,
            titles: titles
          }
        })
      }
    } catch (ex) {
      console.error(ex);
    }
  }).map(character => {
    if (!character) return "";
    return `=${character.name}=\n${character.talents.map((talent, j) => {
      let levels = OPTIONS.levels[j] ?? 13;
      let result = "{{Talent Scaling\n";
      result += `|levels=${levels}\n`;
      result += `|order=${addOrderHeadings(talent.order)}\n`;
      result += `|titles=${addTitleHeadings(talent.titles)}\n`;
      talent.order.forEach((key, i) => {
        let talentValues = Object.entries(talent.scaling).filter(([sKey, _]) => sKey.startsWith(`${i}_${key}_`))
        if (talentValues.every(([_, val]) => val === talentValues[0][1])) {
          result += `|${key}=${talent.scaling[`${i}_${key}_1`]}\n`
        } else {
          for (let j = 1; j <= levels; j++) {
            result += `|${key}_${j}=${talent.scaling[`${i}_${key}_${j}`]}\n`
          }
        }
      })
      result += "}}"
      return `==${talent.name}==\n${formatScaling(result)}`;
    }).join("\n")}`;
  }).join("\n");
  return abilities_result;
}

const NUMBER = String.raw`\d+(?:\.\d+)?`;
// Repeated hits share one value ("34.57+34.57 DEF"); differing parts can be a flat bonus ("270 + 2.8 Max HP").
const STAT_VALUE = String.raw`(${NUMBER})(?:\+\1)*(?:/${NUMBER})*`;
const SCALING_UNITS = [
  [new RegExp(`^${NUMBER}(?:[+/]${NUMBER})*$`), "%"],
  [new RegExp(`^${STAT_VALUE}MaxHP$`), "%Max HP"],
  [new RegExp(`^${STAT_VALUE}CurrentHP$`), "%Current HP"],
  [new RegExp(`^${STAT_VALUE}DEF$`), "%DEF"],
  [new RegExp(`^${STAT_VALUE}ATK$`), "%ATK"],
  [new RegExp(`^${STAT_VALUE}ElementalMastery$`), "%EM"],
];
// The header names the stat, so it is dropped from the values.
const UNIT_STATS = { "%Max HP": /\s*Max HP/g, "%Current HP": /\s*Current HP/g, "%DEF": /\s*DEF/g, "%ATK": /\s*ATK/g, "%EM": /\s*Elemental Mastery/g };
// "DMG" that names the damage itself, not e.g. "DMG Bonus" or "DMG Absorption".
const DAMAGE_TITLE = /\bDMG(?=$| \(|:)/;
const MULTIPLIER = /[×*]\d+(?:\.\d+)?/g;
const OPERATOR = /(?<=\S)\s*([+×*])\s*(?=\S)/g;
// In unlabelled columns, stat percentages keep their stat and get a percent sign, as in game: "0.8% Max HP + 77".
const STAT_PERCENT = new RegExp(String.raw`(${NUMBER}) ?(Max HP|Current HP|DEF|ATK|Elemental Mastery)\b(?! DMG)`, "g");

/**
 * Gets the shared unit of a column's values.
 * @param {String[]} values Values of one Talent Scaling column.
 * @returns The unit, or null for mixed, flat-bonus, or other scalings.
 */
function scalingUnit(values) {
  const units = new Set(values.map(value => {
    const compact = value.replace(/ /g, "").replace(MULTIPLIER, "");
    return SCALING_UNITS.find(([pattern]) => pattern.test(compact))?.[1] ?? null;
  }));
  return units.size == 1 ? [...units][0] : null;
}

/**
 * Labels Talent Scaling titles with their scaling and normalizes the values.
 * @param {String} template Talent Scaling template.
 * @returns The formatted template.
 */
function formatScaling(template) {
  const lines = template.split("\n");
  const valueOf = line => line.slice(line.indexOf("=") + 1);
  const fields = new Map();
  lines.forEach((line, index) => { if (line.startsWith("|")) fields.set(line.slice(1, line.indexOf("=")), index); });
  let order = valueOf(lines[fields.get("order")]).split(",");
  let titles = valueOf(lines[fields.get("titles")]).split(",");
  const values = {};
  const rows = {};
  for (const [name, index] of fields) {
    if (["levels", "order", "titles"].includes(name)) continue;
    const value = valueOf(lines[index]);
    const key = name.replace(/_\d+$/, "");
    (values[key] ??= []).push(value);
    (rows[key] ??= []).push(index);
    lines[index] = `|${name}=${value.replace(OPERATOR, " $1 ")}`;
  }
  const labelled = new Set();
  if (order.length == titles.length) {
    // Titles containing commas ("Bloom, Hyperbloom, and Burgeon DMG Increase") are split in both lists; rejoin them.
    const merged = [];
    for (let i = 0; i < order.length;) {
      let end = order.length;
      while (end > i + 1 && !(order.slice(i, end).join(",") in values)) end--;
      merged.push([order.slice(i, end).join(","), titles.slice(i, end).join(",")]);
      i = end;
    }
    order = merged.map(([key]) => key);
    titles = merged.map(([, title]) => title);
    order.forEach((key, i) => {
      let unit = key in values ? scalingUnit(values[key]) : null;
      // Plain percentages are only labelled on damage titles; stat scalings are labelled on any title.
      if (unit == "%" && !DAMAGE_TITLE.test(titles[i])) unit = null;
      if (unit) titles[i] = `${titles[i]} (${unit})`;
      if (unit in UNIT_STATS) {
        labelled.add(key);
        for (const index of rows[key]) lines[index] = lines[index].replace(UNIT_STATS[unit], "");
      }
    });
    lines[fields.get("titles")] = `|titles=${titles.join(",")}`;
  }
  for (const [key, indexes] of Object.entries(rows)) {
    if (labelled.has(key)) continue;
    for (const index of indexes) {
      const split = lines[index].indexOf("=") + 1;
      lines[index] = lines[index].slice(0, split) + lines[index].slice(split).replace(STAT_PERCENT, "$1% $2");
    }
  }
  return lines.join("\n");
}

/**
 * Get values for order argument of Talent Scaling.
 * @param {String[]} orders Array of order names.
 * @returns String of order names.
 */
function addOrderHeadings(orders) {
  let result = [];
  orders.forEach(order => {
    if (order == "aimed" || order == "charged" || order == "chargedattackcyclicdmg") result.push("charged_title");
    else if (order == "plunge") result.push("plunge_title");
    result.push(order);
  });
  return result.join(",")
}

/**
 * Get values for title argument of Talent Scaling.
 * @param {String[]} titles Array of title names.
 * @returns String of title names.
 */
function addTitleHeadings(titles) {
  let result = [];
  titles.forEach(title => {
    if (title == "Aimed Shot" || title == "Charged Attack DMG" || title == "Charged Attack Cyclic DMG") result.push("Charged Attack");
    else if (title == "Plunge DMG") result.push("Plunging Attack");
    result.push(title);
  });
  return result.join(",")
}

/**
 * Gets Character's voiceovers from FettersExcelConfigData.
 * @param {String} char Character Name.
 * @returns Character's Voiceovers.
 */
function getVoiceOvers(char) {
  if (typeof EXCELS.FettersExcelConfigData[0].title == "object" && Object.keys(EXCELS.FettersExcelConfigData[0].title).length > 2)
    return console.error(`FettersExcelConfigData.json must only contain English and one other language.`)
  let voiceovers = EXCELS.FettersExcelConfigData.filter(fetter => {
    if (typeof fetter.AvatarId == "object") {
      return fetter.AvatarId["EN"] == char
    } else {
      return fetter.AvatarId == char;
    }
  });
  if (!voiceovers || voiceovers.length == 0) return console.error(`Character "${char}" is not a valid id.`)
  let result = voiceovers.map(vo => {
    return {
      file: vo.VoiceFile,
      title: vo.VoiceTitleTextMapHash,
      text: vo.VoiceFileTextTextMapHash
    }
  });
  return result;
}

const VO_ORDER = ["00", "11", "12", "10", "19", "20", "30", "40", "50", "60", "70", "80"]
/**
 * Converts voiceovers to wikitext.
 * @param {[Object]} voiceovers Voiceovers to convert.
 * @param {String} characterName Character Name.
 * @returns Voiceovers in wikitext format.
 */
function voiceOverToText(voiceovers, characterName) {
  // Check arguments
  if (typeof voiceovers[0].title == "object" && Object.keys(voiceovers[0].title).length > 2)
    return console.error(`FettersExcelConfigData.json must only contain English and one other language.`)
  // Group Voiceovers.
  let grouped = Object.assign({}, ...VO_ORDER.map(a => ({ [a]: [] })))
  voiceovers.forEach(vo => {
    if (vo.file == "1000") grouped["00"] = [vo];
    else if ((typeof vo.title == "object" ? vo.title["EN"] : vo.title).indexOf(`About ${characterName}`) == 0) grouped["19"].push(vo);
    else if (vo.file) {
      let prefix = vo.file.substring(0, 2);
      grouped[prefix].push(vo);
    }
  });
  // Create Output.
  let res = `{{VO\n|character={{ROOTPAGENAME}}\n`;
  VO_ORDER.forEach((group, i) => {
    let ii = ("00" + (i + 1)).slice(-2);
    grouped[group].forEach((vo, j) => {
      let jj = ("00" + (j + 1)).slice(-2);
      let title = typeof vo.title == "object" ? vo.title[Object.keys(vo.title).filter(a => a != "EN")[0]] : vo.title;
      title = title
        .replace("·", "・")
        .replace(characterName, "{character}");
      let subtitle = `${vo.title["EN"] ? vo.title["EN"] : ""}`;
      subtitle = subtitle.replace(characterName, "{character}")
      let file = (vo.title["EN"] ? vo.title["EN"] : vo.title)
        .replace(characterName, "{character}")
        .replace(":", " -")
        .replace("Intro", " 01")
        .replace("Building Up", " 02")
        .replace("Climax", " 03")
        .replace("Conclusion", " 04")
        .replace(`${characterName}'s `, "")
        .replace(/ I$/, ` 01`)
        .replace(/ II$/, ` 02`)
        .replace(/ III$/, ` 03`)
        .replace(/ IV$/, ` 04`)
        .replace(/ V$/, ` 05`)
      let transcript = typeof vo.text == "object" ? vo.text[Object.keys(vo.text).filter(a => a != "EN")[0]] : vo.text;
      transcript = transcript
        .replace(/\\n/g, `<br>`)
        .replace(/{M#([^}]+)}{F#([^}]+)}/g, `($1/$2)`)
        .replace(/{F#([^}]+)}{M#([^}]+)}/g, `($2/$1)`)
        .replace(/—/g, `&mdash;`)
        .replace(/·/g, `・`)
        .replace(/<color=#37FFFF>([^<]+)<\/color>/g, `'''$1'''`)
        .replace(/^#/, ``)
        .replace(/{NICKNAME}/g, `(Traveler)`)
      res += `
|vo_${ii}_${jj}_title       = ${title}
|vo_${ii}_${jj}_subtitle    = ${subtitle}
|vo_${ii}_${jj}_file        = VO_{language}{character} ${file}.ogg
|vo_${ii}_${jj}_transcript  = ${transcript}
|vo_${ii}_${jj}_translation = 
|vo_${ii}_${jj}_romanized   = `;
    })
    res += "\n"
  })
  res += "}}"
  return res;
}

/**
 * Get the character's data based on mode.
 * @param {String} mode data of a character to get.
 * @param {String | Number} characterId Character Name or Id to get. Use number for specific Traveler. All if undefined.
 * @returns Character data.
 */
function getCharacter(mode, characterId) {
  let character;
  if (typeof characterId == "string" && characterId.indexOf(";") > -1) character = EXCELS.AvatarExcelConfigData.filter(a => characterId.includes(a.NameTextMapHash));
  else if (typeof characterId == "string") character = EXCELS.AvatarExcelConfigData.filter(a => a.NameTextMapHash == characterId);
  else if (typeof characterId == "number") character = EXCELS.AvatarExcelConfigData.filter(a => a.Id == characterId);
  if (characterId && character && character.length == 0) return console.log(`Character ${characterId} does not exist.`);

  let res = null;
  switch (mode) {
    case "abilities": {
      if (typeof EXCELS.AvatarExcelConfigData[0].NameTextMapHash == "object") return console.log("Must only map one language.")
      if (character) {
        // An Id selects that avatar only; names also match same-named test avatars.
        res = (typeof characterId == "number" ? character : EXCELS.AvatarExcelConfigData.filter(a => character.some(b => a.NameTextMapHash.includes(b.NameTextMapHash)))).map(avatar => {
          let result = {}
          if (avatar.CandSkillDepotIds?.length > 0) {
            if (avatar.BodyType == "BODY_GIRL") result.name = "Lumine";
            else if (avatar.BodyType == "BODY_BOY") result.name = "Aether";
            result.elements = avatar.CandSkillDepotIds.map(id => getCharacterAbilities(EXCELS.AvatarSkillDepotExcelConfigData.find(d => d.Id == id))).filter(e => e.talents[0].name != "")
          }
          if (!result.name) result.name = avatar.NameTextMapHash,
            result.abilities = getCharacterAbilities(EXCELS.AvatarSkillDepotExcelConfigData.find(d => d.Id == avatar.SkillDepotId))
          return result;
        });
      } else {
        res = EXCELS.AvatarExcelConfigData.map(avatar => {
          let result = {}
          if (avatar.CandSkillDepotIds?.length > 0) {
            if (avatar.BodyType == "BODY_GIRL") result.name = "Lumine";
            else if (avatar.BodyType == "BODY_BOY") result.name = "Aether";
            result.elements = avatar.CandSkillDepotIds.map(id => getCharacterAbilities(EXCELS.AvatarSkillDepotExcelConfigData.find(d => d.Id == id))).filter(e => e.talents[0].name != "")
          }
          if (!result.name) result.name = avatar.NameTextMapHash,
            result.abilities = getCharacterAbilities(EXCELS.AvatarSkillDepotExcelConfigData.find(d => d.Id == avatar.SkillDepotId))
          return result;
        });
      }
      break;
    }
  }
  return res;
}


/**
 * Get the character's abilities.
 * @param {Object} skillDepot Object from AvatarSkillDepotExcelConfigData.json
 * @returns Character talents, upgrades, and constellations.
 */
function getCharacterAbilities(skillDepot) {
  let talents = skillDepot.Skills?.filter(a => a > 0).map(s => EXCELS.AvatarSkillExcelConfigData.find(a => a.Id == s)) || [];
  let burst = EXCELS.AvatarSkillExcelConfigData.find(a => a.Id == skillDepot.EnergySkill);
  if (burst) talents.push(burst);
  let passives = skillDepot.InherentProudSkillOpens?.filter(p => p.ProudSkillGroupId).map(p => EXCELS.ProudSkillExcelConfigData.find(a => a.ProudSkillGroupId == p.ProudSkillGroupId)) || [];
  let constellations = skillDepot.Talents?.map(c => EXCELS.AvatarTalentExcelConfigData.find(t => t.TalentId == c)).filter(c => c != undefined) || [];

  let result = {
    character: skillDepot.TalentStarName ? skillDepot.TalentStarName : undefined,
    talents: talents.map(t => ({
      name: t.NameTextMapHash,
      desc: t.DescTextMapHash,
      icon: t.SkillIcon,
      levels: EXCELS.ProudSkillExcelConfigData.filter(a => a.ProudSkillGroupId == t.ProudSkillGroupId).map(mapLevel),
      upgrades: EXCELS.ProudSkillExcelConfigData.filter(a => a.ProudSkillGroupId == t.ProudSkillGroupId).map(l => ({ items: l.CostItems?.filter(i => i.Id), mora: l.CoinCost }))
    })),
    passives: passives.map(p => ({
      name: p.NameTextMapHash,
      desc: p.DescTextMapHash,
      icon: p.Icon
    })),
    constellation: constellations.map(c => ({
      name: c.NameTextMapHash,
      desc: c.DescTextMapHash,
      icon: c.Icon
    }))
  }
  result.talents.forEach(talent => {
    talent.icon = talent.icon || talent.levels[0]?.icon || null;
  });
  return result;
}

/**
 * Gets the titles and values of the talent.
 * @param {Object} skill Talent Level from ProudSkillExcelConfigData.json
 * @returns Talent Level Attributes. 
 */
function mapLevel(skill) {
  if (!skill.ParamDescList || !skill.ParamList) return {};
  return {
    level: skill.Level,
    type: skill.Type,
    icon: skill.Icon,
    values: skill.ParamDescList.filter(d => d != "" && typeof d == 'string').map(a => {
      let title = /(.*)\|/.exec(a);
      let params = [];
      let matches;
      let regex = /\{param(.*?):(.*?)\}/g
      while ((matches = regex.exec(a)) !== null) {
        params.push(matches);
      };
      let value = a.substring(title[0].length)
      params.forEach(p => {
        let amount = skill.ParamList[p[1] - 1]
        if (p[2] == "P" || p[2] == "F1P" || p[2] == "F2P") amount = parseFloat((amount * 100).toFixed(2));
        else if (p[2] == "F1" || p[2] == "F2") amount = parseFloat(amount.toFixed(2));
        else if (p[2] == "I") amount = parseFloat(amount.toFixed(0));
        value = value.replace(p[0], amount)
      })
      return {
        title: title[1],
        value: value
      }
    })
  }
}

/**
 * Get the enemies a specific Spiral Abyss schedule separated by floor, chamber, and half.
 * @param {number} scheduleId Schedule ID
 * @returns Enemies of each floor.
 */
function getSpiralAbyss(scheduleId) {
  let Schedule = EXCELS.TowerScheduleExcelConfigData.find(s => s.ScheduleId == scheduleId);
  let Floors = Schedule.Schedules[0].FloorList.map(floorId => EXCELS.TowerFloorExcelConfigData.find(a => a.FloorId == floorId));
  let FloorChambers = Floors.map(floor => {
    floor.Chambers = EXCELS.TowerLevelExcelConfigData.filter(l => l.LevelGroupId == floor.LevelGroupId);
    return floor;
  });
  let result = "";
  FloorChambers.forEach((floor, f) => {
    result += `Floor ${f + 9}\n`;
    floor.Chambers.forEach((chamber, c) => {
      result += `Chamber ${c + 1}\n`;
      result += `Enemy Level: ${chamber.MonsterLevel + 1}\n`;
      result += `Target: ${chamber.Conds[0].TowerCondType == "TOWER_COND_CHALLENGE_LEFT_TIME_MORE_THAN"
        ? "Remaining challenge time longer than " + chamber.Conds.map(cond => cond.ArgumentList[cond.ArgumentList.length - 1]).join("/") + " sec.\n"
        : "Target defense progress greater than " + chamber.Conds.map(cond => cond.ArgumentList[cond.ArgumentList.length - 1]).join("/") + "%\n"}`;
      // Newer chambers reference a monster preview instead of listing monsters in the Excel data.
      const half = list => list
        ? list.map(id => EXCELS.MonsterDescribeExcelConfigData.find(m => m.Id == id)?.NameTextMapHash || id).join("\n")
        : `(Not in the Excel data; monster preview ${chamber.TowerMonsterPreview ?? "unknown"})`;
      result += `First Half\n`;
      result += `${half(chamber.FirstMonsterList)}\n`;
      result += `Second Half\n`;
      result += `${half(chamber.SecondMonsterList)}\n`;
    });
    result += "\n"
  })

  return result;
}

/**
 * Get the Genius Invokation TCG Stages
 * @returns The Genius Invokation TCG Stages with deck, rewards, description.
 */
function getTCGStages() {
  let result = EXCELS.GCGGameRewardExcelConfigData.map(level => {
    let cards = EXCELS.GCGDeckExcelConfigData.find(d => d.Id == EXCELS.GCGGameExcelConfigData.find(g => g.Id == level.LevelId).EnemyCardGroupId);
    let rewards = EXCELS.GCGGameRewardExcelConfigData.find(g => g.LevelId == level.LevelId);
    let game = EXCELS.GCGGameExcelConfigData.find(g => g.Id == level.LevelId);
    let weekly = EXCELS.GCGWeekLevelExcelConfigData.reduce((a, w) => {
      let l = w.LevelCondList.find(l => l.LevelId == level.LevelId);
      if (l) return l.GcgLevel;
      return a;
    }, undefined)
    return {
      character: game?.OppoPlayerNameTextMapHash,
      name: rewards.LevelNameTextMapHash,
      intro: rewards.LevelDecTextMapHash,
      level: rewards.CondList.find(c => c.Type == "GCG_LEVEL")?.ParamList[0] || weekly,
      rewards: rewards.ChallengeRewardList.reduce((a, c) => {
        if (c.RewardId) a.push(c.RewardId);
        return a;
      }, []),
      deck: {
        active: cards.CharacterList,
        reserve: (cards.WaitingCharacterList || []).reduce((a, c) => {
          if (c.Id) a.push(c.Id);
          return a;
        }, []),
        action: cards.CardList
      }
    }
  });
  return result;
}

main();