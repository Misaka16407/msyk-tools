# MSYK-Additions

在这里，存放了一些**附加实用脚本**，这与仓库其他脚本无太大关联，但是部分用户可能会用得到

## merge_pages.py

用途：页里藏页，把两个页面合并成一个html文件，在点击按钮之后把页面刷新成隐藏页面，两个html文件需要预处理自包含资源。

使用方法：命令行使用，脚本自带帮助，可选“按钮，黑点，盲点”切换，可以修改点击次数，使用的时候多次点击即可切换页面

## msyk_answer.html

用途：纯html版本的简易答案获取工具，可以配合上述合并脚本。

使用方法：打开即用，可以配合上述合并脚本

## msyk_answer_v2.html

用途：msyk_answer.html的加强版，增加了扫描作业功能，材料从新标签页打开换成当页打开

使用方法：打开即用，可以配合上述合并脚本

## msyk_answer_v3.html

用途：msyk_answer_v2.html的加强版，作业材料/答案/资源文件改为在本页内嵌打开（PDF 使用 PDF.js 渲染）；扫描器新增并发加速和停止按钮，单次扫描上限 500

使用方法：打开即用，可以配合上述合并脚本；PDF.js 内联

## build_v3.py

用途：msyk_answer_v3.html 的构建脚本，把 PDF.js 全部内联，生成单个 HTML 文件

使用方法：运行 python3 build_v3.py，会读取同目录的 v3_template.html 生成 msyk_answer_v3.html；首次运行会自动下载并解压 pdfjs-dist 到 .build/

## v3_template.html

用途：msyk_answer_v3.html 的模板，包含页面结构、样式和全部前端逻辑，由 build_v3.py 注入 PDF.js 等资源后生成最终文件

使用方法：修改 v3 功能请编辑此模板，再运行 build_v3.py 重新生成 msyk_answer_v3.html
