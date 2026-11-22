# EverSpark Forge Plugins

[EverSpark Forge](https://github.com/jhinforge/EverSpark-Forge) 的独立插件仓库。插件计划通过 GitHub Releases 单独分发，用户可按需在 EverSpark Forge 客户端中下载。

## 插件

| 插件 | 用途 | 状态 |
| --- | --- | --- |
| LoRA 模型管理面板 | 将现有的 Obsidian LoRA 模型管理面板移植到 EverSpark Forge 客户端，用于浏览和管理 LoRA 模型。 | 计划中 |

## LoRA 脚本目录配置

复制 [lora-config.example.json](lora-config.example.json) 为 `lora-config.json`，填写四个目录。支持绝对路径，或相对于配置文件的路径。也可以用环境变量 `LORA_PLUGIN_CONFIG` 指定配置文件位置。

| 配置项 | 放什么 |
| --- | --- |
| `notes_dir` | 按分类存放 LoRA Markdown 笔记 |
| `previews_dir` | 正式归档的原预览图 |
| `thumbnails_dir` | 面板使用的 JPEG 缩略图缓存 |
| `temp_dir` | 待录入 JSON、`previews/` 下待审核的图片、`staging/` 下的入库暂存文件和 `models/` 下暂存的权重 |

接入已有 Obsidian 库时，可指定 `vault_root` 并让前三项指向原目录。库内笔记继续使用 Vault 相对路径计算缓存文件名，库内原图继续使用 Obsidian 图片链接。独立目录可以省略 `vault_root`，新笔记使用普通 Markdown 图片链接。历史 Obsidian 面板仍按自己的 Vault 和面板内的缓存目录设置读取数据。

手动录入时，把本次要归档的图片放入配置中 `temp_dir` 的 `previews/` 子目录。录入成功后会清理这批临时图片。手动录入、Civitai 录入、全量缩略图重建和 Pod 清单导出及重置共用这套配置。未创建配置时，这些脚本继续使用原来的 Windows 路径。

## 在客户端录入 LoRA

更新客户端源码和 LoRA 插件后，点面板右上角的「录入 LoRA」。可以手动填写并选择本地预览图，也可以从 Civitai 抓取资料、选择预览图再入库。Civitai 使用面板设置里保存的 API Key。已配置的笔记、原图、缩略图和临时目录会直接用于入库。
