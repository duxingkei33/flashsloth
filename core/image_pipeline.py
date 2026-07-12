"""
ImagePipeline — 统一图片上传管线

流程:
  1. extract()    — 从 Markdown body 提取所有图片引用
  2. resolve()    — 解析本地/远程路径
  3. upload()     — 依次尝试: 平台专用上传 → SM.MS fallback
  4. replace()    — 替换 body 中的图片 URL

每个 Publisher 只需实现 platform_upload() 即可接入此管线。
"""
import re, os, io, time, hashlib, requests
from typing import Optional, Callable
from dataclasses import dataclass, field


@dataclass
class ImageRef:
    """一张图片的引用信息"""
    src: str                      # 原始 URL/路径
    alt: str = ""                 # 替代文本
    local_path: Optional[str] = None  # 本地文件路径（解析后）
    source_type: str = ""         # markdown | html
    uploaded_url: str = ""        # 上传后的平台 CDN URL
    filesize: int = 0             # 文件大小(bytes)
    width: int = 0
    height: int = 0
    error: str = ""


class ImageExtractor:
    """从文章正文中提取图片引用"""

    @staticmethod
    def extract(body: str) -> list[ImageRef]:
        """提取 body 中所有图片引用，去重"""
        seen = set()
        images = []

        # Markdown 图片: ![alt](url)
        for m in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', body):
            src = m.group(2).strip()
            if src not in seen:
                seen.add(src)
                images.append(ImageRef(
                    src=src,
                    alt=m.group(1),
                    source_type="markdown"
                ))

        # HTML img: <img src="..." alt="...">
        for m in re.finditer(
            r'<img[^>]*src="([^"]+)"[^>]*(?:alt="([^"]*)")?[^>]*>',
            body, re.IGNORECASE
        ):
            src = m.group(1).strip()
            if src not in seen:
                seen.add(src)
                images.append(ImageRef(
                    src=src,
                    alt=m.group(2) or "",
                    source_type="html"
                ))

        return images


