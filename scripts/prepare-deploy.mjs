/** Prepare the full-stack Worker from a clean Workers Builds checkout. */
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { delimiter, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const backend = join(root, "commerce-testbed/backend");
const tools = join(root, ".cloudflare/tools");
const uv = join(tools, "uv");
const env = { ...process.env, PATH: `${tools}${delimiter}${process.env.PATH ?? ""}` };
// npm run exports this as a CLI override; child installs must read npmrc policy normally.
delete env.npm_config_allow_scripts;

function run(command, args, cwd = root, environment = env) {
  const result = spawnSync(command, args, { cwd, env: environment, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} ${args.join(" ")} failed (${result.status})`);
}

if (!existsSync(uv)) {
  mkdirSync(tools, { recursive: true });
  const response = await fetch("https://astral.sh/uv/0.13.6/install.sh");
  if (!response.ok) throw new Error(`uv installer download failed: HTTP ${response.status}`);
  const installer = join(tools, "install-uv.sh");
  writeFileSync(installer, await response.text());
  run("sh", [installer], root, { ...env, UV_INSTALL_DIR: tools, UV_NO_MODIFY_PATH: "1" });
}

run("npm", ["run", "build"]);
run("npm", ["ci", "--no-audit", "--no-fund"], backend);
run(uv, ["sync", "--locked", "--group", "dev"], backend);
run(uv, ["run", "--locked", "pywrangler", "sync"], backend);
run(uv, ["run", "--locked", "python", "scripts/build_worker.py"], backend);

// Wrangler resolves vendored Python packages beside the selected config file.
const vendor = join(root, "python_modules");
rmSync(vendor, { recursive: true, force: true });
cpSync(join(backend, "python_modules"), vendor, { recursive: true });
console.log("Full-stack Worker ready: React assets, FastAPI sources, and Python packages.");
