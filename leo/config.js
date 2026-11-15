const { readFileSync } = require("fs");
const { dirname, join, resolve } = require("path");

const configPath = resolve(process.env.GENSHIN_TOOLS_CONFIG || join(__dirname, "..", "scriptconfig.json"));
const config = JSON.parse(readFileSync(configPath, "utf8"));
const source = config.DataSource || "local";

if (!["local", "github"].includes(source)) {
  throw new Error('DataSource must be "local" or "github".');
}

if (source === "github") {
  const cache = join(dirname(configPath), ".data", "AnimeGameData");
  let revision;
  let prepared;
  try {
    revision = JSON.parse(readFileSync(join(cache, "ready.json"), "utf8"));
    if (!/^[0-9a-f]{40}$/.test(revision.commit) || !/^[0-9a-f]{64}$/.test(revision.pipeline)) {
      throw new Error("Invalid GitHub setup metadata.");
    }
    config.RepoPath = join(cache, "datasets", `${revision.commit}-${revision.pipeline.slice(0, 12)}`);
    prepared = JSON.parse(readFileSync(join(config.RepoPath, ".prepared.json"), "utf8"));
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    throw new Error("GitHub data is not prepared. Run quickSetup.bat (or python setupData.py) first.");
  }
  if (prepared.commit !== revision.commit || prepared.pipeline !== revision.pipeline) {
    throw new Error("GitHub setup metadata does not match. Run quickSetup.bat again.");
  }
}

module.exports = config;
