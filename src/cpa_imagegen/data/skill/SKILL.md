---
name: cpa-imagegen
description: Generate or edit raster images through the user's configured CPA gateway. Use for image generation, illustrations, product photos, posters, website imagery, or changes to existing images, including Chinese requests such as 生图、画图、生成图片、改图. Prefer native vector editing for existing SVG assets.
---

# CPA Imagegen

Use the independent `cpa-imagegen` CLI for this skill. It uses an explicitly configured gateway, not Codex's built-in image tool. This skill is the user's selected CPA/API workflow.

## Runtime

Use the following command prefix in {{SHELL}}. It is bound to the Python environment that installed this skill; retain that environment.

```text
{{CLI_COMMAND}}
```

Run the prefix with `--help` for the command list, or append `generate --help` / `edit --help` for parameters. If the interpreter or package is missing, report the installation problem; do not substitute a different service.

## Workflow

1. Choose `generate` for a new image or `edit` for changes/references. Inspect existing input images before editing. State the changes and elements to preserve in the prompt.
2. Keep the user's intended content and exact requested text. Add composition or style details only when useful. Use `--prompt-file` with a UTF-8 file for complex text to avoid shell quoting problems.
3. Choose a descriptive, unused `.png` path under the current project's `output/imagegen/`, or use the user's destination. Use `--out` explicitly. Do not overwrite an existing image unless the user asks.
4. Use `--json` to obtain the absolute saved path and metadata. For edits, pass each local input using a repeated `--image` argument.
5. Run the request once. Image requests can take several minutes; wait for the running process instead of launching it again. On timeout, completion is unknown. Report errors and do not automatically retry, change models, or switch services.
6. Inspect the saved result with the host's image-view tool, then display it using an absolute path and give the saved path. Judge subject, requested text and preserved details; do not silently generate more variants.

Example arguments to append to the runtime prefix:

```text
generate --prompt "A matte ceramic mug in soft daylight, no text" --out "output/imagegen/mug.png" --json
edit --image "output/imagegen/mug.png" --prompt "Change only the mug to green; preserve the background, framing and lighting" --out "output/imagegen/mug-green.png" --json
```

Defaults: `gpt-image-2`, 1024x1024, medium quality, one PNG. Honor user-specified model, size and quality; other compatible models are not guaranteed to work. Do not infer supported image parameters from the text model used by the agent.

## Exact output dimensions

The gateway can return different dimensions despite `--size`. Check `size_matches_request` and report any mismatch. Preserve the upstream original; do not repeat generation to chase dimensions.

For exact delivery dimensions, use the independent local `resize` command after generation or on an existing image. It needs no gateway configuration and makes no API call:

```text
resize --image "output/imagegen/mug.png" --size 1024x1024 --mode pad --out "output/imagegen/mug-padded.png" --json
```

Use `pad` to preserve the full composition with transparent borders. Use `crop` when the user requests a filled canvas and permits loss of edges; it crops from the center. Both scale proportionally. Choose a separate output path, inspect the adjusted image, and identify it as locally processed. A requested generation size alone does not authorize cropping. If exact file dimensions are required without an explicit crop preference, use padding and disclose the transparent border. Do not describe a processed image as natively generated at that size.

## Configuration and diagnostics

Use `doctor --json` for a connection/model-list check; it does not verify image generation. `--dry-run` on generate/edit validates local inputs and reports a request without contacting the gateway. Dry-run output includes the prompt, so treat it as potentially private.

When configuration is absent, explain the two choices: set `CPA_IMAGEGEN_BASE_URL` and `CPA_IMAGEGEN_API_KEY` locally, or explicitly run `config import-codex` if the user wants to reuse a Codex provider. Never ask the user to paste a key into chat, print private configuration, or add secrets to the project. The CLI does not read Codex credentials during normal generation.
