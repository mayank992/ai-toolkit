/** "host/group/project" -> "project"; "local:~/code/x" -> "x"; "" -> "no repo". */
export function shortRepo(repo: string): string {
  if (!repo) return "no repo";
  const parts = repo.replace(/^local:/, "").split("/").filter(Boolean);
  return parts[parts.length - 1] ?? repo;
}

/** "repo:host/a/b" -> "b", "lang:ts" -> "ts files", "global" -> "everywhere". */
export function shortScope(scope: string): string {
  if (scope.startsWith("repo:")) return shortRepo(scope.slice(5));
  if (scope.startsWith("lang:")) return `${scope.slice(5)} files`;
  return scope === "global" ? "everywhere" : scope;
}