class ImageResolver:
    """将图片引用解析为本地文件路径"""

    def __init__(self, base_dir: str = ""):
        self.base_dir = base_dir or os.getcwd()

    def resolve(self, img: ImageRef) -> ImageRef:
        """
        解析图片引用为本地文件路径。
        返回新 ImageRef（不修改原对象）。
        """
        src = img.src

        # 已经是本地文件路径
        if os.path.isfile(src):
            img.local_path = os.path.abspath(src)
            return img

        # /static/uploads/ 路径
        if src.startswith("/static/uploads/"):
            rel = src[len("/static/uploads/"):]
            for base in [self.base_dir, os.path.dirname(self.base_dir)]:
                candidate = os.path.join(base, "static", "uploads", rel)
                if os.path.isfile(candidate):
                    img.local_path = os.path.abspath(candidate)
                    return img

        # static/uploads/ 相对路径
        if src.startswith("static/uploads/"):
            for base in [self.base_dir, os.path.dirname(self.base_dir)]:
                candidate = os.path.join(base, src)
                if os.path.isfile(candidate):
                    img.local_path = os.path.abspath(candidate)
                    return img

        # 纯文件名
        if not src.startswith(("http://", "https://", "/")):
            for base in [self.base_dir,
                         os.path.join(self.base_dir, "static", "uploads")]:
                candidate = os.path.join(base, src)
                if os.path.isfile(candidate):
                    img.local_path = os.path.abspath(candidate)
                    return img

        # 远程URL — 下载到临时目录
        if src.startswith(("http://", "https://")):
            try:
                local = self._download_remote(src)
                if local:
                    img.local_path = local
            except Exception as e:
                img.error = f"下载远程图片失败: {e}"
            return img

        return img

    def _download_remote(self, url: str, timeout: int = 30) -> Optional[str]:
        """下载远程图片到临时目录"""
        try:
            resp = requests.get(url, timeout=timeout, stream=True,
                                headers={"User-Agent": "FlashSloth/1.0"})
            resp.raise_for_status()
            ext = self._guess_ext(resp.headers.get("content-type", ""), url)
            tmp_dir = "/tmp/flashsloth_images"
            os.makedirs(tmp_dir, exist_ok=True)
            name = hashlib.md5(url.encode()).hexdigest() + ext
            path = os.path.join(tmp_dir, name)
            with open(path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            return path
        except Exception:
            return None

    @staticmethod
    def _guess_ext(content_type: str, url: str) -> str:
        ext_map = {
            "image/jpeg": ".jpg", "image/png": ".png",
            "image/gif": ".gif", "image/webp": ".webp",
            "image/svg+xml": ".svg", "image/bmp": ".bmp",
        }
        for ct, ext in ext_map.items():
            if ct in content_type:
                return ext
        # fallback: 从 URL 猜
        base = os.path.basename(url.split("?")[0])
        _, ext = os.path.splitext(base)
        return ext if ext else ".jpg"


class ImageUploader:
    """
    统一图片上传器。

    用法:
        uploader = ImageUploader()
        # 用平台专用上传函数
        uploader.upload(img, platform_upload_fn=my_upload)
        # 或直接调用
        url = uploader.upload_to_smms(img.local_path)
    """

    SMMS_API = "https://sm.ms/api/v2/upload"

    def __init__(self, smms_token: str = ""):
        self.smms_token = smms_token

    def upload(self, img: ImageRef,
               platform_upload_fn: Optional[Callable] = None) -> ImageRef:
        """
        上传一张图片：
        1. 优先使用 platform_upload_fn（平台专属上传）
        2. 失败后 fallback 到 SM.MS
        """
        if not img.local_path or not os.path.isfile(img.local_path):
            img.error = "本地文件不存在"
            return img

        # 获取文件信息
        img.filesize = os.path.getsize(img.local_path)
        try:
            from PIL import Image
            pil_img = Image.open(img.local_path)
            img.width, img.height = pil_img.size
        except ImportError:
            pass
        except Exception:
            pass

        # 尝试平台上传
        if platform_upload_fn:
            try:
                result = platform_upload_fn(img.local_path)
                if result and result.get("url"):
                    img.uploaded_url = result["url"]
                    return img
                else:
                    img.error = result.get("error", "平台上传失败")
            except Exception as e:
                img.error = f"平台上传异常: {e}"

        # Fallback: SM.MS
        if not img.uploaded_url:
            try:
                url = self.upload_to_smms(img.local_path)
                if url:
                    img.uploaded_url = url
                    img.error = ""
                else:
                    img.error = img.error or "SM.MS 上传也失败了"
            except Exception as e:
                img.error = f"SM.MS 异常: {e}"

        return img

    def upload_to_smms(self, filepath: str) -> Optional[str]:
        """上传到 SM.MS 图床，返回图片 URL"""
        try:
            headers = {}
            if self.smms_token:
                headers["Authorization"] = self.smms_token
            with open(filepath, "rb") as f:
                resp = requests.post(
                    self.SMMS_API,
                    files={"smfile": f},
                    headers=headers,
                    timeout=30,
                )
            data = resp.json()
            if data.get("success"):
                return data["data"]["url"]
            # 图片已存在时返回图片 URL
            if "images" in data:
                return data["images"]
            return None
        except Exception:
            return None

    def upload_batch(self, images: list[ImageRef],
                     platform_upload_fn: Optional[Callable] = None,
                     concurrency: int = 3) -> list[ImageRef]:
        """批量上传图片"""
        results = []
        for img in images:
            result = self.upload(img, platform_upload_fn)
            results.append(result)
            time.sleep(0.5)  # 礼貌延迟
        return results


class BodyImageReplacer:
    """替换 body 中的图片 URL 为上传后的 URL"""

    @staticmethod
    def replace(body: str, images: list[ImageRef],
                uploaded_only: bool = True) -> str:
        """
        替换正文中的图片引用。

        参数:
            body: 原始正文
            images: ImageRef 列表（含 uploaded_url）
            uploaded_only: 只替换成功上传的图片
        """
        result = body
        for img in images:
            if not img.uploaded_url:
                if uploaded_only:
                    continue
                else:
                    continue  # 不上传的保留原样

            src = re.escape(img.src)

            # Markdown 格式: ![alt](src)
            result = re.sub(
                rf'!\[([^\]]*)\]\({src}\)',
                lambda m: f'![{m.group(1)}]({img.uploaded_url})',
                result
            )
            # HTML 格式: <img src="src" ...>
            result = re.sub(
                rf'<img[^>]*src="{src}"[^>]*>',
                lambda m: re.sub(
                    rf'src="{img.src}"',
                    f'src="{img.uploaded_url}"',
                    m.group(0)
                ),
                result
            )

        return result


# ═══════════════════════════════════════════════
# 一站式管线
# ═══════════════════════════════════════════════

class ImagePipeline:
    """
    一站式图片处理管线。

    用法:
        pipeline = ImagePipeline(base_dir="/path/to/project")
        new_body, results = pipeline.process(
            body=article_body,
            platform_upload_fn=my_platform_upload
        )
    """

    def __init__(self, base_dir: str = "", smms_token: str = ""):
        self.extractor = ImageExtractor()
        self.resolver = ImageResolver(base_dir)
        self.uploader = ImageUploader(smms_token)
        self.replacer = BodyImageReplacer()

    def process(self, body: str,
                platform_upload_fn: Optional[Callable] = None
                ) -> tuple[str, list[ImageRef]]:
        """
        完整处理管线：提取 → 解析 → 上传 → 替换

        返回: (替换后的 body, ImageRef 列表)
        """
        # 1. 提取
        images = self.extractor.extract(body)
        if not images:
            return body, []

        # 2. 解析本地路径
        for img in images:
            self.resolver.resolve(img)

        # 3. 上传
        images = self.uploader.upload_batch(images, platform_upload_fn)

        # 4. 替换
        new_body = self.replacer.replace(body, images)

        return new_body, images
