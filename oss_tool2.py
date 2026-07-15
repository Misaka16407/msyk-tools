import os
import time
import requests
import alibabacloud_oss_v2 as oss
from typing import Dict, Any, List, Optional
from datetime import datetime
from colorama import init, Fore, Back, Style
# from rich.progress import track
from rich.progress import Progress, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
# from colorama import Fore

# ---------- STS 助手 ----------
STS_URL = "https://padapp.msyk.cn/ws/common/uploadController/getParams"

def fetch_sts() -> Dict[str, Any]:
    rsp = requests.post(STS_URL, data={"retry": 0}, timeout=10)
    rsp.raise_for_status()
    data = rsp.json()
    for k in ("AccessKeyId", "AccessKeySecret", "SecurityToken", "Expiration"):
        if k not in data:
            raise KeyError(f"STS 接口缺失字段 {k}")
    return data


# ---------- OSS 工具 ----------
class OSSTool:
    def __init__(
        self,
        region: str,
        bucket: str,
        proxy: Optional[str] = None,
        timeout: int = 30,
    ):
        self.region = region
        self.bucket = bucket
        self.proxy = proxy
        self.timeout = timeout
        self._sts_expires: float = 0
        self._client: Optional[oss.Client] = None
        self._refresh_client()

    # ------------- 内部 -------------
    def _refresh_client(self):
        now = time.time()
        if now < self._sts_expires - 300:
            return
        sts = fetch_sts()
        self._sts_expires = datetime.fromisoformat(
            sts["Expiration"].replace("Z", "+00:00")
        ).timestamp()
        provider = oss.credentials.StaticCredentialsProvider(
            access_key_id=sts["AccessKeyId"],
            access_key_secret=sts["AccessKeySecret"],
            security_token=sts["SecurityToken"],
        )
        cfg = oss.config.load_default()
        cfg.credentials_provider = provider
        cfg.region = self.region
        cfg.connect_timeout = cfg.readwrite_timeout = self.timeout
        if self.proxy:
            cfg.proxy_host = self.proxy
        self._client = oss.Client(cfg)
        print(Fore.YELLOW + "正在运行oss_tool2")
        print(f"[STS] 已刷新，有效期至 {sts['Expiration']}")

    @property
    def client(self) -> oss.Client:
        self._refresh_client()
        return self._client
        
                
    def upload_new(self, key: str, local_path: str) -> str:
        # 获取文件总大小
        import os
        total_size = os.path.getsize(local_path)
        with open(local_path, "rb") as f:
            # 定义进度条样式
            with Progress(
                TextColumn(
                    "[bold blue]{task.description}"),
                    BarColumn(),
                    "[progress.percentage]{task.percentage:>3.0f}%",
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn()
                ) as progress:            
                    # 创建进度条任务
                    task_id = progress.add_task(description="正在上传...", total=total_size)
                    def _progress_fn(n, written, total):
                        # 更新进度条：completed 参数接收已完成的绝对字节数
                        progress.update(task_id, completed=written)
                    result = self.client.put_object(
                        oss.PutObjectRequest(
                            bucket=self.bucket, 
                            key=key, 
                            body=f, 
                            progress_fn=_progress_fn
                        )
                    )
        if result.status_code == 200:
            url = f"https://{self.bucket}.oss-{self.region}.aliyuncs.com/{key}"
            # 使用 rich 的 print 以保持风格统一
            progress.console.print(f"[green]✓ [上传成功][/green] {local_path} -> {url}")
            return url    
        raise Exception(f"上传失败：{result.status_code}, {result.request_id}")


    # ------------- 上传 -------------
    def upload(self, key: str, local_path: str) -> str:
        with open(local_path, "rb") as f:
            progress_state = {'saved': 0}
            #rate = 0
          #  rate_list = []
            def _progress_fn(n, written, total):
                # 使用字典存储累计写入的字节数，避免使用 global 变量
                progress_state['saved'] += n
                # 计算当前上传百分比，将已写入字节数与总字节数进行除法运算后取整
               # global rate
               # print(str(written))
               # print(str(total))
                rate = int(100 * (float(written) / float(total)))
               # rate_list.append(rate)
               # print(str(rate))
            #for i in track(rate, description="Processing... "):
                #rate = int(100 * (float(written) / float(total)))
                   # time.sleep(0.01) # 模拟任务耗时
                # 打印当前上传进度，\r 表示回到行首，实现命令行中实时刷新效果
                # end='' 表示不换行，使下一次打印覆盖当前行
                print(f'\r上传进度：{rate}% ', end='')
          #  for i in track(rate_list, description = 'Uploading... '):
          #      time.sleep(0.01)
            result = self.client.put_object(
                oss.PutObjectRequest(bucket=self.bucket, key=key, body=f, progress_fn=_progress_fn)
            )
       # track(rate, description = 'Uploading... ')
       # time.sleep(0.01)
        if result.status_code == 200:
            url = f"https://{self.bucket}.oss-{self.region}.aliyuncs.com/{key}"
            print(Fore.GREEN + f"\n[上传成功] {local_path} -> {url}")
            return url
        raise Exception(Fore.RED + f"\n上传失败：{result.status_code}, {result.request_id}")

    # ------------- 下载 -------------
    def download(self, key: str, local_path: str):
        result = self.client.get_object(
            oss.GetObjectRequest(bucket=self.bucket, key=key)
        )
        if result.status_code == 200:
            os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(result.body.read())
            print(f"[下载成功] oss://{self.bucket}/{key} -> {local_path}")
        else:
            raise Exception(f"下载失败：{result.status_code}, {result.request_id}")

    # ------------- 列举 -------------
    def list_objects(self, prefix: str = "", max_keys: int = 100) -> List[str]:
        resp = self.client.list_objects(
            oss.ListObjectsRequest(
                bucket=self.bucket, prefix=prefix, max_keys=max_keys
            )
        )
        if resp.status_code != 200:
            raise Exception(f"列举失败：{resp.status_code}, {resp.request_id}")
        if resp.contents is None:
            print(Fore.GREEN + f"[列出成功] 前缀 '{prefix}' 下无文件")
            return []
        keys = [obj.key for obj in resp.contents]
        print(Fore.GREEN + f"[列出成功] 前缀 '{prefix}' 下共 {len(keys)} 个文件" + Style.RESET_ALL)
        return keys

    # ------------- 预签名 -------------
    def presign_url(self, key: str, expires_seconds: int = 3600) -> str:
        req = oss.GetObjectRequest(bucket=self.bucket, key=key)
        url = self.client.presign(req, expires_in=expires_seconds)
        print(f"[预签名] 有效期 {expires_seconds}s -> {url}")
        return url

    # ------------- 删除：单个 -------------
    def delete_one(self, key: str):
        result = self.client.delete_object(
            oss.DeleteObjectRequest(bucket=self.bucket, key=key)
        )
        if result.status_code in (200, 204):
            print(Fore.GREEN + f"[删除成功] {key}")
        else:
            raise Exception(Fore.RED + f"删除失败：{result.status_code}, {result.request_id}")

    # ------------- 删除：批量（≤1000）-------------
    def delete_batch(self, keys: List[str]):
        if not keys:
            print("[删除] 文件列表为空")
            return
        # 构造 Delete 请求体
        objects = [oss.DeleteObject(key=k) for k in keys]
        req = oss.DeleteMultipleObjectsRequest(
            bucket=self.bucket,
            delete=oss.Delete(
                object=objects,
                quiet=False,  # 返回详细结果
            ),
        )
        result = self.client.delete_multiple_objects(req)
        if result.status_code == 200:
            deleted = [obj.key for obj in result.deleted or []]
            print(f"[批量删除] 成功 {len(deleted)} 个")
            for k in deleted:
                print("  -", k)
        else:
            raise Exception(f"批量删除失败：{result.status_code}, {result.request_id}")

    # ------------- 删除：前缀（交互式）-------------
    def delete_prefix(self, prefix: str, dry_run: bool = True):
        """先列举，再确认/执行删除"""
        keys = self.list_objects(prefix)
        if not keys:
            return
        print(f"\n即将删除以上 {len(keys)} 个文件（前缀: {prefix}）")
        if dry_run:
            print("*** 当前为预览模式，加 dry_run=False 真正删除 ***")
            return
        confirm = input("确认删除？(yes/no): ").strip().lower()
        if confirm == "yes":
            # 每批 ≤1000 个
            for i in range(0, len(keys), 1000):
                self.delete_batch(keys[i : i + 1000])
        else:
            print("已取消删除")

