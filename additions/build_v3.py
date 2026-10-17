#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建 msyk_answer_v3.html：把 PDF.js v3 UMD + worker + cmaps + 标准字体全部内联进单文件。

首次运行会自动从 npm registry 下载 pdfjs-dist 并解压到 .build
"""
import base64
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PDFJS_VERSION = "3.11.174"
PDFJS_ROOT = os.path.join(HERE, ".build", "pdfjs")
PDFJS = os.path.join(PDFJS_ROOT, "package")
TEMPLATE = os.path.join(HERE, "v3_template.html")
OUTPUT = os.path.join(HERE, "msyk_answer_v3.html")
TGZ_URL = "https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-%s.tgz" % PDFJS_VERSION


def ensure_pdfjs():
    """确保 .build/pdfjs/package 存在，否则自动下载并解压。"""
    if os.path.isdir(os.path.join(PDFJS, "build")):
        return
    os.makedirs(PDFJS_ROOT, exist_ok=True)
    tgz = os.path.join(PDFJS_ROOT, "pdfjs-dist-%s.tgz" % PDFJS_VERSION)
    if not os.path.exists(tgz):
        import urllib.request
        print("下载 pdfjs-dist %s ..." % PDFJS_VERSION)
        urllib.request.urlretrieve(TGZ_URL, tgz)
    import tarfile
    print("解压 pdfjs-dist ...")
    with tarfile.open(tgz, "r:gz") as t:
        try:
            t.extractall(PDFJS_ROOT, filter="data")
        except TypeError:
            t.extractall(PDFJS_ROOT)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def b64_of(path):
    return base64.b64encode(read_bytes(path)).decode("ascii")


def main():
    ensure_pdfjs()

    # 1) PDF.js 主库（UMD）
    pdf_min = read_bytes(os.path.join(PDFJS, "build", "pdf.min.js")).decode("utf-8")
    if "</script" in pdf_min.lower():
        raise SystemExit("pdf.min.js 含有 </script，不能直接内联")

    # 2) worker（base64，运行时转 Blob）
    worker_b64 = b64_of(os.path.join(PDFJS, "build", "pdf.worker.min.js"))

    # 3) cmaps（全部，含中文 GB/CNS 族）
    cmap_dir = os.path.join(PDFJS, "cmaps")
    cmaps = {}
    for fn in sorted(os.listdir(cmap_dir)):
        if fn.endswith(".bcmap"):
            cmaps[fn] = b64_of(os.path.join(cmap_dir, fn))

    # 4) 标准字体（可选，提升标准 14 字体渲染质量）
    stdfonts = {}
    sf_dir = os.path.join(PDFJS, "standard_fonts")
    if os.path.isdir(sf_dir):
        for fn in sorted(os.listdir(sf_dir)):
            if fn.endswith(".pfb"):
                stdfonts[fn] = b64_of(os.path.join(sf_dir, fn))

    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()

    # 占位符替换
    html = html.replace("/*__PDFJS_LIB__*/", pdf_min)
    html = html.replace("__PDF_WORKER_B64__", worker_b64)
    html = html.replace("/*__PDF_CMAPS__*/", json.dumps(cmaps, separators=(",", ":")))
    html = html.replace("/*__PDF_STDFONTS__*/", json.dumps(stdfonts, separators=(",", ":")))

    for token in ("/*__PDFJS_LIB__*/", "__PDF_WORKER_B64__", "/*__PDF_CMAPS__*/", "/*__PDF_STDFONTS__*/"):
        if token in html:
            raise SystemExit("占位符未替换: " + token)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print("OK ->", OUTPUT)
    print("  pdf.min.js        : %.1f KB" % (len(pdf_min) / 1024))
    print("  worker(b64)       : %.1f KB" % (len(worker_b64) / 1024))
    print("  cmaps             : %d 个, %.1f KB(b64)" % (len(cmaps), sum(len(v) for v in cmaps.values()) / 1024))
    print("  standard fonts    : %d 个, %.1f KB(b64)" % (len(stdfonts), sum(len(v) for v in stdfonts.values()) / 1024))
    print("  输出总大小        : %.2f MB" % (os.path.getsize(OUTPUT) / 1024 / 1024))


if __name__ == "__main__":
    main()
