#!/usr/bin/env python3
"""
抖音博主主页最新视频提取工具 v5
Playwright直接通过浏览器内API获取全部视频，无需拦截
"""
import sys, json
from datetime import datetime
from playwright.sync_api import sync_playwright

def extract_latest_video_url(douyin_url: str) -> dict:
    result = {"status": "error", "message": "", "video_url": "", "video_title": "", "author": "", "publish_time": ""}
    all_videos = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='zh-CN'
        )
        page = context.new_page()
        
        try:
            # Step 1: 打开主页（获取Cookie和鉴权）
            print(f"[1/2] 打开主页", file=sys.stderr)
            page.goto(douyin_url, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(3000)
            
            sec_uid = douyin_url.split('/user/')[-1].split('?')[0]
            
            # Step 2: 在浏览器内循环请求API所有页面
            print(f"[2/2] 加载视频列表", file=sys.stderr)
            cursor = 0
            max_pages = 5
            
            for page_num in range(max_pages):
                api_url = f"https://www.douyin.com/aweme/v1/web/aweme/post/?sec_user_id={sec_uid}&count=18&max_cursor={cursor}&aid=1128"
                
                result_json = page.evaluate(f'''
                    async () => {{
                        try {{
                            const r = await fetch("{api_url}", {{
                                credentials: "include",
                                headers: {{"Accept": "application/json"}}
                            }});
                            const text = await r.text();
                            return text;
                        }} catch(e) {{
                            return "ERROR: " + e.toString();
                        }}
                    }}
                ''')
                
                if result_json.startswith("ERROR:"):
                    print(f"  ⚠️ API错误: {result_json[:80]}", file=sys.stderr)
                    break
                
                try:
                    data = json.loads(result_json)
                except:
                    print(f"  ⚠️ JSON解析失败: {result_json[:100]}", file=sys.stderr)
                    break
                
                if 'aweme_list' not in data:
                    break
                    
                # 去重加入
                existing_ids = {v['id'] for v in all_videos}
                count = 0
                for item in data['aweme_list']:
                    vid = item.get('aweme_id', '')
                    if vid and vid not in existing_ids:
                        all_videos.append({
                            'id': vid,
                            'desc': item.get('desc', ''),
                            'author': item.get('author', {}).get('nickname', ''),
                            'create_time': item.get('create_time', 0),
                        })
                        existing_ids.add(vid)
                        count += 1
                
                has_more = data.get('has_more', 0) == 1
                cursor = data.get('max_cursor', 0)
                
                print(f"  第{page_num+1}页: +{count} 条 (共{len(all_videos)})", file=sys.stderr)
                
                if not has_more or count == 0:
                    break
            
            print(f"  共 {len(all_videos)} 条视频", file=sys.stderr)
            
            if all_videos:
                all_videos.sort(key=lambda x: x.get('create_time', 0), reverse=True)
                latest = all_videos[0]
                result["video_url"] = f"https://www.douyin.com/video/{latest['id']}"
                result["video_title"] = latest.get('desc', '')
                result["author"] = latest.get('author', '')
                result["status"] = "success"
                ts = latest.get('create_time', 0)
                if ts:
                    result["publish_time"] = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
                
                # 返回当天所有视频
                today_start = datetime.now().replace(hour=0, minute=0, second=0)
                today_videos = []
                for v in all_videos:
                    vt = v.get('create_time', 0)
                    if vt:
                        vtime = datetime.fromtimestamp(vt)
                        if vtime >= today_start:
                            today_videos.append({
                                'id': v['id'],
                                'desc': v['desc'],
                                'create_time': vtime.strftime('%H:%M')
                            })
                
                result['today_videos_count'] = len(today_videos)
                result['today_videos'] = today_videos[:10]  # 最多输出10条
                print(f"  ✅ 最新: {result['author']} | {result['publish_time']}", file=sys.stderr)
                print(f"  今日共 {len(today_videos)} 条视频", file=sys.stderr)
            else:
                result["message"] = "未找到视频"
                
        except Exception as e:
            result["message"] = str(e)
        finally:
            browser.close()
    
    return result

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "请提供链接"}))
        sys.exit(1)
    r = extract_latest_video_url(sys.argv[1])
    print(json.dumps(r, ensure_ascii=False))
