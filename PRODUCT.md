# Product

<!-- uizze:product-schema 1 -->

## Platform

web

## Users

基于现有代码推断：在本机同时使用多个 AI Agent 的开发者，需要查看本地安装的 Skills，并判断它们是否启用、来自哪里、部署到哪些 Agent。

## Product Purpose

基于现有代码推断：SkillBridge 是一个 local-first 的 AI Skills 控制中心，扫描本机 Agent 与 Skills，将分散在不同目录的能力聚合为可搜索、可查看、可管理和可安全同步的工作台。成功意味着用户能快速知道环境状态、找到一个 Skill、理解其来源与文件组成，并在同步前看到预检结果。

## Positioning

基于现有代码推断：它不是远程 Marketplace，而是本地文件系统上的可追溯控制层；扫描结果、路径、哈希、Agent 部署状态和同步历史来自本机实际数据。

## Operating Context

用户在本机开发环境中运行 Dashboard。系统扫描 Codex、Claude Code、Hermes、DeepSeek Harness 等 Agent，展示 Skill 目录与安装状态，并通过本地 API 执行打开文件、启用/禁用、移除、导入 Library、预检和安全同步。

## Capabilities and Constraints

- 保留现有 Dashboard、Skills、Skill Detail、Library、Library Skill Detail、Sync History 路由。
- 保留现有 API、数据加载、i18n、同步预检、批量同步和安全操作行为。
- 本地服务只绑定 `127.0.0.1`，前端由 `ui/dist` 提供。
- 不把空的 Library、未安装 Agent 或无历史记录伪装成成功数据；空状态要说明下一步。
- Marketplace / remote library / advanced conflict resolution 仍未实现。

## Brand Commitments

SkillBridge 这个名称与现有 SB 标识是已存在的产品识别元素。语言继续支持简体中文与 English。

## Evidence on Hand

- `README.md`：产品能力、API 和已实现阶段。
- `ui/src/`：真实路由、组件、i18n 与状态边界。
- 本机运行数据：当前可发现 4 个已安装 Agent、48 个 Skills，Library 当前为空。

## Product Principles

1. Local truth over invented status.
2. Understand before mutating.
3. Safe sync is a visible workflow, not a hidden button.
4. Dense enough for daily scanning, calm enough for confident decisions.

## Accessibility & Inclusion

基于现有实现推断：保留语义按钮、键盘可达焦点、状态不只依赖颜色、响应式布局，以及加载、空、错误和禁用状态。
