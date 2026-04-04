# .github/dependabot.yml
# Ditto 依赖自动更新配置

version: 2

updates:
  # ==========================================================
  # GitHub Actions
  # ==========================================================
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "Asia/Shanghai"
    open-pull-requests-limit: 3
    groups:
      github-actions:
        patterns:
          - "*"
    labels:
      - "dependencies"
      - "ci"
    commit-message:
      prefix: "ci(deps)"

  # ==========================================================
  # Python (pip ecosystem - Dependabot 会读取 pyproject.toml)
  # ==========================================================
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "Asia/Shanghai"
    open-pull-requests-limit: 5

    groups:
      # 开发工具依赖（低风险，可自动合并）
      dev-tools:
        patterns:
          - "ruff"
          - "pyright"
          - "pytest*"
          - "coverage*"
          - "pre-commit"
        update-types:
          - "minor"
          - "patch"

      # 类型存根
      type-stubs:
        patterns:
          - "types-*"

      # 可观测性相关
      observability:
        patterns:
          - "opentelemetry*"
          - "loguru"

    # 忽略主版本更新（需手动评估）
    ignore:
      - dependency-name: "*"
        update-types: ["version-update:semver-major"]
      # Polars 主版本更新可能有 breaking changes
      - dependency-name: "polars"
        update-types: ["version-update:semver-major"]

    labels:
      - "dependencies"
      - "python"

    commit-message:
      prefix: "deps(python)"

  # ==========================================================
  # Docker
  # ==========================================================
  - package-ecosystem: "docker"
    directory: "/deploy"
    schedule:
      interval: "monthly"
    labels:
      - "dependencies"
      - "docker"
    commit-message:
      prefix: "deps(docker)"