def main(filepath,filename):
    tool = OSSTool(region="cn-shanghai", bucket="msyk")
    print(Fore.YELLOW + "自动获取oss文件目录所在路径为: " + Style.RESET_ALL + filepath)
    ch = input(Fore.MAGENTA + "自动获取的路径是否正确 [Y/n]:" +Style.RESET_ALL)
    if ch == "y" or ch == "Y":
    	url = filepath
    else:
    	url = input(Fore.YELLOW + "手动输入oss文件目录所在路径: " + Style.RESET_ALL)     
  #  url = "squirrel/material/6340F8149D6E4EBFBE7E5F04F83B08A3/jpg/20250602/BCA78D6F261849409FF1528506C416DF/"
  
    print(Fore.YELLOW + "自动获取oss文件名称为: " + Style.RESET_ALL + filename)
    dh = input(Fore.MAGENTA + "自动获取的名称是否正确 [Y/n]:" +Style.RESET_ALL)
    if dh == "y" or ch == "Y":
    	file_url = filepath + filename
    else:
        file_url = filepath + input(Fore.YELLOW + "手动输入oss文件名称: " + Style.RESET_ALL)
  #  file_url = "squirrel/material/6340F8149D6E4EBFBE7E5F04F83B08A3/jpg/20250602/BCA78D6F261849409FF1528506C416DF/12824766559608369306613659331627.jpg"
    files = tool.list_objects(url)
    for f in files:
        print(" _", f)
        
    yn = input(Fore.MAGENTA + "是否上传文件 [Y/n]:" + Style.RESET_ALL)
    if yn == "y" or yn == "Y":
        local_path = input(Fore.GREEN + "手动输入本地文件路径: " + Style.RESET_ALL)
      #  local_path = "12824566638478648306590492305054.jpg"
        tool.delete_one(file_url)
        tool.upload_new(file_url, local_path)
    
    ny = input(Fore.MAGENTA + "是否重新列举 [Y/n]:" + Style.RESET_ALL)
    if ny == "y" or ny == "Y":
        files = tool.list_objects(url)
        for f in files:
            print(" _", f)
               
