import os
import sys
import re
import requests
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta

# ---------- 工具函数 ----------
def beijing_time():
    """返回北京时间字符串"""
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

def send_wecom(webhook_url, message):
    """发送企业微信消息"""
    if not webhook_url:
        print("❌ 未配置企业微信 Webhook，无法发送通知")
        return False
    try:
        resp = requests.post(
            webhook_url,
            json={"msgtype": "text", "text": {"content": message}},
            timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("errcode") == 0:
            print("✅ 企业微信通知发送成功")
            return True
        else:
            print(f"❌ 企业微信通知发送失败: {result}")
            return False
    except Exception as e:
        print(f"❌ 企业微信通知异常: {e}")
        return False

# ---------- 主函数 ----------
def main():
    # 1. 从环境变量读取配置（GitHub Secrets）
    # 必须项
    synjones_token = os.getenv("SYNJONES_AUTH_TOKEN")
    cookie = os.getenv("REQUEST_COOKIE")
    wecom_webhook = os.getenv("WECOM_WEBHOOK")

    # 检查必需变量
    missing = []
    if not synjones_token:
        missing.append("SYNJONES_AUTH_TOKEN")
    if not cookie:
        missing.append("REQUEST_COOKIE")
    if not wecom_webhook:
        missing.append("WECOM_WEBHOOK")
    if missing:
        print(f"❌ 缺少必要环境变量: {missing}")
        sys.exit(1)

    # 请求体参数（从环境变量读取，如果没有则使用抓包中的默认值）
    payload = {
        "feeitemid": os.getenv("FEEITEM_ID", "428"),
        "type": os.getenv("FEE_TYPE", "IEC"),
        "level": os.getenv("FEE_LEVEL", "4"),
        "campus": os.getenv("CAMPUS", "天津工业大学&天津工业大学"),
        "building": os.getenv("BUILDING", "20161008184448464922&西苑7号楼"),
        "floor": os.getenv("FLOOR", "6&6层"),
        "room": os.getenv("ROOM", "20161009111811827231&1栋608")
    }

    # 2. 构造请求头（完全模拟抓包）
    headers = {
        "Authorization": os.getenv("AUTHORIZATION", "Basic Y2hhcmdlOmNoYXJnZV9zZWNyZXQ="),
        "synjones-auth": f"bearer {synjones_token}",
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Linux; Android 16; V2408A Build/BQ2A.250705.001-BP2A.250605.031.A3_V000L1; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380275 MMWEBSDK/20250202 MMWEBID/3998 wxwork/5.0.6 MicroMessenger/7.0.1 NetType/WIFI Language/zh Lang/zh ColorScheme/Light wwmver/3.26.506.647",
        "Origin": "http://wxykt.tiangong.edu.cn",
        "Referer": "http://wxykt.tiangong.edu.cn/charge-app/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # 3. 发送请求
    url = "http://wxykt.tiangong.edu.cn/charge/feeitem/getThirdData"
    encoded_body = urlencode(payload)
    print(f"🔍 查询时间: {beijing_time()}")
    print(f"📤 请求参数: {payload}")

    try:
        response = requests.post(url, headers=headers, data=encoded_body, timeout=15)
        print(f"📥 响应状态码: {response.status_code}")
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        # 尝试发送错误通知
        err_msg = f"【电费查询失败】\n时间: {beijing_time()}\n错误: {e}"
        send_wecom(wecom_webhook, err_msg)
        sys.exit(1)

    # 4. 检查业务状态码
    code = data.get("code")
    if code != 200:
        error_msg = f"业务错误码 {code}: {data.get('msg', '未知错误')}"
        print(f"❌ {error_msg}")
        send_wecom(wecom_webhook, f"【电费查询失败】\n时间: {beijing_time()}\n错误: {error_msg}")
        sys.exit(1)

    # 5. 从响应中提取电量信息
    show_info = data.get("map", {}).get("showData", {}).get("信息")
    if not show_info:
        print("❌ 未找到 showData.信息 字段")
        send_wecom(wecom_webhook, f"【电费查询失败】\n时间: {beijing_time()}\n错误: 响应结构异常")
        sys.exit(1)

    # 使用正则提取电量数值
    match = re.search(r"剩余购电量:([\d.]+)度", show_info)
    if match:
        electricity = match.group(1)
        print(f"⚡ 剩余电量: {electricity} 度")
    else:
        electricity = "未知"
        print(f"⚠️ 未能提取电量，原始信息: {show_info}")

    # 6. 构建通知消息（简洁明了）
    building_name = data.get("map", {}).get("data", {}).get("buildingName", "未知楼栋")
    room_name = data.get("map", {}).get("data", {}).get("roomName", "未知房间")
    message = (
        f"【电费提醒】\n"
        f"楼栋：{building_name}\n"
        f"房间：{room_name}\n"
        f"时间：{beijing_time()}\n"
        f"剩余电量：{electricity} 度"
    )

    # 7. 发送企业微信通知（always模式）
    send_wecom(wecom_webhook, message)
    print("✅ 脚本执行完毕")

if __name__ == "__main__":
    main()
