#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""把两个自包含 HTML 合并成一个单向、按次数切换的独立 HTML。"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__TITLE__</title>
    <style>
        * { box-sizing: border-box; }
        html, body { margin: 0; min-height: 100%; background: #fff; }
        #page-host { width: 100%; min-height: 100vh; }
        #page-host iframe {
            display: block;
            width: 100%;
            height: calc(100vh - 34px);
            min-height: 480px;
            border: 0;
            background: #fff;
        }
        #switch-bar {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 34px;
            background: #fff;
        }
        #switch-button {
            min-width: 54px;
            height: 24px;
            padding: 0 10px;
            border: 1px solid #d1d5db;
            border-radius: 999px;
            color: #64748b;
            background: #f8fafc;
            font: 12px/1 system-ui, sans-serif;
            cursor: pointer;
        }
        #switch-button:hover { color: #334155; background: #f1f5f9; }
        #switch-button:active { transform: translateY(1px); }
        #switch-button:focus-visible { outline: 2px solid #3b82f6; outline-offset: 2px; }
        .mode-dot #page-host iframe,
        .mode-blind #page-host iframe { height: 100vh; }
        .mode-dot #switch-bar,
        .mode-blind #switch-bar {
            position: fixed;
            left: 50%;
            bottom: 6px;
            z-index: 2147483647;
            width: 40px;
            height: 40px;
            transform: translateX(-50%);
            background: transparent;
        }
        .mode-dot #switch-button,
        .mode-blind #switch-button {
            min-width: 0;
            padding: 0;
            border: 0;
            color: transparent;
            font-size: 0;
            outline: 0;
            box-shadow: none;
        }
        .mode-dot #switch-button {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #000;
        }
        .mode-blind #switch-button {
            width: 40px;
            height: 40px;
            background: transparent;
            opacity: 0;
        }
        .mode-dot #switch-button:hover,
        .mode-dot #switch-button:active { background: #000; transform: none; }
        .mode-blind #switch-button:hover,
        .mode-blind #switch-button:active { background: transparent; transform: none; }
        @media (max-width: 640px) {
            #page-host iframe { min-height: 360px; }
        }
    </style>
</head>
<body class="mode-__SECRET_MODE__">
    <main id="page-host">
        <iframe id="original-page" title="原版页面"
                sandbox="allow-scripts allow-forms allow-modals allow-popups allow-downloads"></iframe>
        <div id="switch-bar">
            <button id="switch-button" type="button" __SECRET_TABINDEX__ aria-label="切换到新版页面">__BUTTON_TEXT__</button>
        </div>
    </main>

    <script>
        (() => {
            "use strict";

            const requiredClicks = __CLICK_COUNT__;
            const originalData = "__ORIGINAL_B64__";
            const injectedData = "__INJECTED_B64__";
            const host = document.getElementById("page-host");
            const originalFrame = document.getElementById("original-page");
            const button = document.getElementById("switch-button");
            let clickCount = 0;
            let switched = false;

            function decodeUtf8Base64(encoded) {
                const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
                return new TextDecoder("utf-8").decode(bytes);
            }

            // 加载原版
            originalFrame.srcdoc = decodeUtf8Base64(originalData);

            button.addEventListener("click", () => {
                if (switched) return;
                clickCount += 1;
                if (clickCount < requiredClicks) return;

                switched = true;
                const injectedFrame = document.createElement("iframe");
                injectedFrame.title = "新版页面";
                injectedFrame.setAttribute(
                    "sandbox",
                    "allow-scripts allow-forms allow-modals allow-popups allow-downloads"
                );
                injectedFrame.style.height = "100vh";
                injectedFrame.style.minHeight = "100vh";
                injectedFrame.srcdoc = decodeUtf8Base64(injectedData);

                // 替换整个原版区域
                host.replaceChildren(injectedFrame);
            });
        })();
    </script>
</body>
</html>
"""


def positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是整数") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("必须大于或等于 1")
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把两个已内嵌 CSS、JS、图片等资源的 HTML 合并为一个独立 HTML。"
    )
    parser.add_argument("original", type=Path, help="自包含的原版 HTML")
    parser.add_argument("injected", type=Path, help="自包含的新版 HTML")
    parser.add_argument("output", type=Path, help="输出 HTML")
    parser.add_argument(
        "-n",
        "--clicks",
        type=positive_integer,
        default=5,
        help="切换到新版所需的点击次数，默认 5",
    )
    parser.add_argument(
        "--secret",
        choices=("button", "dot", "blind"),
        default="button",
        metavar="MODE",
        help="触发器模式：button=普通按钮，dot=小黑点，blind=完全不可见盲点；默认 button",
    )
    parser.add_argument("--title", default="独立双页面", help="输出页面标题")
    return parser.parse_args()


def read_html(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在或不是普通文件：{path}")
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"文件不是有效的 UTF-8 文本：{path}") from exc


def encode_html(document: str) -> str:
    return base64.b64encode(document.encode("utf-8")).decode("ascii")


def escape_title(title: str) -> str:
    return (
        title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def main() -> int:
    args = parse_args()
    try:
        original = read_html(args.original)
        injected = read_html(args.injected)
        is_secret = args.secret in {"dot", "blind"}

        result = (
            TEMPLATE.replace("__ORIGINAL_B64__", encode_html(original))
            .replace("__INJECTED_B64__", encode_html(injected))
            .replace("__CLICK_COUNT__", str(args.clicks))
            .replace("__SECRET_MODE__", args.secret)
            .replace("__SECRET_TABINDEX__", 'tabindex="-1"' if is_secret else "")
            .replace("__BUTTON_TEXT__", "" if is_secret else "切换")
            .replace("__TITLE__", escape_title(args.title))
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="\n") as output_file:
            output_file.write(result)
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"生成完成：{args.output.resolve()}")
    print(f"原版页面：{args.original.resolve()}")
    print(f"新版页面：{args.injected.resolve()}")
    trigger_names = {"button": "普通按钮", "dot": "底部中央小黑点", "blind": "底部中央透明盲点"}
    print(f"切换条件：点击{trigger_names[args.secret]} {args.clicks} 次")
    print(f"触发器模式：{args.secret}")
    print("切换后原版和按钮会被移除，页面不提供返回逻辑。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