# ==================== 命令行示例 ====================
if __name__ == "__main__":
    tool = OSSTool(region="cn-shanghai", bucket="msyk")
    main(filepath,filename)

    # 1. 上传
    #url = tool.upload("sdk-v2/demo.txt", "demo.txt")

    # 2. 列举
    # files = tool.list_objects("/msyk/squirrel/material/6340F8149D6E4EBFBE7E5F04F83B08A3/video/20231214/B4F14EA69365437CA22ADFD5297E00CB/")
    # for f in files:
    #     print(" -", f)

    # 3. 删除单个
    # tool.delete_one("/msyk/squirrel/material/6340F8149D6E4EBFBE7E5F04F83B08A3/video/20231214/B4F14EA69365437CA22ADFD5297E00CB/D4C592D86F50ECC04A0AF69502762E7D.mp4")
    # time.sleep(3)
    # url = tool.upload("/squirrel/material/6340F8149D6E4EBFBE7E5F04F83B08A3/video/20231214/B4F14EA69365437CA22ADFD5297E00CB/D4C592D86F50ECC04A0AF69502762E7D.mp4")
    # time.sleep(3)
    #
    # #files = tool.list_objects("squirrel/material/6D4780C3C32C4E749AF241A11E59F537/ppt/1755515633254/B8C247FA8387463CAD1C9B90D374A772/00000016")
    # for f in files:
    #     print(" -", f)
    
    #tool.download("/squirrel/material/6340F8149D6E4EBFBE7E5F04F83B08A3/video/20231214/B4F14EA69365437CA22ADFD5297E00CB/D4C592D86F50ECC04A0AF69502762E7D.mp4", "bk/page2.jpg")
    # 4. 批量删除（已知 key 列表）
    #tool.delete_batch(["sdk-v2/a.txt", "sdk-v2/b.txt"])

    # 5. 交互式删除整个前缀（预览）
    #tool.delete_prefix("sdk-v2/", dry_run=True)
    #tool.delete_prefix("sdk-v2/", dry_run=False)
