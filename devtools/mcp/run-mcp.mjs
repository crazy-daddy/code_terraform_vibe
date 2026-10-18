// Launches the code-terraform-mcp submodule. The server fixes its paths at startup, so this
// resolves them per launch: the newest save workspace and the newest DOCS Manual export in
// docs/ (by mtime, like split_docs_manual.py). A new save or manual build needs an MCP restart.
// Env vars set by the caller win.
import { existsSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");

function newest(dir, test) {
  if (!existsSync(dir)) return null;
  const hits = readdirSync(dir)
    .map((name) => join(dir, name))
    .filter(test)
    .map((path) => ({ path, mtime: statSync(path).mtimeMs }))
    .sort((a, b) => b.mtime - a.mtime);
  return hits[0]?.path ?? null;
}

const saves = join(process.env.APPDATA ?? "", "io.codeterraform.game");
const workspace = newest(saves, (p) => /[\\/]save_[^\\/]*_scripts$/.test(p) && existsSync(join(p, "codeterraform-workspace.json")));
const manual = newest(join(repo, "docs"), (p) => /[\\/]Code-Terraform-DOCS-Manual[^\\/]*\.md$/.test(p));

if (workspace) process.env.CODE_TERRAFORM_WORKSPACE ||= workspace;
if (manual) process.env.CODE_TERRAFORM_DOCS_MANUAL ||= manual;
process.env.CODE_TERRAFORM_PYTHON ||= "python";
process.env.CODE_TERRAFORM_RUFF ||= join(repo, ".venv", "Scripts", "ruff.exe");
process.env.CODE_TERRAFORM_LOG_LEVEL ||= "warn";

await import(new URL("./code-terraform-mcp/dist/index.js", import.meta.url));
