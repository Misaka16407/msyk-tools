#!/usr/bin/env python3
"""
OSS Plus - 美师优课图片替换 TUI

介绍：

是msykanswer1221.py中oss材料替换功能的增强脚本，由Young-Six-6拓展功能，Chatgpt 5.6重写成TUI脚本形式

功能：
1. 查看或替换学生已上传的答案图片（支持已经提交的作业）。
2. 查看或替换教师发布的作业材料/答案图片。

依赖：
    pip install requests rsa rich pillow alibabacloud-oss-v2
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import sys
import time
import webbrowser
from dataclasses import dataclass
from email.utils import formatdate
from getpass import getpass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table


BASE_URL = "https://padapp.msyk.cn"
CDN_BASE = "https://msyk.wpstatic.cn"
OSS_BUCKET = "msyk"
OSS_REGION = "cn-shanghai"
OSS_ENDPOINT = f"https://{OSS_BUCKET}.oss-{OSS_REGION}.aliyuncs.com"
MSYK_KEY = "DxlE8wwbZt8Y2ULQfgGywAgZfJl82G9S"
HEADERS = {"user-agent": "okhttp/3.12.1"}
IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
}
MSYK_SIGN_PUBKEY_B64 = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAj7YWxpOwulFyf+zQU77Y2cd9chZUMfiwokgUaigyeD"
    "8ac5E8LQpVHWzkm+1CuzH0GxTCWvAUVHWfefOEe4AThk4AbFBNCXqB+MqofroED6Uec1jrLGNcql9IWX3CN2J6"
    "mqJQ8QLB/xPg/7FUTmd8KtGPrtOrKKP64BM5cqaB1xCc4xmQTuWvtK9fRei6LVTHZyH0Ui7nP/TSF3PJV3ywMl"
    "kkQxKi8JBkz1fx1ZO5TVLYRKxzMQdeD6whq+kOsSXhlLIiC/Y8skdBJmsBWDMfQXxtMr5CyFbVMrG+lip/V5n2"
    "2EdigHcLOmFW9nnB+sgiifLHeXx951lcTmaGy4uChQIDAQAB"
)

console = Console()


@dataclass(frozen=True)
class Session:
    user_id: str
    unit_id: str
    real_name: str
    sign: str


@dataclass(frozen=True)
class ImageItem:
    category: str
    label: str
    url: str
    oss_key: str


@dataclass(frozen=True)
class PublicImageStatus:
    matches: bool
    size: int
    digest: str
    age: int | None
    cache_time: int | None
    cache_result: str

    @property
    def remaining_seconds(self) -> int | None:
        if self.age is None or self.cache_time is None:
            return None
        return max(self.cache_time - self.age, 0)


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def now_ms() -> int:
    return int(time.time() * 1000)


def rsa_decrypt_sign(server_sign_b64: str) -> str:
    """解密登录响应中的 sign，返回 token + userId。"""
    from rsa import PublicKey, core, transform

    public_der = base64.b64decode(MSYK_SIGN_PUBKEY_B64)
    public_key = PublicKey.load_pkcs1_openssl_der(public_der)
    cipher_bytes = base64.b64decode(server_sign_b64)
    plain_int = core.decrypt_int(
        transform.bytes2int(cipher_bytes), public_key.e, public_key.n
    )
    plain_bytes = transform.int2bytes(plain_int)
    plain_text = plain_bytes[plain_bytes.index(0) + 1 :].decode("utf-8")
    parts = plain_text.split(":")
    if len(parts) < 2:
        raise ValueError("登录 sign 的明文格式无效")
    return parts[1] + parts[0]


def post_signed(
    path: str,
    data: dict[str, Any],
    sign: str,
    timeout: int = 20,
) -> dict[str, Any]:
    """按字段名排序并拼接值，生成美师优课请求签名。"""
    salt = str(now_ms())
    payload = dict(data)
    values = "".join(
        str(payload[key] or "")
        for key in sorted(payload)
        if key not in {"sign", "key", "salt"}
    )
    payload.update(
        {
            "salt": salt,
            "sign": sign,
            "key": md5(values + salt + sign + MSYK_KEY),
        }
    )
    response = requests.post(
        BASE_URL + path,
        data=payload,
        headers=HEADERS,
        timeout=timeout,
    )
    response.raise_for_status()
    result = response.json()
    if str(result.get("code")) != "10000":
        message = result.get("message") or result.get("msg") or "接口返回失败"
        raise RuntimeError(f"{path}: code={result.get('code')}, {message}")
    return result


def login(username: str, password: str) -> Session:
    auth = md5(f"{username}{password}HHOO")
    response = requests.get(
        f"{BASE_URL}/ws/app/padLogin",
        params={"userName": username, "auth": auth},
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    result = response.json()
    if str(result.get("code")) != "10000":
        raise RuntimeError(result.get("message") or "用户名或密码错误")

    info = result.get("InfoMap") or {}
    encrypted_sign = result.get("sign") or result.get("serverSign")
    if not encrypted_sign:
        raise RuntimeError("登录响应缺少 sign")
    return Session(
        user_id=str(info.get("id", "")),
        unit_id=str(info.get("unitId", "")),
        real_name=str(info.get("realName") or username),
        sign=rsa_decrypt_sign(encrypted_sign),
    )


def normalize_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    url = value.strip()
    if url.lower() in {"--", "-", "null", "none", "undefined", "无"}:
        return ""
    if url.lower().startswith(("http://", "https://")):
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return CDN_BASE + url
    return f"{CDN_BASE}/{url}"


def oss_key_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return parsed.path.lstrip("/")
    return url.split("?", 1)[0].lstrip("/")


def looks_like_image(url: str) -> bool:
    suffix = Path(urlparse(url).path).suffix.lower()
    return not suffix or suffix in IMAGE_SUFFIXES


def add_item(
    target: list[ImageItem],
    category: str,
    label: str,
    raw_url: Any,
) -> None:
    url = normalize_url(raw_url)
    if not url or not looks_like_image(url):
        return
    key = oss_key_from_url(url)
    if key:
        target.append(ImageItem(category, label, url, key))


def first_value(mapping: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value:
            return value
    return ""


def question_map(resource_list: list[dict[str, Any]]) -> dict[str, tuple[Any, Any]]:
    result: dict[str, tuple[Any, Any]] = {}
    for resource in resource_list:
        resource_id = str(
            resource.get("resId") or resource.get("resourceId") or ""
        )
        if resource_id:
            result[resource_id] = (
                resource.get("orderNum", "?"),
                resource.get("questionType", 0),
            )
    return result


def question_label(
    prefix: str,
    item: dict[str, Any],
    q_map: dict[str, tuple[Any, Any]],
) -> str:
    resource_id = str(item.get("questionId") or item.get("resId") or "")
    order_num, question_type = q_map.get(
        resource_id,
        (item.get("orderNum", "?"), item.get("questionType", 0)),
    )
    type_name = {
        1: "单选",
        2: "多选",
        3: "主观",
        4: "填空",
        5: "判断",
        6: "改错",
    }.get(question_type, "")
    suffix = f" · {type_name}" if type_name else ""
    return f"{prefix} · 题{order_num}{suffix}"


def collect_student_images(
    homework: dict[str, Any],
    card: dict[str, Any],
    session: Session,
    homework_id: str,
) -> list[ImageItem]:
    """从多个可能的响应字段枚举学生答案图片。"""
    items: list[ImageItem] = []
    resources = homework.get("resourceList") or []
    q_map = question_map(resources)

    for entry in homework.get("studentHomeworkAnswers") or []:
        add_item(
            items,
            "学生答案",
            question_label("学生答案", entry, q_map),
            first_value(entry, ("pictureUrl", "url", "resourceUrl", "picUrl")),
        )

    for entry in homework.get("studentAnswerList") or []:
        bit_id = entry.get("bitmapId", entry.get("bitId", "-1"))
        add_item(
            items,
            "学生答案",
            f"{question_label('学生图片', entry, q_map)} · bit={bit_id}",
            first_value(entry, ("pictureUrl", "url", "resourceUrl", "picUrl")),
        )

    for resource in resources:
        order_num = resource.get("orderNum", "?")
        for entry in resource.get("upLoadPicList") or []:
            add_item(
                items,
                "学生答案",
                f"学生上传 · 题{order_num}",
                first_value(entry, ("url", "pictureUrl", "resourceUrl", "picUrl")),
            )

    for entry in card.get("homeworkCardList") or []:
        add_item(
            items,
            "学生答案",
            f"答题卡图片 · 题{entry.get('orderNum', entry.get('serialNumber', '?'))}",
            first_value(entry, ("pictureUrl", "url")),
        )

    # 当前作业响应没有携带图片时，逐题查询作为只读兜底。
    if not items:
        modify_num = str(homework.get("modifyNum", 0))
        for resource in resources:
            resource_id = str(
                resource.get("resId") or resource.get("resourceId") or ""
            )
            if not resource_id:
                continue
            try:
                answer = post_signed(
                    "/ws/student/homework/studentHomework/getHomeworkAnswer",
                    {
                        "homeworkId": homework_id,
                        "resourceId": resource_id,
                        "studentId": session.user_id,
                        "unitId": session.unit_id,
                        "modifyNum": modify_num,
                    },
                    session.sign,
                )
            except Exception:
                continue

            candidates: list[dict[str, Any]] = []
            for key in ("studentHomeworkAnswers", "studentAnswerList", "answerList"):
                value = answer.get(key)
                if isinstance(value, list):
                    candidates.extend(x for x in value if isinstance(x, dict))
            if not candidates:
                candidates = [answer]

            for entry in candidates:
                raw_urls = first_value(
                    entry,
                    ("pictureUrl", "url", "resourceUrl", "picUrl", "answer"),
                )
                if not isinstance(raw_urls, str):
                    continue
                for raw_url in raw_urls.split(","):
                    add_item(
                        items,
                        "学生答案",
                        f"逐题答案 · 题{resource.get('orderNum', '?')}",
                        raw_url,
                    )
    return deduplicate(items)


def collect_material_images(
    homework: dict[str, Any],
    card: dict[str, Any],
) -> list[ImageItem]:
    """枚举教师发布的作业材料、解析/答案图片。"""
    items: list[ImageItem] = []

    for entry in card.get("materialRelas") or []:
        add_item(
            items,
            "作业材料",
            f"材料 · {entry.get('title', '未命名')}",
            entry.get("resourceUrl"),
        )

    for entry in card.get("analysistList") or []:
        add_item(
            items,
            "作业答案",
            f"答案/解析 · {entry.get('title', '未命名')}",
            entry.get("resourceUrl"),
        )

    for entry in homework.get("resourceList") or []:
        add_item(
            items,
            "作业材料",
            f"题目资源 · 题{entry.get('orderNum', '?')} · "
            f"{entry.get('resTitle', entry.get('title', '未命名'))}",
            first_value(entry, ("resourceUrl", "url", "pictureUrl")),
        )
    return deduplicate(items)


def material_directory_prefixes(
    homework: dict[str, Any],
    card: dict[str, Any],
) -> list[str]:
    """从材料响应中提取目录，并兼顾 PDF 对应的 cut 派生图目录。"""
    raw_urls: list[Any] = []
    for entry in card.get("materialRelas") or []:
        raw_urls.append(entry.get("resourceUrl"))
    for entry in card.get("analysistList") or []:
        raw_urls.append(entry.get("resourceUrl"))
    for entry in homework.get("resourceList") or []:
        raw_urls.append(first_value(entry, ("resourceUrl", "url", "pictureUrl")))

    prefixes: set[str] = set()
    for raw_url in raw_urls:
        url = normalize_url(raw_url)
        if not url:
            continue
        key = oss_key_from_url(url)
        if "/" not in key:
            continue
        directory = key.rsplit("/", 1)[0] + "/"
        prefixes.add(directory)
        if "/cut/" in directory:
            prefixes.add(directory.split("/cut/", 1)[0] + "/")
        elif Path(key).suffix.lower() == ".pdf":
            prefixes.add(directory + "cut/")
    return sorted(prefixes)


def expand_material_directory_images(
    items: list[ImageItem],
    homework: dict[str, Any],
    card: dict[str, Any],
) -> list[ImageItem]:
    """列举相关材料目录，将其中的图片加入选择列表。"""
    import alibabacloud_oss_v2 as oss

    prefixes = material_directory_prefixes(homework, card)
    if not prefixes:
        return items

    client = make_oss_client(fetch_sts(use_signed=False))
    expanded = list(items)
    for prefix in prefixes:
        response = client.list_objects(
            oss.ListObjectsRequest(
                bucket=OSS_BUCKET,
                prefix=prefix,
                max_keys=1000,
            )
        )
        if response.status_code != 200:
            continue
        for obj in response.contents or []:
            key = obj.key
            if not key or Path(key).suffix.lower() not in IMAGE_SUFFIXES:
                continue
            expanded.append(
                ImageItem(
                    "目录图片",
                    f"目录文件 · {Path(key).name}",
                    f"{CDN_BASE}/{key}",
                    key,
                )
            )
    return deduplicate(expanded)


def deduplicate(items: list[ImageItem]) -> list[ImageItem]:
    seen: set[str] = set()
    result: list[ImageItem] = []
    for item in items:
        if item.oss_key not in seen:
            seen.add(item.oss_key)
            result.append(item)
    return result


def fetch_homework(
    session: Session,
    homework_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    homework = post_signed(
        "/ws/common/homework/homeworkStatus",
        {
            "homeworkId": homework_id,
            "modifyNum": "0",
            "userId": session.user_id,
            "unitId": session.unit_id,
        },
        session.sign,
    )
    try:
        card = post_signed(
            "/ws/teacher/homeworkCard/getHomeworkCardInfo",
            {
                "homeworkId": homework_id,
                "studentId": session.user_id,
                "modifyNum": "0",
                "unitId": session.unit_id,
            },
            session.sign,
        )
    except Exception as exc:
        console.print(f"[yellow]答题卡详情不可用：{exc}[/yellow]")
        card = {}
    return homework, card


def fetch_sts(use_signed: bool) -> dict[str, Any]:
    """按原脚本行为获取 STS：学生答案用签名模式，材料用 retry 模式。"""
    if use_signed:
        salt = str(now_ms())
        payload = {"salt": salt, "key": md5(salt + MSYK_KEY)}
    else:
        payload = {"retry": "0"}
    response = requests.post(
        f"{BASE_URL}/ws/common/uploadController/getParams",
        data=payload,
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    result = response.json()
    for field in ("AccessKeyId", "AccessKeySecret", "SecurityToken"):
        if not result.get(field):
            raise RuntimeError(f"STS 响应缺少 {field}")
    return result


def make_oss_client(sts: dict[str, Any]):
    import alibabacloud_oss_v2 as oss

    provider = oss.credentials.StaticCredentialsProvider(
        access_key_id=sts["AccessKeyId"],
        access_key_secret=sts["AccessKeySecret"],
        security_token=sts["SecurityToken"],
    )
    config = oss.config.load_default()
    config.credentials_provider = provider
    config.region = OSS_REGION
    config.connect_timeout = 30
    config.readwrite_timeout = 60
    return oss.Client(config)


def verify_local_image(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在：{path}")
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError(f"不支持的图片扩展名：{path.suffix or '无扩展名'}")
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.verify()
    except ImportError:
        pass
    except Exception as exc:
        raise ValueError(f"图片校验失败：{exc}") from exc


def replace_at_same_key(item: ImageItem, local_path: Path) -> tuple[int, str]:
    """替换图片并重新读取源站内容，确认上传结果与本地文件一致。"""
    import alibabacloud_oss_v2 as oss

    verify_local_image(local_path)
    # 使用不同的 STS 获取方式
    sts = fetch_sts(use_signed=item.category == "学生答案")
    client = make_oss_client(sts)

    delete_result = client.delete_object(
        oss.DeleteObjectRequest(bucket=OSS_BUCKET, key=item.oss_key)
    )
    if delete_result.status_code not in (200, 204):
        raise RuntimeError(
            f"删除失败：HTTP {delete_result.status_code}, "
            f"request_id={delete_result.request_id}"
        )

    total = local_path.stat().st_size
    with local_path.open("rb") as stream:
        with Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("上传到原 OSS Key", total=total)

            def update_progress(_increment: int, written: int, _total: int) -> None:
                progress.update(task_id, completed=written)

            upload_result = client.put_object(
                oss.PutObjectRequest(
                    bucket=OSS_BUCKET,
                    key=item.oss_key,
                    body=stream,
                    progress_fn=update_progress,
                    cache_control="no-cache, no-store, must-revalidate",
                    expires=formatdate(0, usegmt=True),
                    content_type=mimetypes.guess_type(local_path.name)[0]
                    or "application/octet-stream",
                )
            )

    if upload_result.status_code != 200:
        raise RuntimeError(
            "原对象已删除，但上传失败："
            f"HTTP {upload_result.status_code}, request_id={upload_result.request_id}"
        )

    local_digest = hashlib.sha256(local_path.read_bytes()).hexdigest()
    verify_result = client.get_object(
        oss.GetObjectRequest(bucket=OSS_BUCKET, key=item.oss_key)
    )
    if verify_result.status_code != 200:
        raise RuntimeError(f"上传后读取校验失败：HTTP {verify_result.status_code}")
    remote_bytes = verify_result.body.read()
    remote_digest = hashlib.sha256(remote_bytes).hexdigest()
    if remote_digest != local_digest:
        raise RuntimeError("上传后校验不一致，源站内容不是所选本地图片")
    return len(remote_bytes), remote_digest


def check_public_image(item: ImageItem, expected_digest: str) -> PublicImageStatus:
    """检查 App 使用的公开图片地址当前返回的是新图还是缓存图。"""
    response = requests.get(item.url, timeout=30)
    response.raise_for_status()
    digest = hashlib.sha256(response.content).hexdigest()

    def header_int(name: str) -> int | None:
        value = response.headers.get(name)
        try:
            return int(value) if value is not None else None
        except ValueError:
            return None

    return PublicImageStatus(
        matches=digest == expected_digest,
        size=len(response.content),
        digest=digest,
        age=header_int("Age"),
        cache_time=header_int("X-Swift-CacheTime"),
        cache_result=response.headers.get("X-Cache", ""),
    )


def wait_for_public_refresh(
    item: ImageItem,
    expected_digest: str,
    wait_seconds: int,
) -> bool:
    """短时间轮询公开地址，直到缓存刷新或到达等待上限。"""
    deadline = time.monotonic() + wait_seconds
    with console.status("[cyan]正在等待公开图片缓存刷新...[/cyan]") as status:
        while True:
            try:
                current = check_public_image(item, expected_digest)
                if current.matches:
                    return True
                remaining = max(int(deadline - time.monotonic()), 0)
                status.update(f"[cyan]正在等待公开图片缓存刷新，剩余 {remaining} 秒...[/cyan]")
            except requests.RequestException:
                pass
            if time.monotonic() >= deadline:
                return False
            time.sleep(min(5, max(deadline - time.monotonic(), 0)))


def render_items(items: list[ImageItem], title: str) -> None:
    table = Table(title=title, box=box.ROUNDED, header_style="bold cyan")
    table.add_column("#", justify="right", style="bold yellow", width=4)
    table.add_column("类型", style="magenta", no_wrap=True)
    table.add_column("说明", style="white")
    table.add_column("文件路径", style="green", overflow="fold")
    for index, item in enumerate(items, 1):
        table.add_row(str(index), item.category, item.label, item.oss_key)
    console.print(table)


def download_image(item: ImageItem) -> None:
    folder = Path.cwd() / "oss_plus_downloads"
    folder.mkdir(exist_ok=True)
    filename = Path(urlparse(item.url).path).name or f"image_{now_ms()}.jpg"
    destination = folder / filename
    response = requests.get(item.url, stream=True, timeout=60)
    response.raise_for_status()
    with destination.open("wb") as stream:
        for chunk in response.iter_content(1024 * 128):
            stream.write(chunk)
    console.print(f"[green]已下载：{destination.resolve()}[/green]")


def item_menu(items: list[ImageItem], title: str) -> None:
    while True:
        console.clear()
        render_items(items, title)
        console.print(
            Panel.fit(
                "[bold]R[/bold] 替换图片   "
                "[bold]O[/bold] 浏览器打开   "
                "[bold]D[/bold] 下载   "
                "[bold]B[/bold] 返回",
                border_style="blue",
            )
        )
        action = Prompt.ask("操作", choices=["R", "O", "D", "B"], default="R").upper()
        if action == "B":
            return

        number = IntPrompt.ask("图片编号")
        if number < 1 or number > len(items):
            console.print("[red]编号超出范围[/red]")
            Prompt.ask("按回车继续", default="")
            continue
        item = items[number - 1]

        if action == "O":
            separator = "&" if "?" in item.url else "?"
            webbrowser.open(f"{item.url}{separator}ossplus_refresh={now_ms()}")
            continue
        if action == "D":
            try:
                download_image(item)
            except Exception as exc:
                console.print(f"[red]下载失败：{exc}[/red]")
            Prompt.ask("按回车继续", default="")
            continue

        local_value = Prompt.ask("本地替换图片路径").strip().strip('"')
        local_path = Path(os.path.expandvars(os.path.expanduser(local_value))).resolve()
        console.print(
            Panel(
                f"[yellow]目标：[/yellow]{item.label}\n"
                f"[yellow]远程路径：[/yellow]{item.oss_key}\n"
                f"[yellow]本地图片：[/yellow]{local_path}\n\n"
                "[bold red]将替换远程图片，请确认所选文件正确。[/bold red]",
                title="替换确认",
                border_style="red",
            )
        )
        if not Confirm.ask("确认替换", default=False):
            continue
        try:
            size, digest = replace_at_same_key(item, local_path)
            console.print(
                f"[bold green]替换成功，源站校验通过（{size} 字节，"
                f"SHA256 {digest[:12]}…）。[/bold green]"
            )
            try:
                public_status = check_public_image(item, digest)
            except Exception as exc:
                console.print(f"[yellow]公开图片地址暂时无法复查：{exc}[/yellow]")
            else:
                if public_status.matches:
                    console.print("[bold green]公开图片地址也已刷新。[/bold green]")
                else:
                    remaining = public_status.remaining_seconds
                    remaining_text = (
                        f"，预计还需约 {remaining} 秒"
                        if remaining is not None
                        else ""
                    )
                    console.print(
                        f"[yellow]公开图片地址目前仍返回缓存图"
                        f"（{public_status.size} 字节，"
                        f"{public_status.cache_result or '缓存状态未知'}）"
                        f"{remaining_text}。[/yellow]"
                    )
                    if (
                        remaining is not None
                        and 0 < remaining <= 180
                        and Confirm.ask("是否等待并自动复查", default=True)
                    ):
                        refreshed = wait_for_public_refresh(
                            item,
                            digest,
                            min(remaining + 30, 210),
                        )
                        if refreshed:
                            console.print(
                                "[bold green]公开图片缓存已经刷新，请重新打开 App 查看。[/bold green]"
                            )
                        else:
                            console.print(
                                "[yellow]等待结束后仍是缓存图，请稍后重试或清理 App 图片缓存。[/yellow]"
                            )
            if item.category in {"作业材料", "作业答案", "目录图片"}:
                console.print(
                    "[dim]材料图片可能由 PDF 生成；若公开图片已刷新而 App 仍未变化，"
                    "请重启 App 或清理其图片缓存。[/dim]"
                )
        except Exception as exc:
            console.print(f"[bold red]替换失败：{exc}[/bold red]")
        Prompt.ask("按回车继续", default="")


def homework_tui(session: Session) -> None:
    while True:
        console.clear()
        console.print(
            Panel.fit(
                f"[bold cyan]OSS Plus[/bold cyan]\n"
                f"当前用户：[green]{session.real_name}[/green] "
                f"(ID: {session.user_id})",
                border_style="cyan",
            )
        )
        homework_id = Prompt.ask("作业 ID（输入 Q 退出）").strip()
        if homework_id.upper() == "Q":
            return
        if not homework_id.isdigit():
            console.print("[red]作业 ID 必须是数字[/red]")
            time.sleep(1)
            continue

        try:
            with console.status("[cyan]正在读取作业与附件信息...[/cyan]"):
                homework, card = fetch_homework(session, homework_id)
        except Exception as exc:
            console.print(f"[red]获取作业失败：{exc}[/red]")
            Prompt.ask("按回车继续", default="")
            continue

        while True:
            console.clear()
            homework_name = (
                homework.get("homeworkName")
                or card.get("homeworkName")
                or f"作业 {homework_id}"
            )
            console.print(
                Panel.fit(
                    f"[bold]{homework_name}[/bold]\n作业 ID：{homework_id}",
                    border_style="cyan",
                )
            )
            console.print("[bold cyan]1[/bold cyan] 学生答案图片")
            console.print("[bold cyan]2[/bold cyan] 作业材料/答案图片")
            console.print("[bold cyan]3[/bold cyan] 刷新作业数据")
            console.print("[bold cyan]B[/bold cyan] 返回输入其他作业")
            mode = Prompt.ask("选择", choices=["1", "2", "3", "B"], default="1").upper()
            if mode == "B":
                break
            if mode == "3":
                try:
                    with console.status("[cyan]正在刷新...[/cyan]"):
                        homework, card = fetch_homework(session, homework_id)
                except Exception as exc:
                    console.print(f"[red]刷新失败：{exc}[/red]")
                    Prompt.ask("按回车继续", default="")
                continue

            if mode == "1":
                with console.status("[cyan]正在枚举学生答案图片...[/cyan]"):
                    items = collect_student_images(
                        homework, card, session, homework_id
                    )
                title = "学生答案图片"
            else:
                with console.status("[cyan]正在枚举材料目录图片...[/cyan]"):
                    items = collect_material_images(homework, card)
                    items = expand_material_directory_images(
                        items, homework, card
                    )
                title = "作业材料/答案图片"

            if not items:
                console.print(f"[yellow]未发现{title}。[/yellow]")
                Prompt.ask("按回车继续", default="")
                continue
            item_menu(items, title)


def main() -> int:
    console.clear()
    console.print(
        Panel(
            "[bold cyan]美师优课 OSS Plus[/bold cyan]\n"
            "学生答案图片 + 作业材料图片替换工具",
            border_style="cyan",
        )
    )
    username = Prompt.ask("用户名").strip()
    password = getpass("密码: ")
    if not username or not password:
        console.print("[red]用户名和密码不能为空[/red]")
        return 1

    try:
        with console.status("[cyan]正在登录...[/cyan]"):
            session = login(username, password)
    except Exception as exc:
        console.print(f"[bold red]登录失败：{exc}[/bold red]")
        return 1

    console.print(f"[green]登录成功：{session.real_name}[/green]")
    time.sleep(0.8)
    homework_tui(session)
    console.print("[green]已退出 OSS Plus。[/green]")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]操作已取消。[/yellow]")
        raise SystemExit(130)
