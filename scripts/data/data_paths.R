# 共有データパス解決ヘルパー（正本: research-template、sync で配布）。
# 台帳: docs/data/data-paths.json（説明は docs/data/data-catalog.md）。
#
# 使い方:
#   source(file.path(<repo_root>, "scripts", "data", "data_paths.R"))
#   acc <- data_path("fq_accounting_exp")
#   dt  <- data.table::fread(acc, select = c("NKCODE", "ACC", "Assets"))
#
# ルートは環境変数で上書き可:
# RESEARCH_ONEDRIVE_ROOT / RESEARCH_DESKTOP_ROOT / RESEARCH_PROJECT_ROOT

local({
  script_path <- tryCatch(
    normalizePath(sys.frames()[[1]]$ofile, winslash = "/"),
    error = function(e) NULL
  )
  if (is.null(script_path)) {
    # source() 以外（例: RStudio の実行）ではリポジトリルートを推定
    repo_root <- normalizePath(getwd(), winslash = "/")
  } else {
    repo_root <- normalizePath(file.path(dirname(script_path), "..", ".."),
                               winslash = "/")
  }
  assign(".data_paths_registry_file",
         file.path(repo_root, "docs", "data", "data-paths.json"),
         envir = globalenv())
})

.data_paths_registry <- function() {
  if (!requireNamespace("jsonlite", quietly = TRUE)) {
    # ホスト R ではユーザーライブラリが .libPaths に載らないことがある
    user_lib <- Sys.getenv("R_LIBS_USER")
    if (nzchar(user_lib) && dir.exists(user_lib)) {
      .libPaths(c(user_lib, .libPaths()))
    }
  }
  if (!requireNamespace("jsonlite", quietly = TRUE)) {
    stop("jsonlite パッケージが必要です: install.packages('jsonlite')")
  }
  jsonlite::fromJSON(.data_paths_registry_file, simplifyVector = FALSE)
}

data_root <- function(name) {
  reg <- .data_paths_registry()
  spec <- reg$roots[[name]]
  if (is.null(spec)) stop("unknown root: ", name)
  override <- Sys.getenv(spec$env, unset = "")
  root <- if (nzchar(override)) override else spec$default
  path.expand(root)
}

data_path <- function(key, must_exist = TRUE) {
  reg <- .data_paths_registry()
  entry <- reg$entries[[key]]
  if (is.null(entry)) {
    stop("unknown data key: ", key,
         "（data_keys() で一覧を確認してください）")
  }
  p <- file.path(data_root(entry$root), entry$path)
  if (must_exist && !file.exists(p)) {
    stop(key, ": ", p, " が見つかりません。OneDrive 未同期または環境変数",
         reg$roots[[entry$root]]$env, " の設定を確認してください。")
  }
  p
}

data_keys <- function() {
  sort(names(.data_paths_registry()$entries))
}

data_describe <- function(key) {
  .data_paths_registry()$entries[[key]]$desc
}
