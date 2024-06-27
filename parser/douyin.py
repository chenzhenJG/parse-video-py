import json
from urllib.parse import unquote

import httpx
from parsel import Selector
from bs4 import BeautifulSoup
import re
from .base import BaseParser, VideoAuthor, VideoInfo


class DouYin(BaseParser):
    """
    抖音 / 抖音火山版
    """
   

    async def parse_share_url(self, share_url: str) -> VideoInfo:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(share_url, headers=self.get_default_headers())
            response.raise_for_status()

        # 使用 BeautifulSoup 解析 HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # 找到包含 window._ROUTER_DATA 的 script 标签，并提取 nonce 值
        scripts = soup.find_all('script', text=re.compile(r'window\._ROUTER_DATA\s*=\s*{'))
        cid = None
        for script in scripts:
            nonce_value = script.get('nonce')
            if nonce_value:
                cid = nonce_value
                print(f"====================================Nonce value: {nonce_value}")
            else:
                print("No nonce attribute found.")

        sel = Selector(response.text)
        # print("aaaaaaaaaaaaaaaaaaaaaaaaaa"+'script[nonce="'+cid+'"]::text')
        render_data = sel.css('script[nonce="'+cid+'"]::text').getall()
        # 遍历所有找到的script标签内容
        for script_content in render_data:
            # 检查script标签内容是否包含window._ROUTER_DATA
            if 'window._ROUTER_DATA' in script_content:
                match = re.search(r'{.*}', script_content)
                if match:
                    render_data = match.group(0)
                else:
                    print("No JSON data found.")
                
                break
        # # 解码 Unicode 转义序列
        render_data = re.sub(r'(\\u[a-zA-Z0-9]{4})',lambda x:x.group(1).encode("utf-8").decode("unicode-escape"),render_data)
        
        if len(render_data) <= 0:
            raise Exception("failed to parse render data from HTML")
        render_data = unquote(render_data)  # urldecode
        json_data = json.loads(render_data)
    
        loaderData = json_data["loaderData"]
        # 如果没有视频信息，获取并抛出异常
        if len(loaderData["video_(id)/page"]["videoInfoRes"]["item_list"]) == 0:
            err_detail_msg = "failed to parse video info from HTML"
            if len(filter_list := loaderData["video_(id)/page"]["videoInfoRes"]["filter_list"]) > 0:
                err_detail_msg = filter_list[0]["detail_msg"]
            raise Exception(err_detail_msg)

        data = loaderData["video_(id)/page"]["videoInfoRes"]["item_list"][0]

        # 获取图集图片地址
        images = []
        # 如果data含有 images，并且 images 是一个列表
        if "images" in data and isinstance(data["images"], list):
            # 获取每个图片的url_list中的第一个元素，非空时添加到images列表中
            for img in data["images"]:
                if (
                    "url_list" in img
                    and isinstance(img["url_list"], list)
                    and len(img["url_list"]) > 0
                    and len(img["url_list"][0]) > 0
                ):
                    images.append(img["url_list"][0])

        # 获取视频播放地址
        video_url = data["video"]["play_addr"]["url_list"][0].replace("playwm", "play")
        # 如果图集地址不为空时，因为没有视频，上面抖音返回的视频地址无法访问，置空处理
        if len(images) > 0:
            video_url = ""

        # 获取重定向后的mp4视频地址
        # 图集时，视频地址为空，不处理
        video_mp4_url = ""
        if len(video_url) > 0:
            video_mp4_url = await self.get_video_redirect_url(video_url)

        video_info = VideoInfo(
            video_url=video_mp4_url,
            cover_url=data["video"]["cover"]["url_list"][0],
            title=data["desc"],
            images=images,
            author=VideoAuthor(
                uid=data["author"]["sec_uid"],
                name=data["author"]["nickname"],
                avatar=data["author"]["avatar_thumb"]["url_list"][0],
            ),
        )
        return video_info

    async def get_video_redirect_url(self, video_url: str) -> str:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.get(video_url, headers=self.get_default_headers())
        # 返回重定向后的地址，如果没有重定向则返回原地址(抖音中的西瓜视频,重定向地址为空)
        return response.headers.get("location") or video_url

    async def parse_video_id(self, video_id: str) -> VideoInfo:
        req_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
        return await self.parse_share_url(req_url)
